import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.handle.receiveAudioHandle import startToChat
from core.safety import ChildContentSafetyPolicy


class _DialogueRecorder:
    def __init__(self):
        self.messages = []

    def put(self, message):
        self.messages.append(message)


class _Logger:
    def bind(self, **_kwargs):
        return self

    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None


class _FakeConnection:
    def __init__(self):
        self.content_safety = ChildContentSafetyPolicy(enabled=True)
        self.introduced_speakers = set()
        self.current_speaker = None
        self.need_bind = False
        self.max_output_size = 0
        self.client_is_speaking = False
        self.client_listen_mode = "auto"
        self.client_abort = False
        self.current_user_query = ""
        self.sentence_id = None
        self.features = {"emoji": True}
        self.dialogue = _DialogueRecorder()
        self.logger = _Logger()


class ChildSafetyReceivePathTest(unittest.IsolatedAsyncioTestCase):
    async def test_private_input_never_reaches_intent_or_chat_history(self):
        connection = _FakeConnection()
        private_text = "我妈妈电话是13812345678"

        with (
            patch(
                "core.handle.receiveAudioHandle.handle_user_intent",
                new=AsyncMock(),
            ) as intent,
            patch(
                "core.handle.receiveAudioHandle.send_stt_message",
                new=AsyncMock(),
            ) as send_stt,
            patch(
                "core.handle.receiveAudioHandle.textUtils.get_emotion",
                new=AsyncMock(),
            ) as emotion,
            patch(
                "core.handle.receiveAudioHandle.speak_txt",
                new=Mock(),
            ) as speak,
        ):
            await startToChat(connection, private_text)

        intent.assert_not_awaited()
        send_stt.assert_awaited_once()
        emotion.assert_awaited_once()
        speak.assert_called_once()
        self.assertNotIn("13812345678", connection.current_user_query)
        self.assertEqual(len(connection.dialogue.messages), 1)
        self.assertNotIn(
            "13812345678", connection.dialogue.messages[0].content
        )


if __name__ == "__main__":
    unittest.main()
