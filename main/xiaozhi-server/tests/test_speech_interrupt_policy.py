import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.handle.receiveAudioHandle import is_wakeup_word, startToChat
from core.providers.asr.base import ASRProviderBase


class _Logger:
    def bind(self, **_kwargs):
        return self

    def info(self, *_args, **_kwargs):
        return None


class _FakeConnection:
    def __init__(self):
        self.config = {"wakeup_words": ["小草莓"]}
        self.introduced_speakers = set()
        self.current_speaker = None
        self.need_bind = False
        self.max_output_size = 0
        self.client_is_speaking = True
        self.client_listen_mode = "realtime"
        self.just_woken_up = False
        self.logger = _Logger()


class _StubAsr(ASRProviderBase):
    def __init__(self, text):
        super().__init__()
        self.text = text

    async def speech_to_text_wrapper(self, _pcm_data, _session_id):
        return self.text, None

    async def speech_to_text(self, _opus_data, _session_id, _artifacts=None):
        return self.text, None


class SpeechInterruptPolicyTest(unittest.IsolatedAsyncioTestCase):
    def test_wakeup_word_ignores_punctuation(self):
        connection = _FakeConnection()
        self.assertTrue(is_wakeup_word(connection, "小草莓！"))
        self.assertFalse(is_wakeup_word(connection, "我也想说话"))

    async def test_ordinary_speech_does_not_interrupt_playback(self):
        connection = _FakeConnection()

        with (
            patch(
                "core.handle.receiveAudioHandle.handleAbortMessage",
                new=AsyncMock(),
            ) as abort,
            patch(
                "core.handle.receiveAudioHandle.send_stt_message",
                new=AsyncMock(),
            ) as send_stt,
        ):
            await startToChat(
                connection,
                "我也想说话",
                input_started_while_speaking=True,
            )

        abort.assert_not_awaited()
        send_stt.assert_not_awaited()
        self.assertFalse(connection.just_woken_up)

    async def test_only_wakeup_word_interrupts_playback(self):
        connection = _FakeConnection()

        with (
            patch(
                "core.handle.receiveAudioHandle.handleAbortMessage",
                new=AsyncMock(),
            ) as abort,
            patch(
                "core.handle.receiveAudioHandle.send_stt_message",
                new=AsyncMock(),
            ) as send_stt,
        ):
            await startToChat(
                connection,
                "小草莓！",
                input_started_while_speaking=True,
            )

        abort.assert_awaited_once_with(connection)
        send_stt.assert_awaited_once_with(connection, "小草莓！")
        self.assertTrue(connection.just_woken_up)

    async def test_speech_that_began_during_playback_stays_ignored(self):
        connection = _FakeConnection()
        connection.client_is_speaking = False

        with (
            patch(
                "core.handle.receiveAudioHandle.handleAbortMessage",
                new=AsyncMock(),
            ) as abort,
            patch(
                "core.handle.receiveAudioHandle.send_stt_message",
                new=AsyncMock(),
            ) as send_stt,
        ):
            await startToChat(
                connection,
                "刚才那句话",
                input_started_while_speaking=True,
            )

        abort.assert_not_awaited()
        send_stt.assert_not_awaited()

    async def test_ignored_overlap_is_not_written_to_chat_report(self):
        connection = SimpleNamespace(
            asr_started_while_speaking=True,
            client_is_speaking=False,
            voiceprint_provider=None,
            session_id="test-session",
            config={"wakeup_words": ["小草莓"]},
        )
        provider = _StubAsr("普通插话")

        with (
            patch(
                "core.providers.asr.base.enqueue_asr_report"
            ) as enqueue_report,
            patch(
                "core.providers.asr.base.startToChat",
                new=AsyncMock(),
            ) as start_chat,
        ):
            await provider.handle_voice_stop(connection, [b"\x00\x00"])

        enqueue_report.assert_not_called()
        start_chat.assert_awaited_once_with(
            connection,
            "普通插话",
            input_started_while_speaking=True,
        )
        self.assertFalse(connection.asr_started_while_speaking)

    async def test_wakeup_overlap_is_kept_in_chat_report(self):
        connection = SimpleNamespace(
            asr_started_while_speaking=True,
            client_is_speaking=True,
            voiceprint_provider=None,
            session_id="test-session",
            config={"wakeup_words": ["小草莓"]},
        )
        provider = _StubAsr("小草莓")

        with (
            patch(
                "core.providers.asr.base.enqueue_asr_report"
            ) as enqueue_report,
            patch(
                "core.providers.asr.base.startToChat",
                new=AsyncMock(),
            ),
        ):
            await provider.handle_voice_stop(connection, [b"\x00\x00"])

        enqueue_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
