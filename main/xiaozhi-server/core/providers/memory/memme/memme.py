import asyncio
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urlparse

import httpx

from ..base import MemoryProviderBase, logger

TAG = __name__


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

    def __init__(self, config: Dict[str, Any], summary_memory=None):
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
        self.recall_limit = max(1, min(int(config.get("recall_limit", 5)), 50))
        self.recall_max_chars = max(
            256, min(int(config.get("recall_max_chars", 4000)), 32000)
        )
        self.queue_max_jobs = max(1, int(config.get("queue_max_jobs", 10000)))
        self.queue_max_bytes = max(1024, int(config.get("queue_max_bytes", 268435456)))
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
        queue_path = os.path.expandvars(
            str(config.get("queue_path", "data/memme-retry.sqlite3"))
        )
        self.queue_path = Path(queue_path).expanduser().resolve()
        self.device_id = None
        self._transport = None
        self._drain_lock = asyncio.Lock()

        parsed_url = urlparse(self.base_url)
        missing = []
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            missing.append("base_url")
        for key, value in (
            ("user_id", self.user_id),
            ("agent_id", self.agent_id),
            ("app_id", self.app_id),
        ):
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

    def init_memory(self, role_id, llm, **kwargs):
        # role_id is currently the device MAC for older providers. MemMe deliberately
        # uses the stable IDs from its own config instead.
        super().init_memory(role_id, llm, **kwargs)
        self.device_id = kwargs.get("device_id") or role_id

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
                    last_error TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memme_jobs_due "
                "ON memme_jobs(next_attempt_at, created_at)"
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
                "SELECT 1 FROM memme_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if existing is not None:
                return job_id
            count = connection.execute("SELECT COUNT(*) FROM memme_jobs").fetchone()[0]
            if count >= self.queue_max_jobs:
                raise RuntimeError(
                    f"MemMe retry queue is full ({self.queue_max_jobs} jobs)"
                )
            queued_bytes = connection.execute(
                "SELECT COALESCE(SUM(length(CAST(payload AS BLOB))), 0) FROM memme_jobs"
            ).fetchone()[0]
            if queued_bytes + payload_bytes > self.queue_max_bytes:
                raise RuntimeError(
                    f"MemMe retry queue exceeds {self.queue_max_bytes} bytes"
                )
            connection.execute(
                """
                INSERT INTO memme_jobs(
                    id, kind, payload, attempts, next_attempt_at, created_at
                ) VALUES (?, ?, ?, 0, ?, ?)
                """,
                (job_id, kind, serialized, now, now),
            )
        return job_id

    def _get_job(self, job_id: str) -> Optional[sqlite3.Row]:
        with self._connect_queue() as connection:
            return connection.execute(
                "SELECT * FROM memme_jobs WHERE id = ?", (job_id,)
            ).fetchone()

    def _due_jobs(self, limit: int, exclude: Iterable[str] = ()) -> List[sqlite3.Row]:
        if limit <= 0:
            return []
        excluded = [job_id for job_id in exclude if job_id]
        placeholders = ",".join("?" for _ in excluded)
        exclusion = f"AND id NOT IN ({placeholders})" if excluded else ""
        with self._connect_queue() as connection:
            return connection.execute(
                f"""
                SELECT * FROM memme_jobs
                WHERE next_attempt_at <= ? {exclusion}
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (time.time(), *excluded, limit),
            ).fetchall()

    def _pending_job_count(self) -> int:
        with self._connect_queue() as connection:
            return int(
                connection.execute("SELECT COUNT(*) FROM memme_jobs").fetchone()[0]
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
                SET attempts = ?, next_attempt_at = ?, last_error = ?
                WHERE id = ?
                """,
                (attempts + 1, time.time() + delay, error[:500], job_id),
            )

    def _finish_job(
        self,
        job_id: str,
        follow_up: Optional[tuple[str, Dict[str, Any]]] = None,
    ) -> Optional[str]:
        follow_up_id = None
        with self._connect_queue() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM memme_jobs WHERE id = ?", (job_id,))
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
                        id, kind, payload, attempts, next_attempt_at, created_at
                    ) VALUES (?, ?, ?, 0, ?, ?)
                    """,
                    (follow_up_id, kind, serialized, now, now),
                )
        return follow_up_id

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _post_json(
        self, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Any:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.request_timeout,
            headers=self._headers(),
            transport=self._transport,
        ) as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            envelope = response.json()
        if not isinstance(envelope, dict):
            raise RuntimeError("invalid MemMe response")
        if envelope.get("success") is not True:
            error = envelope.get("error", "invalid MemMe response")
            raise RuntimeError(str(error))
        return envelope.get("data")

    def _events_payload(self, msgs, session_id: str) -> Optional[Dict[str, Any]]:
        messages = []
        for message in msgs:
            if getattr(message, "role", None) not in {"user", "assistant"}:
                continue
            content = _message_text(getattr(message, "content", None))
            if content is None:
                continue
            message_id = str(getattr(message, "uniq_id", "")).strip()
            if not message_id:
                logger.bind(tag=TAG).warning("MemMe 忽略缺少稳定 ID 的消息")
                continue
            messages.append(
                {
                    "event_id": f"{session_id}:{message_id}",
                    "role": message.role,
                    "content": content,
                }
            )
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

    async def _process_job(self, row: sqlite3.Row) -> Optional[str]:
        job_id = row["id"]
        kind = row["kind"]
        attempts = int(row["attempts"])
        payload = json.loads(row["payload"])
        try:
            if kind == "events":
                result = await self._post_json("/v1/events", payload)
                pending = int((result or {}).get("embedding_pending", 0))
                if pending:
                    self._mark_failed(
                        job_id,
                        attempts,
                        f"{pending} event embeddings are still pending",
                    )
                    return None
                follow_up = None
                if self.compact_on_save:
                    follow_up = ("compact", {"session_id": payload["session_id"]})
                return self._finish_job(job_id, follow_up)
            if kind == "compact":
                session_id = quote(str(payload["session_id"]), safe="")
                await self._post_json(f"/v1/sessions/{session_id}/compact")
                self._finish_job(job_id)
                return None
            self._mark_failed(job_id, attempts, f"unknown job kind: {kind}")
        except Exception as error:
            error_summary = self._error_summary(error)
            self._mark_failed(job_id, attempts, error_summary)
            logger.bind(tag=TAG).warning(
                f"MemMe {kind} 暂时失败，已保留本地重试任务: {error_summary}"
            )
        return None

    async def _process_job_id(self, job_id: str) -> Optional[str]:
        row = await asyncio.to_thread(self._get_job, job_id)
        if row is None:
            return None
        return await self._process_job(row)

    async def _drain_due_jobs(self, limit: int, exclude: Iterable[str] = ()) -> None:
        rows = await asyncio.to_thread(self._due_jobs, limit, exclude)
        for row in rows:
            await self._process_job(row)

    async def save_memory(self, msgs, session_id=None):
        if not self.use_memme:
            return None
        session_id = str(session_id or "").strip()
        if not session_id:
            logger.bind(tag=TAG).error("MemMe 拒绝保存：session_id 为空")
            return None
        payload = self._events_payload(msgs, session_id)
        if payload is None:
            return None

        try:
            job_id = await asyncio.to_thread(self._enqueue, "events", payload)
        except Exception as error:
            logger.bind(tag=TAG).error(f"MemMe 本地入队失败: {error}")
            raise

        async with self._drain_lock:
            follow_up_id = await self._process_job_id(job_id)
            if follow_up_id is not None:
                await self._process_job_id(follow_up_id)
            await self._drain_due_jobs(self.retry_batch_size, {job_id, follow_up_id})
        return {"queued_job_id": job_id}

    async def query_memory(self, query: str) -> str:
        if not self.use_memme:
            return ""
        search_query = _message_text(query)
        if search_query is None:
            return ""
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
        if not isinstance(data, dict):
            logger.bind(tag=TAG).warning("MemMe 查询失败: invalid response")
            return ""
        for entry in data.get("memories", []):
            if not isinstance(entry, dict):
                continue
            content = _message_text(entry.get("content"))
            if content is None:
                continue
            updated_at = str(entry.get("updated_at", "")).strip()
            prefix = f"[{updated_at}] " if updated_at else ""
            lines.append(f"- {prefix}{content}")
        return "\n".join(lines)[: self.recall_max_chars]
