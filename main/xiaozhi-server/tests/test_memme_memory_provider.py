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
        "base_url": "http://127.0.0.1:8080",
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
            503,
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
                "data": {
                    "events_appended": 0,
                    "events_replayed": 2,
                    "embedding_pending": 0,
                },
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
            json={
                "success": True,
                "data": {
                    "events_appended": 0,
                    "events_replayed": 1,
                    "embedding_pending": pending,
                },
            },
        )

    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(handler)
    messages = [Message("user", "需要补写向量", uniq_id="event-1")]

    asyncio.run(provider.save_memory(messages, "session-2"))
    assert provider._pending_job_count() == 1

    asyncio.run(provider.save_memory(messages, "session-2"))
    assert provider._pending_job_count() == 0


def test_enqueue_memory_is_durable_without_waiting_for_network(tmp_path):
    calls = []
    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(lambda request: calls.append(request))

    job_id = asyncio.run(
        provider.enqueue_memory(
            [Message("user", "先把这句话保存", uniq_id="early-user")],
            "early-session",
        )
    )

    assert job_id is not None
    assert calls == []
    assert provider._pending_job_count() == 1


def test_successful_write_compacts_and_recall_omits_run_scope(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/v1/events":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "events_appended": 1,
                        "events_replayed": 0,
                        "embedding_pending": 0,
                    },
                },
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


def test_temporary_and_tool_call_messages_never_enter_events(tmp_path):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "events_appended": 1,
                    "events_replayed": 0,
                    "embedding_pending": 0,
                },
            },
        )

    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(handler)
    messages = [
        Message("user", "给我讲个故事吧", uniq_id="fake-u", is_temporary=True),
        Message(
            "assistant",
            "不应保存",
            uniq_id="fake-a",
            tool_calls=[{"id": "tool-1"}],
            is_temporary=True,
        ),
        Message("user", "我喜欢蓝色", uniq_id="real-u"),
    ]

    asyncio.run(provider.save_memory(messages, "temporary-session"))

    assert [item["event_id"] for item in captured[0]["messages"]] == [
        "temporary-session:real-u"
    ]


def test_legacy_queue_payload_is_refiltered_before_upload(tmp_path):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "events_appended": 0,
                    "events_replayed": 1,
                    "embedding_pending": 0,
                },
            },
        )

    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(handler)
    provider._enqueue(
        "events",
        {
            "session_id": "legacy-session",
            "user_id": "family-1",
            "agent_id": "pet-1",
            "app_id": "xiaozhi",
            "messages": [
                {
                    "event_id": "legacy-session:u1",
                    "role": "user",
                    "content": "我家WiFi密码是abc12345",
                }
            ],
        },
    )

    asyncio.run(provider._drain_due_jobs(1))

    assert "abc12345" not in captured[0]["messages"][0]["content"]
    assert provider._pending_job_count() == 0


def test_two_providers_claim_one_job_only_once(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "events_appended": 0,
                    "events_replayed": 1,
                    "embedding_pending": 0,
                },
            },
        )

    first = MemoryProvider(_config(tmp_path))
    second = MemoryProvider(_config(tmp_path))
    transport = httpx.MockTransport(handler)
    first._transport = transport
    second._transport = transport
    first._enqueue(
        "events",
        {
            "session_id": "claim-session",
            "user_id": "family-1",
            "agent_id": "pet-1",
            "app_id": "xiaozhi",
            "messages": [
                {"event_id": "claim-session:u1", "role": "user", "content": "你好"}
            ],
        },
    )

    async def drain_both():
        await asyncio.gather(
            first._drain_due_jobs(1), second._drain_due_jobs(1)
        )

    asyncio.run(drain_both())

    assert calls == ["/v1/events"]
    assert first._pending_job_count() == 0


def test_background_worker_recovers_without_new_save(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "events_appended": 0,
                    "events_replayed": 1,
                    "embedding_pending": 0,
                },
            },
        )

    worker = MemoryProvider(
        _config(tmp_path, retry_poll_seconds=0.01), worker_only=True
    )
    worker._transport = httpx.MockTransport(handler)
    worker._enqueue(
        "events",
        {
            "session_id": "recover-session",
            "user_id": "family-1",
            "agent_id": "pet-1",
            "app_id": "xiaozhi",
            "messages": [
                {"event_id": "recover-session:u1", "role": "user", "content": "你好"}
            ],
        },
    )

    async def run_worker():
        worker.start_background_worker()
        await asyncio.sleep(0.08)
        await worker.close()

    asyncio.run(run_worker())

    assert calls == ["/v1/events"]
    assert worker._pending_job_count() == 0


