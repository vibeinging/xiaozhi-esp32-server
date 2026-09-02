"""确保儿童模式下的文本先形成可审核片段，再进入真正的 TTS 队列。"""

from __future__ import annotations

import queue
import threading

from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO
from core.safety.policy import (
    OUTPUT_BLOCK_RESPONSE,
    ChildContentSafetyPolicy,
    SafetyAction,
)


class SafetyAwareTTSQueue:
    STRONG_PUNCTUATION = frozenset("。！？!?；;\n")

    def __init__(
        self,
        policy: ChildContentSafetyPolicy | None = None,
        max_buffer_chars: int = 80,
    ):
        self._queue = queue.Queue()
        self._policy = policy or ChildContentSafetyPolicy(enabled=False)
        self._max_buffer_chars = max(24, int(max_buffer_chars))
        self._buffers: dict[str, str] = {}
        self._blocked_sentence_ids = set()
        self._lock = threading.RLock()

    def set_policy(self, policy: ChildContentSafetyPolicy):
        with self._lock:
            self._policy = policy or ChildContentSafetyPolicy(enabled=False)
            self._buffers.clear()
            self._blocked_sentence_ids.clear()

    def put(self, message, block=True, timeout=None):
        if not self._policy.enabled or not isinstance(message, TTSMessageDTO):
            return self._queue.put(message, block=block, timeout=timeout)

        with self._lock:
            sentence_id = message.sentence_id
            if message.sentence_type == SentenceType.FIRST:
                self._buffers[sentence_id] = ""
                self._blocked_sentence_ids.discard(sentence_id)
                return self._queue.put(message, block=block, timeout=timeout)

            if message.content_type == ContentType.TEXT and message.content_detail:
                if sentence_id not in self._blocked_sentence_ids:
                    self._buffers[sentence_id] = (
                        self._buffers.get(sentence_id, "") + str(message.content_detail)
                    )
                    self._flush_ready(sentence_id, force=False)
            elif message.content_type == ContentType.FILE:
                self._flush_ready(sentence_id, force=True)
                self._queue.put(message, block=block, timeout=timeout)

            if message.sentence_type == SentenceType.LAST:
                self._flush_ready(sentence_id, force=True)
                self._buffers.pop(sentence_id, None)
                return self._queue.put(message, block=block, timeout=timeout)
        return None

    def put_nowait(self, message):
        return self.put(message, block=False)

    def get(self, block=True, timeout=None):
        return self._queue.get(block=block, timeout=timeout)

    def get_nowait(self):
        return self._queue.get_nowait()

    def qsize(self):
        return self._queue.qsize()

    def empty(self):
        return self._queue.empty()

    def task_done(self):
        return self._queue.task_done()

    def join(self):
        return self._queue.join()

    def is_blocked(self, sentence_id: str | None) -> bool:
        with self._lock:
            return bool(sentence_id and sentence_id in self._blocked_sentence_ids)

    def _flush_ready(self, sentence_id: str, force: bool):
        while sentence_id not in self._blocked_sentence_ids:
            buffer = self._buffers.get(sentence_id, "")
            cut = self._find_cut(buffer, force)
            if cut is None:
                return
            segment = buffer[:cut]
            self._buffers[sentence_id] = buffer[cut:]
            if segment:
                self._emit_reviewed_segment(sentence_id, segment)
            if not force and not self._buffers.get(sentence_id):
                return

    def _find_cut(self, buffer: str, force: bool):
        if not buffer:
            return None
        for index, char in enumerate(buffer):
            if char in self.STRONG_PUNCTUATION:
                return index + 1
        if len(buffer) >= self._max_buffer_chars:
            preferred = max(
                buffer.rfind("，", 0, self._max_buffer_chars),
                buffer.rfind(",", 0, self._max_buffer_chars),
            )
            if preferred >= self._max_buffer_chars // 2:
                return preferred + 1
            return self._max_buffer_chars
        return len(buffer) if force else None

    def _emit_reviewed_segment(self, sentence_id: str, segment: str):
        decision = self._policy.evaluate_output(segment)
        if decision.action == SafetyAction.BLOCK_OUTPUT:
            self._blocked_sentence_ids.add(sentence_id)
            self._buffers[sentence_id] = ""
            safe_text = decision.response or OUTPUT_BLOCK_RESPONSE
        else:
            safe_text = decision.safe_text or segment
        self._queue.put(
            TTSMessageDTO(
                sentence_id=sentence_id,
                sentence_type=SentenceType.MIDDLE,
                content_type=ContentType.TEXT,
                content_detail=safe_text,
            )
        )
