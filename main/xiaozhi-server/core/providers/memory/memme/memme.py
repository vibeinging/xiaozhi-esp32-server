import asyncio
import hashlib
import ipaddress
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urlparse

import httpx

from core.safety.memory_filter import (
    exclude_reason,
    filter_for_long_term_memory,
    filter_recalled_memory,
    redact_for_long_term_memory,
)

from ..base import MemoryProviderBase, logger

TAG = __name__
QUEUE_FILTER_VERSION = 2


class PermanentMemMeError(RuntimeError):
    """A request that cannot succeed without changing config or payload."""


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _message_text(content: Any) -> Optional[str]:
    if content is None:
        return None
    text = content if isinstance(content, str) else str(content)
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            decoded = json.loads(stripped)
            nested = decoded.get("content") if isinstance(decoded, dict) else None
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        except (json.JSONDecodeError, TypeError):
            pass
    return stripped


class MemoryProvider(MemoryProviderBase):
    """MemMe REST provider with a local, durable retry queue."""

    requires_durable_save = True
    _global_workers: Dict[str, "MemoryProvider"] = {}

    def __init__(
        self, config: Dict[str, Any], summary_memory=None, worker_only: bool = False
    ):
        super().__init__(config)
        self.base_url = str(config.get("base_url", "")).strip().rstrip("/")
        raw_api_key = str(config.get("api_key", "")).strip()
        self.api_key = os.path.expandvars(raw_api_key)
        if self.api_key == raw_api_key and raw_api_key.startswith("${"):
            self.api_key = ""
        self.user_id = str(config.get("user_id", "")).strip()
        self.agent_id = str(config.get("agent_id", "")).strip()
        self.app_id = str(config.get("app_id", "xiaozhi")).strip()
        self.request_timeout = max(0.1, float(config.get("request_timeout_seconds", 3)))
        self.lease_seconds = max(30.0, self.request_timeout * 2 + 5)
        self.recall_limit = max(1, min(int(config.get("recall_limit", 5)), 50))
        self.recall_max_chars = max(
            256, min(int(config.get("recall_max_chars", 4000)), 32000)
        )
        self.queue_max_jobs = max(1, int(config.get("queue_max_jobs", 10000)))
        self.queue_max_bytes = max(1024, int(config.get("queue_max_bytes", 268435456)))
        self.dead_letter_max_jobs = max(
            1, int(config.get("dead_letter_max_jobs", 1000))
        )
        self.retry_batch_size = max(0, min(int(config.get("retry_batch_size", 2)), 100))
        self.retry_base_seconds = max(1.0, float(config.get("retry_base_seconds", 10)))
        self.retry_max_seconds = max(
            self.retry_base_seconds,
            float(config.get("retry_max_seconds", 3600)),
        )
        # Compact needs an LLM on the MemMe server. Raw events are already
        # searchable, so the safe no-LLM default must not create endless retries.
        self.compact_on_save = _as_bool(config.get("compact_on_save"), False)
        self.include_device_id = _as_bool(config.get("include_device_id"), False)
        # 儿童长期记忆不允许通过运行时配置绕过过滤。
        self.write_filter_enabled = True
        if config.get("write_filter") is not None and not _as_bool(
            config.get("write_filter"), True
        ):
            logger.bind(tag=TAG).warning("MemMe 已忽略不安全的 write_filter=false")
        queue_path = os.path.expandvars(
            str(config.get("queue_path", "data/memme-retry.sqlite3"))
        )
        self.queue_path = Path(queue_path).expanduser().resolve()
        self.device_id = None
        self._transport = None
        self._drain_lock = asyncio.Lock()
        self._worker_only = worker_only
        self._worker_task = None
        self._worker_stop = None
        self._worker_id = uuid.uuid4().hex
        self.retry_poll_seconds = max(
            0.1, float(config.get("retry_poll_seconds", 1.0))
        )

        parsed_url = urlparse(self.base_url)
        missing = []
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            missing.append("base_url")
        elif not self._is_loopback_host(parsed_url.hostname):
            missing.append("loopback_base_url")
        if not self.api_key:
            missing.append("api_key")
        scoped_values = (("app_id", self.app_id),)
        if not worker_only:
            scoped_values = (
                ("user_id", self.user_id),
                ("agent_id", self.agent_id),
                ("app_id", self.app_id),
            )
        for key, value in scoped_values:
            if not value:
                missing.append(key)
        self.use_memme = not missing

        if not self.use_memme:
            logger.bind(tag=TAG).error(
                "MemMe 配置不完整，已停用记忆接入：" + ", ".join(missing)
            )
            return

        try:
            self._initialize_queue()
        except Exception as error:
            self.use_memme = False
            logger.bind(tag=TAG).error(f"MemMe 重试队列初始化失败: {error}")

    @staticmethod
    def _is_loopback_host(hostname: Optional[str]) -> bool:
        if not hostname:
            return False
        if hostname.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False

    def init_memory(self, role_id, llm, **kwargs):
        # role_id is currently the device MAC for older providers. MemMe deliberately
        # uses the stable IDs from its own config instead.
        super().init_memory(role_id, llm, **kwargs)
        self.device_id = kwargs.get("device_id") or role_id

    def _worker_signature(self) -> tuple:
        return (
            self.base_url,
            hashlib.sha256(self.api_key.encode("utf-8")).hexdigest(),
            self.retry_batch_size,
            self.retry_poll_seconds,
            self.retry_base_seconds,
            self.retry_max_seconds,
            self.dead_letter_max_jobs,
            self.lease_seconds,
            self.compact_on_save,
            self.include_device_id,
        )

    def ensure_global_worker(self) -> None:
        """每个队列只保留一个进程级重试任务，设备断线后仍继续工作。"""
        if not self.use_memme or self.retry_batch_size <= 0:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        key = str(self.queue_path)
        existing = type(self)._global_workers.get(key)
        if existing is not None and existing._worker_signature() == self._worker_signature():
            existing.start_background_worker()
            return
        if existing is not None:
            loop.create_task(existing.close())
        worker = self if self._worker_only else type(self)(self.config, worker_only=True)
        if not worker.use_memme:
            return
        type(self)._global_workers[key] = worker
        worker.start_background_worker()

    @classmethod
    async def close_global_workers(cls) -> None:
        workers = list(cls._global_workers.values())
        cls._global_workers.clear()
        if workers:
            await asyncio.gather(*(worker.close() for worker in workers))

    def start_background_worker(self) -> None:
        if not self.use_memme or self._worker_task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.bind(tag=TAG).warning("MemMe 后台重试将在事件循环可用后启动")
            return
        self._worker_stop = asyncio.Event()
        self._worker_task = loop.create_task(self._retry_worker())

    async def close(self) -> None:
        if self._worker_stop is not None:
            self._worker_stop.set()
        task = self._worker_task
        self._worker_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _retry_worker(self) -> None:
        while self._worker_stop is not None and not self._worker_stop.is_set():
            try:
                await self._drain_due_jobs(max(1, self.retry_batch_size))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.bind(tag=TAG).warning(
                    f"MemMe 后台重试异常: {self._error_summary(error)}"
                )
            try:
                await asyncio.wait_for(
                    self._worker_stop.wait(), timeout=self.retry_poll_seconds
                )
            except asyncio.TimeoutError:
                pass

    def _connect_queue(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.queue_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize_queue(self) -> None:
        parent_was_missing = not self.queue_path.parent.exists()
        self.queue_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent_was_missing:
            try:
                os.chmod(self.queue_path.parent, 0o700)
            except OSError:
                pass
        with self._connect_queue() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memme_jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    last_error TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    locked_until REAL,
                    worker_id TEXT,
                    filter_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(memme_jobs)")
            }
            for name, definition in (
                ("status", "TEXT NOT NULL DEFAULT 'pending'"),
                ("locked_until", "REAL"),
                ("worker_id", "TEXT"),
                ("filter_version", "INTEGER NOT NULL DEFAULT 1"),
            ):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE memme_jobs ADD COLUMN {name} {definition}"
                    )
            expected_index_columns = [
                "status",
                "next_attempt_at",
                "locked_until",
                "created_at",
            ]
            current_index_columns = [
                row[2]
                for row in connection.execute(
                    "PRAGMA index_info(idx_memme_jobs_due)"
                ).fetchall()
            ]
            if current_index_columns != expected_index_columns:
                connection.execute("DROP INDEX IF EXISTS idx_memme_jobs_due")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memme_jobs_due "
                "ON memme_jobs(status, next_attempt_at, locked_until, created_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memme_tombstones (
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL DEFAULT '',
                    app_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    block_future INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(user_id, agent_id, app_id)
                )
                """
            )
            tombstone_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(memme_tombstones)"
                )
            }
            if "block_future" not in tombstone_columns:
                connection.execute(
                    "ALTER TABLE memme_tombstones "
                    "ADD COLUMN block_future INTEGER NOT NULL DEFAULT 1"
                )
        try:
            os.chmod(self.queue_path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _job_id(kind: str, payload: Dict[str, Any]) -> str:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(f"{kind}\0{encoded}".encode("utf-8")).hexdigest()
        return f"{kind}:{digest}"

    @staticmethod
    def _error_summary(error: Exception) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"HTTP {error.response.status_code}"
        if isinstance(error, httpx.TimeoutException):
            return "request timeout"
        if isinstance(error, httpx.RequestError):
            return type(error).__name__
        return type(error).__name__

    def _enqueue(self, kind: str, payload: Dict[str, Any]) -> str:
        job_id = self._job_id(kind, payload)
        serialized = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        payload_bytes = len(serialized.encode("utf-8"))
        now = time.time()
        with self._connect_queue() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT status FROM memme_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if existing is not None:
                if existing["status"] == "dead":
                    connection.execute(
                        """
                        UPDATE memme_jobs
                        SET status='pending', attempts=0, next_attempt_at=?,
                            last_error=NULL, locked_until=NULL, worker_id=NULL,
                            filter_version=?
                        WHERE id=?
                        """,
                        (now, QUEUE_FILTER_VERSION, job_id),
                    )
                return job_id
            count = connection.execute(
                "SELECT COUNT(*) FROM memme_jobs WHERE status != 'dead'"
            ).fetchone()[0]
            if count >= self.queue_max_jobs:
                raise RuntimeError(
                    f"MemMe retry queue is full ({self.queue_max_jobs} jobs)"
                )
            queued_bytes = connection.execute(
                "SELECT COALESCE(SUM(length(CAST(payload AS BLOB))), 0) "
                "FROM memme_jobs WHERE status != 'dead'"
            ).fetchone()[0]
            if queued_bytes + payload_bytes > self.queue_max_bytes:
                raise RuntimeError(
                    f"MemMe retry queue exceeds {self.queue_max_bytes} bytes"
                )
            connection.execute(
                """
                INSERT INTO memme_jobs(
                    id, kind, payload, attempts, next_attempt_at, created_at,
                    status, filter_version
                ) VALUES (?, ?, ?, 0, ?, ?, 'pending', ?)
                """,
                (job_id, kind, serialized, now, now, QUEUE_FILTER_VERSION),
            )
        return job_id

    def _get_job(self, job_id: str) -> Optional[sqlite3.Row]:
        with self._connect_queue() as connection:
            return connection.execute(
                "SELECT * FROM memme_jobs WHERE id = ?", (job_id,)
            ).fetchone()

    def _is_scope_tombstoned(
        self, user_id: str, agent_id: str = "", app_id: str = ""
    ) -> bool:
        with self._connect_queue() as connection:
            return (
                connection.execute(
                    """
                    SELECT 1 FROM memme_tombstones
                    WHERE user_id = ? AND block_future = 1 AND (
                        (agent_id = '' AND app_id = '') OR
                        (agent_id = ? AND (app_id = '' OR app_id = ?))
                    ) LIMIT 1
                    """,
                    (user_id, agent_id, app_id),
                ).fetchone()
                is not None
            )

    def _scope_cutoff(
        self, user_id: str, agent_id: str = "", app_id: str = ""
    ) -> Optional[float]:
        with self._connect_queue() as connection:
            row = connection.execute(
                """
                SELECT MAX(created_at) AS cutoff FROM memme_tombstones
                WHERE user_id = ? AND (
                    (agent_id = '' AND app_id = '') OR
                    (agent_id = ? AND (app_id = '' OR app_id = ?))
                )
                """,
                (user_id, agent_id, app_id),
            ).fetchone()
            if row is None or row["cutoff"] is None:
                return None
            return float(row["cutoff"])

    def _tombstone_user_and_purge_queue(
        self, user_id: str, block_future: bool = True
    ) -> float:
        now = time.time()
        with self._connect_queue() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO memme_tombstones(
                    user_id, agent_id, app_id, created_at, block_future
                ) VALUES (?, '', '', ?, ?)
                ON CONFLICT(user_id, agent_id, app_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    block_future = excluded.block_future
                """,
                (user_id, now, 1 if block_future else 0),
            )
            rows = connection.execute("SELECT id, payload FROM memme_jobs").fetchall()
            delete_ids = []
            for row in rows:
                try:
                    payload = json.loads(row["payload"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict) and payload.get("user_id") == user_id:
                    delete_ids.append(row["id"])
            connection.executemany(
                "DELETE FROM memme_jobs WHERE id = ?",
                [(job_id,) for job_id in delete_ids],
            )
        return now

    def _allow_future_writes(self, user_id: str) -> None:
        with self._connect_queue() as connection:
            connection.execute(
                """
                UPDATE memme_tombstones SET block_future = 0
                WHERE user_id = ? AND agent_id = '' AND app_id = ''
                """,
                (user_id,),
            )

    def _claim_due_jobs(
        self, limit: int, exclude: Iterable[str] = ()
    ) -> List[sqlite3.Row]:
        if limit <= 0:
            return []
        excluded = [job_id for job_id in exclude if job_id]
        placeholders = ",".join("?" for _ in excluded)
        exclusion = f"AND id NOT IN ({placeholders})" if excluded else ""
        now = time.time()
        with self._connect_queue() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                f"""
                SELECT * FROM memme_jobs
                WHERE status != 'dead'
                  AND next_attempt_at <= ?
                  AND (status = 'pending' OR locked_until IS NULL OR locked_until <= ?)
                  {exclusion}
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (now, now, *excluded, limit),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE memme_jobs
                    SET status = 'processing', locked_until = ?, worker_id = ?
                    WHERE id = ?
                    """,
                    (now + self.lease_seconds, self._worker_id, row["id"]),
                )
            return rows

    def _claim_job(self, job_id: str) -> Optional[sqlite3.Row]:
        now = time.time()
        with self._connect_queue() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM memme_jobs
                WHERE id = ? AND status != 'dead'
                  AND (status = 'pending' OR locked_until IS NULL OR locked_until <= ?)
                """,
                (job_id, now),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE memme_jobs SET status='processing', locked_until=?, worker_id=? WHERE id=?",
                (now + self.lease_seconds, self._worker_id, job_id),
            )
            return row

    def _pending_job_count(self) -> int:
        with self._connect_queue() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM memme_jobs WHERE status != 'dead'"
                ).fetchone()[0]
            )

    def _dead_job_count(self) -> int:
        with self._connect_queue() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM memme_jobs WHERE status = 'dead'"
                ).fetchone()[0]
            )

    def _mark_failed(self, job_id: str, attempts: int, error: str) -> None:
        delay = min(
            self.retry_base_seconds * (2 ** min(max(attempts, 0), 10)),
            self.retry_max_seconds,
        )
        with self._connect_queue() as connection:
            connection.execute(
                """
                UPDATE memme_jobs
                SET attempts = ?, next_attempt_at = ?, last_error = ?,
                    status = 'pending', locked_until = NULL, worker_id = NULL
                WHERE id = ? AND worker_id = ?
                """,
                (
                    attempts + 1,
                    time.time() + delay,
                    error[:500],
                    job_id,
                    self._worker_id,
                ),
            )

    def _update_claimed_payload(self, job_id: str, payload: Dict[str, Any]) -> None:
        serialized = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with self._connect_queue() as connection:
            connection.execute(
                """
                UPDATE memme_jobs SET payload = ?, filter_version = ?
                WHERE id = ? AND worker_id = ?
                """,
                (serialized, QUEUE_FILTER_VERSION, job_id, self._worker_id),
            )

    def _mark_dead(self, job_id: str, attempts: int, error: str) -> None:
        with self._connect_queue() as connection:
            connection.execute(
                """
                UPDATE memme_jobs
                SET attempts = ?, last_error = ?, status = 'dead',
                    locked_until = NULL, worker_id = NULL
                WHERE id = ? AND worker_id = ?
                """,
                (attempts + 1, error[:500], job_id, self._worker_id),
            )
            connection.execute(
                """
                DELETE FROM memme_jobs
                WHERE status = 'dead' AND id NOT IN (
                    SELECT id FROM memme_jobs WHERE status = 'dead'
                    ORDER BY created_at DESC LIMIT ?
                )
                """,
                (self.dead_letter_max_jobs,),
            )

    def _finish_job(
        self,
        job_id: str,
        follow_up: Optional[tuple[str, Dict[str, Any]]] = None,
    ) -> Optional[str]:
        follow_up_id = None
        with self._connect_queue() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM memme_jobs WHERE id = ? AND worker_id = ?",
                (job_id, self._worker_id),
            )
            if follow_up is not None:
                kind, payload = follow_up
                follow_up_id = self._job_id(kind, payload)
                serialized = json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                now = time.time()
                connection.execute(
                    """
                    INSERT OR IGNORE INTO memme_jobs(
                        id, kind, payload, attempts, next_attempt_at, created_at,
                        status, filter_version
                    ) VALUES (?, ?, ?, 0, ?, ?, 'pending', ?)
                    """,
                    (
                        follow_up_id,
                        kind,
                        serialized,
                        now,
                        now,
                        QUEUE_FILTER_VERSION,
                    ),
                )
        return follow_up_id

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _post_json(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        method: str = "POST",
    ) -> Any:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.request_timeout,
            headers=self._headers(),
            transport=self._transport,
        ) as client:
            response = await client.request(method, path, json=payload)
            response.raise_for_status()
            envelope = response.json()
        if not isinstance(envelope, dict):
            raise PermanentMemMeError("invalid MemMe response")
        if envelope.get("success") is not True:
            raise PermanentMemMeError("MemMe response reported failure")
        if "data" not in envelope:
            raise PermanentMemMeError("MemMe response is missing data")
        return envelope["data"]

    def _events_payload(
        self, msgs, session_id: str, cutoff: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        messages = []
        excluded = {}
        for message in msgs:
            if getattr(message, "role", None) not in {"user", "assistant"}:
                continue
            if getattr(message, "is_temporary", False):
                continue
            if cutoff is not None and float(
                getattr(message, "created_at", 0.0) or 0.0
            ) <= cutoff:
                continue
            if getattr(message, "tool_calls", None):
                continue
            content = _message_text(getattr(message, "content", None))
            if content is None:
                continue
            message_id = str(getattr(message, "uniq_id", "")).strip()
            if not message_id:
                logger.bind(tag=TAG).warning("MemMe 忽略缺少稳定 ID 的消息")
                continue
            reason = exclude_reason(content)
            if reason is not None:
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            content = filter_for_long_term_memory(content)
            if content is None:
                continue
            messages.append(
                {
                    "event_id": f"{session_id}:{message_id}",
                    "role": message.role,
                    "content": content,
                }
            )
        if excluded:
            # 只记类别与数量，不落任何原文（合同 §8：错误正文不入队同理）
            summary = ", ".join(f"{k}×{v}" for k, v in sorted(excluded.items()))
            logger.bind(tag=TAG).info(f"MemMe 写入过滤排除消息：{summary}")
        if not messages:
            return None

        payload: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "app_id": self.app_id,
            "run_id": session_id,
            "messages": messages,
        }
        if self.include_device_id and self.device_id:
            payload["metadata"] = {"device_id": self.device_id}
        return payload

    def _sanitize_queued_events(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """旧队列也必须按当前规则重新过滤，不能信任磁盘里的原始 payload。"""
        required = ("session_id", "user_id", "agent_id", "app_id", "messages")
        if not all(payload.get(key) for key in required):
            raise PermanentMemMeError("invalid queued event scope")
        if not isinstance(payload["messages"], list):
            raise PermanentMemMeError("invalid queued event messages")
        safe_messages = []
        for message in payload["messages"]:
            if not isinstance(message, dict):
                continue
            if message.get("role") not in {"user", "assistant"}:
                continue
            event_id = str(message.get("event_id") or "").strip()
            content = filter_for_long_term_memory(message.get("content"))
            if event_id and content is not None:
                safe_messages.append(
                    {"event_id": event_id, "role": message["role"], "content": content}
                )
        sanitized = {
            key: payload[key]
            for key in ("session_id", "user_id", "agent_id", "app_id")
        }
        sanitized["run_id"] = str(payload.get("run_id") or payload["session_id"])
        sanitized["messages"] = safe_messages
        if self.include_device_id and isinstance(payload.get("metadata"), dict):
            device_id = payload["metadata"].get("device_id")
            if device_id:
                sanitized["metadata"] = {"device_id": str(device_id)}
        return sanitized

    @staticmethod
    def _validate_events_result(result: Any, expected_events: int) -> int:
        if not isinstance(result, dict):
            raise PermanentMemMeError("invalid MemMe events response")
        pending = result.get("embedding_pending")
        if isinstance(pending, bool) or not isinstance(pending, int) or pending < 0:
            raise PermanentMemMeError("invalid embedding_pending")
        acknowledged = 0
        for field in ("events_appended", "events_replayed"):
            value = result.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PermanentMemMeError(f"invalid {field}")
            acknowledged += value
        if acknowledged != expected_events:
            raise PermanentMemMeError("event acknowledgement count mismatch")
        return pending

    @staticmethod
    def _is_permanent_error(error: Exception) -> bool:
        if isinstance(error, (PermanentMemMeError, json.JSONDecodeError)):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            return 400 <= status < 500 and status not in {408, 429}
        return False

    async def _process_job(self, row: sqlite3.Row) -> Optional[str]:
        job_id = row["id"]
        kind = row["kind"]
        attempts = int(row["attempts"])
        try:
            payload = json.loads(row["payload"])
            if not isinstance(payload, dict):
                raise PermanentMemMeError("invalid queued payload")
            if kind == "events":
                payload = self._sanitize_queued_events(payload)
                cutoff = await asyncio.to_thread(
                    self._scope_cutoff,
                    str(payload["user_id"]),
                    str(payload["agent_id"]),
                    str(payload["app_id"]),
                )
                if cutoff is not None and float(row["created_at"]) <= cutoff:
                    return await asyncio.to_thread(self._finish_job, job_id)
                if await asyncio.to_thread(
                    self._is_scope_tombstoned,
                    str(payload["user_id"]),
                    str(payload["agent_id"]),
                    str(payload["app_id"]),
                ):
                    return await asyncio.to_thread(self._finish_job, job_id)
                await asyncio.to_thread(
                    self._update_claimed_payload, job_id, payload
                )
                if not payload["messages"]:
                    return await asyncio.to_thread(self._finish_job, job_id)
                result = await self._post_json("/v1/events", payload)
                pending = self._validate_events_result(
                    result, len(payload["messages"])
                )
                if pending:
                    await asyncio.to_thread(
                        self._mark_failed,
                        job_id,
                        attempts,
                        f"{pending} event embeddings are still pending",
                    )
                    return None
                follow_up = None
                if self.compact_on_save:
                    follow_up = (
                        "compact",
                        {
                            "session_id": payload["session_id"],
                            "user_id": payload["user_id"],
                            "agent_id": payload["agent_id"],
                            "app_id": payload["app_id"],
                        },
                    )
                return await asyncio.to_thread(self._finish_job, job_id, follow_up)
            if kind == "compact":
                required_scope = ("user_id", "agent_id", "app_id")
                if not all(payload.get(key) for key in required_scope):
                    raise PermanentMemMeError("unscoped compact job")
                cutoff = await asyncio.to_thread(
                    self._scope_cutoff,
                    str(payload["user_id"]),
                    str(payload["agent_id"]),
                    str(payload["app_id"]),
                )
                if cutoff is not None and float(row["created_at"]) <= cutoff:
                    return await asyncio.to_thread(self._finish_job, job_id)
                if await asyncio.to_thread(
                    self._is_scope_tombstoned,
                    str(payload["user_id"]),
                    str(payload["agent_id"]),
                    str(payload["app_id"]),
                ):
                    return await asyncio.to_thread(self._finish_job, job_id)
                session_id = quote(str(payload["session_id"]), safe="")
                await self._post_json(f"/v1/sessions/{session_id}/compact")
                await asyncio.to_thread(self._finish_job, job_id)
                return None
            await asyncio.to_thread(
                self._mark_dead, job_id, attempts, f"unknown job kind: {kind}"
            )
        except Exception as error:
            error_summary = self._error_summary(error)
            if self._is_permanent_error(error):
                await asyncio.to_thread(
                    self._mark_dead, job_id, attempts, error_summary
                )
                logger.bind(tag=TAG).error(
                    f"MemMe {kind} 永久失败，已转入死信: {error_summary}"
                )
            else:
                await asyncio.to_thread(
                    self._mark_failed, job_id, attempts, error_summary
                )
                logger.bind(tag=TAG).warning(
                    f"MemMe {kind} 暂时失败，已保留本地重试任务: {error_summary}"
                )
        return None

    async def _process_job_id(self, job_id: str) -> Optional[str]:
        row = await asyncio.to_thread(self._claim_job, job_id)
        if row is None:
            return None
        return await self._process_job(row)

    async def _drain_due_jobs(self, limit: int, exclude: Iterable[str] = ()) -> None:
        rows = await asyncio.to_thread(self._claim_due_jobs, limit, exclude)
        for row in rows:
            await self._process_job(row)

    async def enqueue_memory(self, msgs, session_id=None) -> Optional[str]:
        """只完成本地可靠入队；供用户消息在模型执行前快速落盘。"""
        if not self.use_memme:
            return None
        if not self._worker_only:
            self.ensure_global_worker()
        session_id = str(session_id or "").strip()
        if not session_id:
            logger.bind(tag=TAG).error("MemMe 拒绝保存：session_id 为空")
            return None
        if await asyncio.to_thread(
            self._is_scope_tombstoned, self.user_id, self.agent_id, self.app_id
        ):
            logger.bind(tag=TAG).warning("MemMe 已拒绝向删除过的数据范围继续写入")
            return None
        cutoff = await asyncio.to_thread(
            self._scope_cutoff, self.user_id, self.agent_id, self.app_id
        )
        payload = self._events_payload(msgs, session_id, cutoff=cutoff)
        if payload is None:
            return None

        try:
            return await asyncio.to_thread(self._enqueue, "events", payload)
        except Exception as error:
            logger.bind(tag=TAG).error(f"MemMe 本地入队失败: {error}")
            raise

    async def save_memory(self, msgs, session_id=None):
        job_id = await self.enqueue_memory(msgs, session_id)
        if job_id is None:
            return None

        async with self._drain_lock:
            follow_up_id = await self._process_job_id(job_id)
            if follow_up_id is not None:
                await self._process_job_id(follow_up_id)
            await self._drain_due_jobs(self.retry_batch_size, {job_id, follow_up_id})
        return {"queued_job_id": job_id}

    async def export_user_data(self, user_id: str) -> Any:
        user_id = str(user_id or "").strip()
        if not user_id:
            raise ValueError("user_id is required")
        return await self._post_json("/v1/data/export", {"user_id": user_id})

    async def delete_user_data(self, user_id: str, allow_future: bool = False) -> Any:
        user_id = str(user_id or "").strip()
        if not user_id:
            raise ValueError("user_id is required")
        # 先在本地阻止写回并清除待发任务。远端失败时保留 tombstone，
        # 防止家长已经要求删除后，旧对话又被自动上传。
        await asyncio.to_thread(
            self._tombstone_user_and_purge_queue, user_id, True
        )
        encoded_user_id = quote(user_id, safe="")
        result = await self._post_json(
            f"/v1/users/{encoded_user_id}",
            {"confirm_user_id": user_id},
            method="DELETE",
        )
        if allow_future:
            await asyncio.to_thread(self._allow_future_writes, user_id)
        return result

    async def query_memory(self, query: str) -> str:
        if not self.use_memme:
            return ""
        if not self._worker_only and await asyncio.to_thread(
            self._is_scope_tombstoned, self.user_id, self.agent_id, self.app_id
        ):
            return ""
        search_query = _message_text(query)
        if search_query is None:
            return ""
        # 对接合同 §7.1：召回查询使用脱敏文字，不把原始 PII 发给 MemMe
        search_query = redact_for_long_term_memory(search_query)
        payload = {
            "query": search_query,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "app_id": self.app_id,
            "limit": self.recall_limit,
        }
        try:
            data = await self._post_json("/v1/recall", payload)
        except Exception as error:
            logger.bind(tag=TAG).warning(
                f"MemMe 查询失败: {self._error_summary(error)}"
            )
            return ""

        lines = []
        if not isinstance(data, dict) or not isinstance(data.get("memories"), list):
            logger.bind(tag=TAG).warning("MemMe 查询失败: invalid response")
            return ""
        for entry in data.get("memories", []):
            if not isinstance(entry, dict):
                continue
            content = filter_recalled_memory(entry.get("content"))
            if content is None:
                continue
            updated_at = str(entry.get("updated_at", "")).strip()
            prefix = f"[{updated_at}] " if updated_at else ""
            lines.append(f"- {prefix}{content}")
        return "\n".join(lines)[: self.recall_max_chars]