def test_global_worker_keeps_retrying_independent_of_connection(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "events_appended": 0,
                    "events_replayed": 1,
                    "embedding_pending": 0,
                },
            },
        )

    async def run_global_worker():
        await MemoryProvider.close_global_workers()
        worker = MemoryProvider(
            _config(
                tmp_path,
                retry_batch_size=1,
                retry_poll_seconds=0.01,
            ),
            worker_only=True,
        )
        worker._transport = httpx.MockTransport(handler)
        worker._enqueue(
            "events",
            {
                "session_id": "global-session",
                "user_id": "family-1",
                "agent_id": "pet-1",
                "app_id": "xiaozhi",
                "messages": [
                    {
                        "event_id": "global-session:u1",
                        "role": "user",
                        "content": "你好",
                    }
                ],
            },
        )
        worker.ensure_global_worker()
        await asyncio.sleep(0.08)
        await MemoryProvider.close_global_workers()
        return worker

    worker = asyncio.run(run_global_worker())

    assert calls == ["/v1/events"]
    assert worker._pending_job_count() == 0


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"success": False, "error": "unauthorized"}),
        httpx.Response(200, json={"success": True, "data": {}}),
    ],
)
def test_permanent_or_invalid_response_moves_job_to_dead_letter(tmp_path, response):
    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(lambda request: response)

    asyncio.run(
        provider.save_memory(
            [Message("user", "我喜欢蓝色", uniq_id="u1")], "dead-session"
        )
    )

    assert provider._pending_job_count() == 0
    assert provider._dead_job_count() == 1


def test_missing_key_or_non_loopback_url_disables_provider(tmp_path):
    missing_key = MemoryProvider(_config(tmp_path, api_key=""))
    remote = MemoryProvider(_config(tmp_path, base_url="https://memme.example.com"))

    assert missing_key.use_memme is False
    assert remote.use_memme is False


def test_user_delete_purges_queue_and_blocks_future_writeback(tmp_path):
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(
            200, json={"success": True, "data": {"deleted": True}}
        )

    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(handler)
    provider._enqueue(
        "events",
        {
            "session_id": "delete-session",
            "user_id": "family-1",
            "agent_id": "pet-1",
            "app_id": "xiaozhi",
            "messages": [
                {"event_id": "delete-session:u1", "role": "user", "content": "你好"}
            ],
        },
    )
    provider._enqueue(
        "compact",
        {
            "session_id": "delete-session",
            "user_id": "family-1",
            "agent_id": "pet-1",
            "app_id": "xiaozhi",
        },
    )

    result = asyncio.run(provider.delete_user_data("family-1"))

    assert result == {"deleted": True}
    assert provider._pending_job_count() == 0
    assert requests == [("DELETE", "/v1/users/family-1")]

    asyncio.run(
        provider.save_memory(
            [Message("user", "我喜欢紫色", uniq_id="after-delete")],
            "after-delete-session",
        )
    )
    assert requests == [("DELETE", "/v1/users/family-1")]
    assert asyncio.run(provider.query_memory("喜欢什么")) == ""


def test_legacy_unscoped_compact_job_is_not_sent(tmp_path):
    calls = []
    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(lambda request: calls.append(request))
    provider._enqueue("compact", {"session_id": "legacy-session"})

    asyncio.run(provider._drain_due_jobs(1))

    assert calls == []
    assert provider._pending_job_count() == 0
    assert provider._dead_job_count() == 1


def test_parent_clear_drops_old_snapshot_but_allows_new_memories(tmp_path):
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(
                200, json={"success": True, "data": {"deleted": True}}
            )
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "events_appended": len(payload["messages"]),
                    "events_replayed": 0,
                    "embedding_pending": 0,
                },
            },
        )

    provider = MemoryProvider(_config(tmp_path))
    provider._transport = httpx.MockTransport(handler)
    old_message = Message(
        "user", "清空前的旧内容", uniq_id="old-message", created_at=1
    )

    asyncio.run(provider.delete_user_data("family-1", allow_future=True))
    asyncio.run(provider.save_memory([old_message], "old-snapshot"))
    asyncio.run(
        provider.save_memory(
            [Message("user", "清空后的新内容", uniq_id="new-message")],
            "new-session",
        )
    )

    assert requests == [
        ("DELETE", "/v1/users/family-1"),
        ("POST", "/v1/events"),
    ]
    assert provider._pending_job_count() == 0
