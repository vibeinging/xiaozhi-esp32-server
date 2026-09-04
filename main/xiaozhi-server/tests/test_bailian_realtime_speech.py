import asyncio
import json
import threading
import unittest

import websockets

from core.providers.asr.qwen3_asr_realtime import ASRProvider
from core.providers.bailian_realtime import build_realtime_ws_url
from core.providers.tts.qwen3_tts_realtime import TTSProvider


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(json.loads(message))


class ClosedWebSocket:
    async def recv(self):
        raise websockets.ConnectionClosed(None, None)


class BailianRealtimeUrlTest(unittest.TestCase):
    def test_dedicated_workspace_host_is_preserved(self):
        url = build_realtime_ws_url(
            "https://llm-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            "qwen3-asr-flash-realtime",
        )
        self.assertEqual(
            url,
            "wss://llm-example.cn-beijing.maas.aliyuncs.com/"
            "api-ws/v1/realtime?model=qwen3-asr-flash-realtime",
        )

    def test_explicit_ws_url_keeps_other_query_parameters(self):
        url = build_realtime_ws_url(
            None,
            "new-model",
            "wss://example.test/realtime?workspace=one&model=old-model",
        )
        self.assertEqual(
            url,
            "wss://example.test/realtime?workspace=one&model=new-model",
        )


class BailianRealtimeAsrTest(unittest.IsolatedAsyncioTestCase):
    async def test_commit_is_sent_once_and_finish_is_not_sent_early(self):
        provider = ASRProvider(
            {
                "api_key": "test-key",
                "base_url": "https://example.test/compatible-mode/v1",
            },
            True,
        )
        provider.asr_ws = FakeWebSocket()
        provider.server_ready = True

        await provider._send_stop_request()
        await provider._send_stop_request()

        self.assertEqual(
            [message["type"] for message in provider.asr_ws.messages],
            ["input_audio_buffer.commit"],
        )
        self.assertIsNotNone(provider._commit_deadline)

    async def test_audio_is_not_buffered_after_commit(self):
        provider = ASRProvider(
            {
                "api_key": "test-key",
                "base_url": "https://example.test/compatible-mode/v1",
            },
            True,
        )
        provider.input_committed = True

        class Conn:
            asr_audio = [b"before"]

        conn = Conn()
        await provider.receive_audio(conn, b"after", True)

        self.assertEqual(conn.asr_audio, [b"before"])

    async def test_audio_buffer_is_bounded(self):
        provider = ASRProvider(
            {
                "api_key": "test-key",
                "base_url": "https://example.test/compatible-mode/v1",
                "sample_rate": 10,
                "max_buffer_seconds": 1,
            },
            True,
        )

        class Conn:
            asr_audio = [b"a" * 12, b"b" * 12]

        conn = Conn()
        provider._trim_audio_buffer(conn)

        self.assertEqual(conn.asr_audio, [b"b" * 12])

    async def test_final_result_deadline_stops_waiting(self):
        provider = ASRProvider(
            {
                "api_key": "test-key",
                "base_url": "https://example.test/compatible-mode/v1",
            },
            True,
        )
        provider.asr_ws = FakeWebSocket()
        provider.input_committed = True
        provider._commit_deadline = 0

        with self.assertRaises(asyncio.TimeoutError):
            await provider._recv_result_event()


class BailianRealtimeTtsTest(unittest.IsolatedAsyncioTestCase):
    def make_provider(self):
        return TTSProvider(
            {
                "api_key": "test-key",
                "base_url": "https://example.test/compatible-mode/v1",
                "max_segment_chars": 6,
            },
            True,
        )

    async def test_text_is_committed_as_append_then_commit(self):
        provider = self.make_provider()
        provider.ws = FakeWebSocket()

        await provider._commit_text("你好呀。")

        self.assertEqual(
            [message["type"] for message in provider.ws.messages],
            ["input_text_buffer.append", "input_text_buffer.commit"],
        )
        self.assertEqual(provider._pending_responses, 1)

    async def test_closed_connection_ends_pending_audio_wait_immediately(self):
        provider = self.make_provider()
        provider.ws = ClosedWebSocket()
        provider.conn = type("Conn", (), {"stop_event": threading.Event()})()
        provider._pending_responses = 1
        provider._responses_done.clear()

        await provider._monitor_response()

        self.assertTrue(provider._responses_done.is_set())
        self.assertIn("connection closed", provider._response_error)

    async def test_first_comma_starts_audio_segment_without_waiting_for_full_reply(
        self,
    ):
        provider = self.make_provider()
        provider._text_buffer = "你好呀，我是小布。"

        first = provider._drain_text_segments(force=False)
        second = provider._drain_text_segments(force=True)

        self.assertEqual(first, ["你好呀，", "我是小布。"])
        self.assertEqual(second, [])

    async def test_cat_meow_uses_configured_probability_for_normal_reply(self):
        provider = self.make_provider()
        provider.cat_meow_enabled = True
        provider.cat_meow_probability = 0.5
        provider._user_text = "陪我猜小动物吧。"
        provider._response_text = "轻松回答。"

        provider._random = lambda: 0.49
        self.assertTrue(provider._should_append_cat_meow())

        provider._random = lambda: 0.5
        self.assertFalse(provider._should_append_cat_meow())

    async def test_cat_meow_is_skipped_for_safety_reply_without_advancing_counter(self):
        provider = self.make_provider()
        provider.cat_meow_enabled = True
        provider.cat_meow_probability = 1.0
        provider._random = lambda: 0.0
        provider._user_text = "插座好像漏电了。"
        provider._response_text = "马上离开并告诉身边的大人。"

        self.assertFalse(provider._should_append_cat_meow())

    async def test_cat_meow_is_skipped_for_fixed_child_safety_handoff(self):
        provider = self.make_provider()
        provider.cat_meow_enabled = True
        provider.cat_meow_probability = 1.0
        provider._random = lambda: 0.0
        provider._user_text = "[儿童安全事件:abuse_or_bullying]"
        provider._response_text = "这不是你的错，请现在就告诉可信任的大人。"

        self.assertFalse(provider._should_append_cat_meow())

    async def test_existing_meow_resets_counter_without_duplicate(self):
        provider = self.make_provider()
        provider.cat_meow_enabled = True
        provider.cat_meow_probability = 1.0
        provider._random = lambda: 0.0
        provider._user_text = "今天真开心。"
        provider._response_text = "我也很开心，喵～喵～"

        self.assertFalse(provider._should_append_cat_meow())

    async def test_meow_suffix_can_be_removed_from_safety_reply(self):
        provider = self.make_provider()

        cleaned = provider.CAT_MEOW_PATTERN.sub("", "马上离开插座。喵～喵～")

        self.assertEqual(cleaned, "马上离开插座。")


if __name__ == "__main__":
    unittest.main()
