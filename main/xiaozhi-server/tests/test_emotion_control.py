import asyncio
import json

from core.utils.textUtils import get_emotion, should_emit_emotion


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(json.loads(message))


class _FakeConnection:
    def __init__(self):
        self.websocket = _FakeWebSocket()
        self.session_id = "emotion-test"


def _emotion_for(text):
    connection = _FakeConnection()
    asyncio.run(get_emotion(connection, text))
    return connection.websocket.messages[0]


def test_excited_marker_controls_star_eyes():
    message = _emotion_for("🤩我们发现了一颗亮晶晶的小星星！")

    assert message["text"] == "🤩"
    assert message["emotion"] == "excited"


def test_missing_marker_falls_back_to_neutral():
    message = _emotion_for("我们慢慢想一想。")

    assert message["text"] == "😶"
    assert message["emotion"] == "neutral"


def test_first_supported_marker_wins():
    message = _emotion_for("先难过一下😔，后来又开心🙂。")

    assert message["text"] == "😔"
    assert message["emotion"] == "sad"


def test_stream_waits_for_marker_in_later_chunk():
    prefix = ""
    prefix += "我们一起"
    assert should_emit_emotion(prefix) is False

    prefix += "🙂来试试吧。"
    assert should_emit_emotion(prefix) is True


def test_stream_eventually_falls_back_without_marker():
    assert should_emit_emotion("我们慢慢想一想。", final=True) is True
