"""长期记忆写入过滤测试（对接合同 §9）。"""

import asyncio
import json

import httpx

from core.providers.memory.memme.memme import MemoryProvider
from core.safety.memory_filter import (
    exclude_reason,
    filter_for_long_term_memory,
    redact_for_long_term_memory,
)
from core.utils.dialogue import Message


# ---------- 纯函数 ----------

def test_redacts_common_pii():
    text = (
        "我妈妈电话13812345678，邮箱 child@example.com，"
        "验证码是482913，网址 https://example.com/x，"
        "身份证 110101201901011234，密钥 sk-abcdefghijklmnop"
    )
    result = redact_for_long_term_memory(text)
    for secret in (
        "13812345678", "child@example.com", "482913",
        "https://example.com/x", "110101201901011234", "sk-abcdefghijklmnop",
    ):
        assert secret not in result
    assert result.count("已隐藏") >= 5


def test_redacts_address_and_school_but_keeps_plain_words():
    result = redact_for_long_term_memory("我家住在幸福路12号3栋2单元501室")
    assert "幸福路12号" not in result
    assert "501" not in result

    result = redact_for_long_term_memory("我在阳光幼儿园上学，喜欢实验小学的老师")
    assert "阳光幼儿园" not in result
    assert "实验小学" not in result
    assert "上学" in result  # 普通词不被误伤

    result = redact_for_long_term_memory("我在三年级二班有好多朋友")
    assert "三年级二班" not in result
    assert "有好多朋友" in result


def test_normal_child_talk_passes_unchanged():
    text = "我最喜欢蓝色，还喜欢听小猫咪的故事"
    assert redact_for_long_term_memory(text) == text


def test_danger_medical_adult_excluded_entirely():
    assert exclude_reason("我不想活了") == "danger"
    assert exclude_reason("有人拍我裸照") == "danger"
    assert exclude_reason("我今天发烧了不想吃饭") == "medical"
    assert exclude_reason("下周要做手术") == "medical"
    assert filter_for_long_term_memory("我不想活了") is None
    assert filter_for_long_term_memory("我喜欢画画") == "我喜欢画画"


def test_filter_redacts_before_returning():
    result = filter_for_long_term_memory("妈妈电话13812345678，她晚上回家")
    assert "13812345678" not in result
    assert "她晚上回家" in result


# ---------- Provider 集成 ----------

def _provider(tmp_path, **overrides):
    config = {
        "base_url": "http://memme.test",
        "api_key": "test-token",
        "user_id": "xiaozhi-user-7",
        "agent_id": "xiaozhi-agent-1",
        "app_id": "xiaozhi",
        "queue_path": str(tmp_path / "memme-retry.sqlite3"),
        "compact_on_save": False,
        "retry_batch_size": 0,
    }
    config.update(overrides)
    return MemoryProvider(config)


def test_provider_filters_messages_before_write(tmp_path):
    captured = []

    def ok_transport(request):
        captured.append(request)
        return httpx.Response(
            200, json={"success": True, "data": {"events_replayed": 0, "embedding_pending": 0}}
        )

    provider = _provider(tmp_path)
    provider._transport = httpx.MockTransport(ok_transport)
    messages = [
        Message("user", "妈妈电话13812345678晚上到家", uniq_id="u1"),
        Message("user", "我不想活了", uniq_id="u2"),
        Message("user", "我最喜欢蓝色", uniq_id="u3"),
        Message("assistant", "好的，我记住你喜欢蓝色啦", uniq_id="a1"),
    ]

    asyncio.run(provider.save_memory(messages, "session-1"))

    assert len(captured) == 1
    payload = json.loads(captured[0].content)
    contents = {m["event_id"]: m["content"] for m in payload["messages"]}
    assert "13812345678" not in contents["session-1:u1"]
    assert "晚上到家" in contents["session-1:u1"]
    assert "session-1:u2" not in contents  # danger 整条排除
    assert contents["session-1:u3"] == "我最喜欢蓝色"
    assert provider._pending_job_count() == 0


def test_provider_all_excluded_writes_nothing(tmp_path):
    captured = []

    def ok_transport(request):
        captured.append(request)
        return httpx.Response(
            200, json={"success": True, "data": {"events_replayed": 0, "embedding_pending": 0}}
        )

    provider = _provider(tmp_path)
    provider._transport = httpx.MockTransport(ok_transport)
    messages = [Message("user", "我今天发烧了", uniq_id="u1")]

    asyncio.run(provider.save_memory(messages, "session-1"))

    assert captured == []
    assert provider._pending_job_count() == 0


def test_provider_redacts_recall_query(tmp_path):
    captured = []

    def ok_transport(request):
        captured.append(request)
        return httpx.Response(
            200, json={"success": True, "data": {"memories": []}}
        )

    provider = _provider(tmp_path)
    provider._transport = httpx.MockTransport(ok_transport)

    asyncio.run(provider.query_memory("妈妈电话13812345678叫什么名字"))

    payload = json.loads(captured[0].content)
    assert "13812345678" not in payload["query"]
    assert "叫什么名字" in payload["query"]


def test_provider_filter_can_be_disabled_for_tests(tmp_path):
    captured = []

    def ok_transport(request):
        captured.append(request)
        return httpx.Response(
            200, json={"success": True, "data": {"events_replayed": 0, "embedding_pending": 0}}
        )

    provider = _provider(tmp_path, write_filter=False)
    provider._transport = httpx.MockTransport(ok_transport)
    messages = [Message("user", "妈妈电话13812345678", uniq_id="u1")]

    asyncio.run(provider.save_memory(messages, "session-1"))

    payload = json.loads(captured[0].content)
    assert "13812345678" in payload["messages"][0]["content"]
