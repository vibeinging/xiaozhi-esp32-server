import asyncio
import base64
import json
import os
import queue
import random
import re
import time
import traceback

import websockets

from config.logger import setup_logging
from core.providers.bailian_realtime import build_realtime_ws_url, realtime_event
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import ContentType, InterfaceType, SentenceType
from core.utils.tts import MarkdownCleaner


TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    """Qwen3 TTS Flash Realtime，百炼 PCM 分片到达后立即转设备 Opus。"""

    TTS_PARAM_CONFIG = [
        ("ttsVolume", "volume", 0, 100, 50, int),
        ("ttsRate", "speech_rate", 0.5, 2.0, 1.0, lambda value: round(value, 1)),
        ("ttsPitch", "pitch_rate", 0.5, 2.0, 1.0, lambda value: round(value, 1)),
    ]

    FIRST_PUNCTUATION = "，,、：:~。！？!?\n"
    STRONG_PUNCTUATION = "。！？!?；;\n"
    CAT_MEOW_PATTERN = re.compile(r"喵(?:[～~—…!！。,.， ]*喵)?[～~—…!！。,.， ]*")
    CAT_SAFETY_MARKERS = (
        "危险",
        "受伤",
        "流血",
        "漏电",
        "触电",
        "插座",
        "电线",
        "着火",
        "火灾",
        "刀子",
        "药品",
        "吃药",
        "医院",
        "医生",
        "不舒服",
        "很疼",
        "好疼",
        "欺负",
        "打我",
        "摸我",
        "威胁",
        "保守秘密",
        "别告诉",
        "走失",
        "迷路",
        "陌生人",
        "马路",
        "窗台",
        "溺水",
        "自杀",
        "自伤",
        "伤害自己",
        "伤害别人",
        "救命",
        "求助",
        "110",
        "120",
        "119",
        "密码",
        "住址",
        "学校地址",
        "电话号码",
        "隐私",
        "可信任的大人",
        "需要爸爸妈妈",
        "不用告诉我",
        "我不能教",
        "不适合现在播放",
    )

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.interface_type = InterfaceType.DUAL_STREAM
        self.report_on_last = True

        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("Qwen3 实时 TTS 需要配置 api_key")

        self.model = config.get("model", "qwen3-tts-flash-realtime")
        self.voice = config.get("private_voice") or config.get("voice", "Cherry")
        self.language_type = config.get("language_type", "Chinese")
        self.volume = int(config.get("volume", 50))
        self.speech_rate = float(config.get("speech_rate", 1.0))
        self.pitch_rate = float(config.get("pitch_rate", 1.0))
        self.max_segment_chars = int(config.get("max_segment_chars", 18))
        self.cat_meow_enabled = bool(config.get("cat_meow_enabled", False))
        self.cat_meow_probability = min(
            1.0, max(0.0, float(config.get("cat_meow_probability", 0.5)))
        )
        self._random = random.random
        self._response_text = ""
        self._user_text = ""
        self._apply_percentage_params(config)

        self.ws_url = build_realtime_ws_url(
            config.get("base_url"), self.model, config.get("ws_url")
        )
        self.ws = None
        self._monitor_task = None
        self.activate_session = False
        self.last_active_time = None
        self.current_sentence_id = None
        self._text_buffer = ""
        self._first_segment = True
        self._first_audio_announced = False
        self._first_committed_text = None
        self._pending_responses = 0
        self._responses_done = asyncio.Event()
        self._responses_done.set()
        self._response_error = None
        self._output_finalized = False

    def tts_text_priority_thread(self):
        while not self.conn.stop_event.is_set():
            try:
                message = self.tts_text_queue.get(timeout=1)
                if message.sentence_id != self.conn.sentence_id:
                    continue

                if self.conn.client_abort:
                    asyncio.run_coroutine_threadsafe(self.close(), loop=self.conn.loop)
                    continue

                if message.sentence_type == SentenceType.FIRST:
                    self.current_sentence_id = message.sentence_id
                    future = asyncio.run_coroutine_threadsafe(
                        self.start_session(message.sentence_id), loop=self.conn.loop
                    )
                    future.result(timeout=self.tts_timeout)
                    self.before_stop_play_files.clear()
                elif (
                    message.content_type == ContentType.TEXT and message.content_detail
                ):
                    future = asyncio.run_coroutine_threadsafe(
                        self.text_to_speak(message.content_detail, None),
                        loop=self.conn.loop,
                    )
                    future.result(timeout=self.tts_timeout)
                elif message.content_type == ContentType.FILE:
                    if message.content_file and os.path.exists(message.content_file):
                        self._process_audio_file_stream(
                            message.content_file,
                            callback=lambda audio: self.handle_audio_file(
                                audio, message.content_detail
                            ),
                        )

                if message.sentence_type == SentenceType.LAST:
                    future = asyncio.run_coroutine_threadsafe(
                        self.finish_session(message.sentence_id), loop=self.conn.loop
                    )
                    future.result(timeout=self.tts_timeout + 3)
            except queue.Empty:
                continue
            except Exception as exc:
                logger.bind(tag=TAG).error(
                    f"处理 Qwen3 实时 TTS 文本失败: {exc}, "
                    f"堆栈: {traceback.format_exc()}"
                )

    async def start_session(self, session_id):
        await self._close_connection()
        self.reset_stream_state()
        self.current_sentence_id = session_id
        self.activate_session = True
        self._text_buffer = ""
        self._first_segment = True
        self._first_audio_announced = False
        self._first_committed_text = None
        self._pending_responses = 0
        self._responses_done = asyncio.Event()
        self._responses_done.set()
        self._response_error = None
        self._output_finalized = False
        self._response_text = ""
        self._user_text = str(getattr(self.conn, "current_user_query", "") or "")
        if hasattr(self, "opus_encoder") and self.opus_encoder:
            self.opus_encoder.reset_state()

        self.ws = await websockets.connect(
            self.ws_url,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
            ping_interval=20,
            ping_timeout=10,
            close_timeout=2,
            max_size=10 * 1024 * 1024,
        )
        await self._wait_for_event("session.created")

        sample_rate = int(self.conn.sample_rate)
        if sample_rate not in (8000, 16000, 24000, 48000):
            raise ValueError(f"Qwen3 实时 TTS 不支持采样率 {sample_rate}")
        await self.ws.send(
            json.dumps(
                realtime_event(
                    "session.update",
                    session={
                        "voice": self.voice,
                        "mode": "commit",
                        "language_type": self.language_type,
                        "response_format": "pcm",
                        "sample_rate": sample_rate,
                        "speech_rate": self.speech_rate,
                        "volume": self.volume,
                        "pitch_rate": self.pitch_rate,
                    },
                ),
                ensure_ascii=False,
            )
        )
        await self._wait_for_event("session.updated")
        self._monitor_task = asyncio.create_task(self._monitor_response())

    async def _wait_for_event(self, expected_type):
        while True:
            message = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=10))
            event_type = message.get("type")
            if event_type == expected_type:
                return message
            if event_type == "error":
                raise RuntimeError(self._error_text(message))

    async def text_to_speak(self, text, _):
        if not self.ws or not self.activate_session:
            logger.bind(tag=TAG).warning("Qwen3 实时 TTS 会话未就绪，忽略文本")
            return
        cleaned = MarkdownCleaner.clean_markdown(text)
        if not cleaned:
            return
        self._response_text += cleaned
        if self.cat_meow_enabled and self._contains_safety_signal(self._user_text):
            cleaned = self.CAT_MEOW_PATTERN.sub("", cleaned)
            if not cleaned.strip():
                return
        self._text_buffer += cleaned
        for segment in self._drain_text_segments(force=False):
            await self._commit_text(segment)

    def _drain_text_segments(self, force=False):
        segments = []
        while self._text_buffer:
            punctuation = (
                self.FIRST_PUNCTUATION
                if self._first_segment
                else self.STRONG_PUNCTUATION
            )
            cut = next(
                (
                    index + 1
                    for index, char in enumerate(self._text_buffer)
                    if char in punctuation
                ),
                None,
            )
            if cut is None and len(self._text_buffer) >= self.max_segment_chars:
                cut = self.max_segment_chars
            if cut is None and force:
                cut = len(self._text_buffer)
            if cut is None:
                break

            segment = self._text_buffer[:cut]
            self._text_buffer = self._text_buffer[cut:]
            if self._correct_words_pattern:
                segment = self._correct_words_pattern.sub(
                    lambda match: self.correct_words[match.group(0)], segment
                )
            if segment.strip():
                segments.append(segment)
                self._first_segment = False
        return segments

    async def _commit_text(self, text):
        if not self.ws or not text:
            return
        if self._first_committed_text is None:
            self._first_committed_text = text
        self._pending_responses += 1
        self._responses_done.clear()
        await self.ws.send(
            json.dumps(
                realtime_event("input_text_buffer.append", text=text),
                ensure_ascii=False,
            )
        )
        await self.ws.send(json.dumps(realtime_event("input_text_buffer.commit")))
        self.last_active_time = time.time()

    async def _monitor_response(self):
        try:
            while self.ws and not self.conn.stop_event.is_set():
                message = json.loads(await self.ws.recv())
                event_type = message.get("type")
                self.last_active_time = time.time()

                if event_type == "response.audio.delta":
                    pcm = base64.b64decode(message.get("delta", ""))
                    if pcm and not self._first_audio_announced:
                        text = self.get_tts_text(self.current_sentence_id)
                        text = text or self._first_committed_text
                        self.tts_audio_queue.put(
                            (SentenceType.FIRST, [], text, self.current_sentence_id)
                        )
                        self._first_audio_announced = True
                    if pcm:
                        self.opus_encoder.encode_pcm_to_opus_stream(
                            pcm, False, callback=self.handle_opus
                        )
                elif event_type == "response.done":
                    self._pending_responses = max(0, self._pending_responses - 1)
                    if self._pending_responses == 0:
                        self._responses_done.set()
                elif event_type == "error":
                    self._response_error = self._error_text(message)
                    self._responses_done.set()
                    logger.bind(tag=TAG).error(
                        f"Qwen3 实时 TTS 服务错误: {self._response_error}"
                    )
                    break
                elif event_type == "session.finished":
                    break
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as exc:
            self._response_error = f"connection closed before response completed: {exc}"
            self._responses_done.set()
            logger.bind(tag=TAG).warning(
                "Qwen3 实时 TTS 连接在音频完成前关闭"
            )
        except Exception as exc:
            self._response_error = str(exc)
            self._responses_done.set()
            logger.bind(tag=TAG).error(f"处理 Qwen3 实时 TTS 音频失败: {exc}")

    async def finish_session(self, session_id):
        if self._output_finalized:
            return
        if self._should_append_cat_meow():
            self._text_buffer += " 喵～喵～"
        for segment in self._drain_text_segments(force=True):
            await self._commit_text(segment)

        if self._pending_responses:
            try:
                await asyncio.wait_for(
                    self._responses_done.wait(), timeout=self.tts_timeout
                )
            except asyncio.TimeoutError:
                logger.bind(tag=TAG).error(
                    f"Qwen3 实时 TTS 等待音频超时，"
                    f"未完成响应数: {self._pending_responses}"
                )

        if self.ws:
            try:
                await self.ws.send(json.dumps(realtime_event("session.finish")))
            except Exception:
                pass

        # 百炼的 session.finished 可能晚约 10 秒，音频已收齐时不再等它。
        self.opus_encoder.encode_pcm_to_opus_stream(
            b"", True, callback=self.handle_opus
        )
        self._output_finalized = True
        self.activate_session = False
        self._process_before_stop_play_files()
        await self._close_connection()

    @classmethod
    def _contains_safety_signal(cls, text):
        normalized = str(text or "")
        return any(marker in normalized for marker in cls.CAT_SAFETY_MARKERS)

    def _should_append_cat_meow(self):
        if not self.cat_meow_enabled or not self._response_text.strip():
            return False

        if self._user_text.startswith("[儿童安全事件:"):
            return False

        if self.tts_text_queue.is_blocked(self.current_sentence_id):
            return False

        combined = f"{self._user_text}\n{self._response_text}"
        if self._contains_safety_signal(combined):
            return False

        if "喵" in self._response_text:
            return False

        return self._random() < self.cat_meow_probability

    async def _close_connection(self):
        ws = self.ws
        self.ws = None
        if ws:
            try:
                await asyncio.wait_for(ws.close(), timeout=1)
                await asyncio.sleep(0.05)
            except Exception:
                pass

        current = asyncio.current_task()
        if self._monitor_task and self._monitor_task is not current:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except (asyncio.CancelledError, Exception):
                pass
        self._monitor_task = None

    async def close(self):
        self.activate_session = False
        await self._close_connection()
        self._sentence_text_map.clear()

    def to_tts(self, text):
        """为唤醒词缓存生成独立的 Opus 音频。

        这条路径不会经过 FIRST/LAST 队列，所以使用独立 WebSocket
        和独立 Opus 编码器，不影响正在进行的对话会话。
        """
        from core.utils.opus_encoder_utils import OpusEncoderUtils

        cleaned = MarkdownCleaner.clean_markdown(text)
        if not cleaned or not self.conn:
            return []

        sample_rate = int(self.conn.sample_rate)
        if sample_rate not in (8000, 16000, 24000, 48000):
            logger.bind(tag=TAG).error(
                f"Qwen3 实时 TTS 不支持唤醒词采样率 {sample_rate}"
            )
            return []

        async def generate():
            packets = []
            encoder = OpusEncoderUtils(sample_rate, 1, 60)
            ws = await websockets.connect(
                self.ws_url,
                additional_headers={"Authorization": f"Bearer {self.api_key}"},
                ping_interval=20,
                ping_timeout=10,
                close_timeout=2,
                max_size=10 * 1024 * 1024,
            )
            try:
                await self._wait_for_event_on(ws, "session.created")
                await ws.send(
                    json.dumps(
                        realtime_event(
                            "session.update",
                            session={
                                "voice": self.voice,
                                "mode": "commit",
                                "language_type": self.language_type,
                                "response_format": "pcm",
                                "sample_rate": sample_rate,
                                "speech_rate": self.speech_rate,
                                "volume": self.volume,
                                "pitch_rate": self.pitch_rate,
                            },
                        ),
                        ensure_ascii=False,
                    )
                )
                await self._wait_for_event_on(ws, "session.updated")
                await ws.send(
                    json.dumps(
                        realtime_event("input_text_buffer.append", text=cleaned),
                        ensure_ascii=False,
                    )
                )
                await ws.send(json.dumps(realtime_event("input_text_buffer.commit")))

                while True:
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                    event_type = message.get("type")
                    if event_type == "response.audio.delta":
                        pcm = base64.b64decode(message.get("delta", ""))
                        if pcm:
                            encoder.encode_pcm_to_opus_stream(
                                pcm, False, callback=packets.append
                            )
                    elif event_type == "response.done":
                        encoder.encode_pcm_to_opus_stream(
                            b"", True, callback=packets.append
                        )
                        try:
                            await ws.send(json.dumps(realtime_event("session.finish")))
                        except Exception:
                            pass
                        return packets
                    elif event_type == "error":
                        raise RuntimeError(self._error_text(message))
            finally:
                try:
                    await asyncio.wait_for(ws.close(), timeout=1)
                    await asyncio.sleep(0.05)
                except Exception:
                    pass
                encoder.close()

        try:
            # 唤醒词缓存在工作线程中调用此同步方法。将 WebSocket
            # 放到设备连接的长期事件循环，避免 asyncio.run() 在 SSL
            # transport 的最后回调到达前就销毁短命事件循环。
            conn_loop = getattr(self.conn, "loop", None)
            if conn_loop and conn_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(generate(), conn_loop)
                return future.result(timeout=self.tts_timeout + 3)
            return asyncio.run(generate())
        except Exception as exc:
            logger.bind(tag=TAG).error(f"生成唤醒词音频失败: {exc}")
            return []

    async def _wait_for_event_on(self, ws, expected_type):
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            event_type = message.get("type")
            if event_type == expected_type:
                return message
            if event_type == "error":
                raise RuntimeError(self._error_text(message))

    def audio_to_opus_data_stream(self, audio_file_path, callback=None):
        # 文件音频另建编码器，避免与实时 PCM 的编码缓冲并发修改。
        from core.utils.util import audio_to_data_stream

        return audio_to_data_stream(
            audio_file_path,
            is_opus=True,
            callback=callback,
            sample_rate=self.conn.sample_rate,
            opus_encoder=None,
        )

    @staticmethod
    def _error_text(message):
        error = message.get("error") or {}
        if isinstance(error, dict):
            return f"{error.get('code', 'unknown')}: {error.get('message', error)}"
        return str(error or message)
