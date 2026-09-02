import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest

from core.providers.memory.memme.memme import MemoryProvider
from core.utils.dialogue import Message


def _config(tmp_path: Path, **overrides):
    config = {
        "base_url": "http://memme.test",
        "api_key": "test-token",
        "user_id": "family-1",
        "agent_id": "pet-1",
        "app_id": "xiaozhi",
        "queue_path": str(tmp_path / "memme-retry.sqlite3"),
        "compact_on_save": False,
        "retry_batch_size": 0,
    }
    config.update(overrides)
    return config


def test_failed_write_stays_in_queue_and_replays_with_stable_scope(tmp_path):
    requests = []

    def unavailable(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "success": False,
                "error": "server-secret-that-must-not-persist",
            },
        )

    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(unavailable)
    provider.init_memory("device-mac", None, device_id="device-mac")
    messages = [
        Message("system", "system prompt", uniq_id="system-1"),
        Message("user", '{"content":"我喜欢蓝色。"}', uniq_id="user-1"),
        Message("tool", "private tool output", uniq_id="tool-1"),
        Message("assistant", "我记住了。", uniq_id="assistant-1"),
    ]

    asyncio.run(provider.save_memory(messages, "session-1"))

    assert provider._pending_job_count() == 1
    assert b"test-token" not in provider.queue_path.read_bytes()
    assert (
        b"server-secret-that-must-not-persist" not in provider.queue_path.read_bytes()
    )
    if os.name == "posix":
        assert provider.queue_path.stat().st_mode & 0o777 == 0o600
    payload = json.loads(requests[0].content)
    assert payload["user_id"] == "family-1"
    assert payload["agent_id"] == "pet-1"
    assert payload["app_id"] == "xiaozhi"
    assert payload["run_id"] == "session-1"
    assert "metadata" not in payload
    assert payload["messages"] == [
        {
            "event_id": "session-1:user-1",
            "role": "user",
            "content": "我喜欢蓝色。",
        },
        {
            "event_id": "session-1:assistant-1",
            "role": "assistant",
            "content": "我记住了。",
        },
    ]
    assert requests[0].headers["authorization"] == "Bearer test-token"

    def recovered(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {"events_replayed": 2, "embedding_pending": 0},
            },
        )

    restarted = MemoryProvider(_config(tmp_path))
    restarted._transport = httpx.MockTransport(recovered)
    asyncio.run(restarted.save_memory(messages, "session-1"))

    assert restarted._pending_job_count() == 0


def test_embedding_pending_keeps_exact_event_job_for_backfill(tmp_path):
    responses = [1, 0]

    def handler(request):
        pending = responses.pop(0)
        return httpx.Response(
            200,
            json={"success": True, "data": {"embedding_pending": pending}},
        )

    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(handler)
    messages = [Message("user", "需要补写向量", uniq_id="event-1")]

    asyncio.run(provider.save_memory(messages, "session-2"))
    assert provider._pending_job_count() == 1

    asyncio.run(provider.save_memory(messages, "session-2"))
    assert provider._pending_job_count() == 0


def test_successful_write_compacts_and_recall_omits_run_scope(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/v1/events":
            return httpx.Response(
                200,
                json={"success": True, "data": {"embedding_pending": 0}},
            )
        if request.url.path == "/v1/sessions/session-3/compact":
            return httpx.Response(200, json={"success": True, "data": {}})
        if request.url.path == "/v1/recall":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "memories": [
                            {
                                "content": "喜欢蓝色玩具",
                                "updated_at": "2026-09-02T10:00:00Z",
                            }
                        ]
                    },
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    provider = MemoryProvider(_config(tmp_path, compact_on_save=True))
    provider._transport = httpx.MockTransport(handler)
    messages = [Message("user", "我喜欢蓝色玩具", uniq_id="event-3")]

    asyncio.run(provider.save_memory(messages, "session-3"))
    recalled = asyncio.run(provider.query_memory('{"content":"喜欢什么玩具？"}'))

    assert [request.url.path for request in requests] == [
        "/v1/events",
        "/v1/sessions/session-3/compact",
        "/v1/recall",
    ]
    recall_payload = json.loads(requests[-1].content)
    assert recall_payload == {
        "query": "喜欢什么玩具？",
        "user_id": "family-1",
        "agent_id": "pet-1",
        "app_id": "xiaozhi",
        "limit": 5,
    }
    assert "喜欢蓝色玩具" in recalled
    assert provider._pending_job_count() == 0


def test_missing_stable_identity_disables_provider(tmp_path):
    provider = MemoryProvider(_config(tmp_path, user_id="", agent_id=""))

    assert provider.use_memme is False
    assert asyncio.run(provider.query_memory("不会发送")) == ""


def test_retry_queue_has_a_total_byte_limit(tmp_path):
    provider = MemoryProvider(_config(tmp_path, queue_max_bytes=1024))
    provider._transport = httpx.MockTransport(
        lambda request: httpx.Response(503, json={"success": False, "error": "offline"})
    )
    messages = [Message("user", "大" * 2000, uniq_id="large-event")]

    with pytest.raises(RuntimeError, match="retry queue exceeds"):
        asyncio.run(provider.save_memory(messages, "large-session"))

    assert provider._pending_job_count() == 0
