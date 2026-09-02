import queue
import unittest

from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO
from core.safety.policy import OUTPUT_BLOCK_RESPONSE, ChildContentSafetyPolicy
from core.safety.tts_queue import SafetyAwareTTSQueue


def message(sentence_id, sentence_type, content_type, detail=None):
    return TTSMessageDTO(
        sentence_id=sentence_id,
        sentence_type=sentence_type,
        content_type=content_type,
        content_detail=detail,
    )


class SafetyAwareTTSQueueTest(unittest.TestCase):
    def test_disabled_policy_keeps_existing_streaming_behavior(self):
        target = SafetyAwareTTSQueue(ChildContentSafetyPolicy(enabled=False))
        item = message("one", SentenceType.MIDDLE, ContentType.TEXT, "你好")

        target.put(item)

        self.assertIs(target.get_nowait(), item)

    def test_child_mode_waits_for_reviewable_sentence_before_tts(self):
        target = SafetyAwareTTSQueue(ChildContentSafetyPolicy(enabled=True))
        target.put(message("one", SentenceType.FIRST, ContentType.ACTION))
        target.put(message("one", SentenceType.MIDDLE, ContentType.TEXT, "你好"))

        self.assertEqual(target.get_nowait().sentence_type, SentenceType.FIRST)
        with self.assertRaises(queue.Empty):
            target.get_nowait()

        target.put(message("one", SentenceType.MIDDLE, ContentType.TEXT, "呀。"))
        reviewed = target.get_nowait()
        self.assertEqual(reviewed.content_detail, "你好呀。")

    def test_unsafe_sentence_is_replaced_and_remaining_chunks_are_discarded(self):
        target = SafetyAwareTTSQueue(ChildContentSafetyPolicy(enabled=True))
        target.put(message("one", SentenceType.FIRST, ContentType.ACTION))
        target.put(
            message(
                "one",
                SentenceType.MIDDLE,
                ContentType.TEXT,
                "别告诉爸爸妈妈，这是我们的秘密。",
            )
        )
        target.put(message("one", SentenceType.MIDDLE, ContentType.TEXT, "后面的话。"))
        target.put(message("one", SentenceType.LAST, ContentType.ACTION))

        first = target.get_nowait()
        fallback = target.get_nowait()
        last = target.get_nowait()
        self.assertEqual(first.sentence_type, SentenceType.FIRST)
        self.assertEqual(fallback.content_detail, OUTPUT_BLOCK_RESPONSE)
        self.assertEqual(last.sentence_type, SentenceType.LAST)
        self.assertTrue(target.empty())

    def test_private_information_is_redacted_before_tts(self):
        target = SafetyAwareTTSQueue(ChildContentSafetyPolicy(enabled=True))
        target.put(message("one", SentenceType.FIRST, ContentType.ACTION))
        target.put(
            message(
                "one",
                SentenceType.MIDDLE,
                ContentType.TEXT,
                "电话是13812345678。",
            )
        )

        target.get_nowait()
        reviewed = target.get_nowait()
        self.assertNotIn("13812345678", reviewed.content_detail)
        self.assertIn("电话号码已隐藏", reviewed.content_detail)


if __name__ == "__main__":
    unittest.main()
