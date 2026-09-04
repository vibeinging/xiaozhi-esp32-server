import queue
import sys
import types
import unittest

sys.modules.setdefault("opuslib_next", types.SimpleNamespace())

from core.handle.reportHandle import enqueue_asr_report
from core.safety import ChildContentSafetyPolicy


class _Logger:
    def bind(self, **_kwargs):
        return self

    def debug(self, *_args, **_kwargs):
        return None


class _Connection:
    def __init__(self, chat_history_conf=1):
        self.read_config_from_api = True
        self.need_bind = False
        self.report_asr_enable = True
        self.chat_history_conf = chat_history_conf
        self.content_safety = ChildContentSafetyPolicy(enabled=True)
        self.report_queue = queue.Queue()
        self.logger = _Logger()
        self.device_id = "test-device"


class ChildSafetyReportTest(unittest.TestCase):
    def test_high_risk_report_keeps_category_but_not_original_text(self):
        connection = _Connection()
        original = "我不想活了"

        enqueue_asr_report(connection, original, [b"audio"])

        _, content, audio, _ = connection.report_queue.get_nowait()
        self.assertNotIn(original, content)
        self.assertIn("self_harm", content)
        self.assertIsNone(audio)

    def test_child_mode_never_uploads_audio_even_if_config_is_two(self):
        connection = _Connection(chat_history_conf=2)

        enqueue_asr_report(connection, "给我讲个故事", [b"audio"])

        _, content, audio, _ = connection.report_queue.get_nowait()
        self.assertEqual(content, "给我讲个故事")
        self.assertIsNone(audio)

    def test_private_text_is_redacted_before_report(self):
        connection = _Connection()

        enqueue_asr_report(connection, "妈妈电话是13812345678", [])

        _, content, _, _ = connection.report_queue.get_nowait()
        self.assertNotIn("13812345678", content)
        self.assertIn("privacy", content)


if __name__ == "__main__":
    unittest.main()
