import asyncio
import base64
import json
import math

import websockets

from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType
from core.providers.bailian_realtime import build_realtime_ws_url, realtime_event


TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    """Qwen3 ASR Flash Realtime，输入为 16 kHz 单声道 PCM。"""

    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.interface_type = InterfaceType.STREAM
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("Qwen3 实时 ASR 需要配置 api_key")

        self.model = config.get("model", "qwen3-asr-flash-realtime-2026-02-10")
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.language = config.get("language", "zh")
        self.ws_url = build_realtime_ws_url(
            config.get("base_url"), self.model, config.get("ws_url")
        )
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file
        self.final_result_timeout = float(
            config.get("final_result_timeout_seconds", 8)
        )
        if (
            not math.isfinite(self.final_result_timeout)
            or self.final_result_timeout <= 0
        ):
            raise ValueError(
                "final_result_timeout_seconds must be a positive finite number"
            )
        self.max_buffer_bytes = max(
            self.sample_rate * 2,
            int(float(config.get("max_buffer_seconds", 30)) * self.sample_rate * 2),
        )

        self.asr_ws = None
        self.forward_task = None
        self.is_processing = False
        self.server_ready = False
        self.input_committed = False
        self._commit_deadline = None
        self.text = ""
        self._cleanup_lock = asyncio.Lock()

    async def receive_audio(self, conn, pcm_frame, audio_have_voice):
        # commit 后只等最终文字，不再把后续环境音塞进当前句子的缓存。
        if self.input_committed:
            return
        await super().receive_audio(conn, pcm_frame, audio_have_voice)
        self._trim_audio_buffer(conn)

        started_now = False
        if audio_have_voice and not self.is_processing and self.asr_ws is None:
            try:
                await self._start_recognition(conn)
                started_now = True
            except Exception as exc:
                logger.bind(tag=TAG).error(f"启动 Qwen3 实时 ASR 失败: {exc}")
                await self._cleanup()
                return

        if (
            self.asr_ws
            and self.server_ready
            and self.is_processing
            and not self.input_committed
        ):
            try:
                # 刚连接时已发送了包含当前帧的预缓冲，不重复发送。
                if not started_now:
                    await self._send_audio_frame(pcm_frame)
                if conn.client_voice_stop:
                    await self._send_stop_request()
            except Exception as exc:
                logger.bind(tag=TAG).warning(f"发送 ASR 音频失败: {exc}")
                await self._cleanup()
                conn.reset_audio_states()

    async def _start_recognition(self, conn):
        self.is_processing = True
        self.server_ready = False
        self.input_committed = False
        self._commit_deadline = None
        self.text = ""

        self.asr_ws = await websockets.connect(
            self.ws_url,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
            ping_interval=20,
            ping_timeout=10,
            close_timeout=3,
            max_size=10 * 1024 * 1024,
        )

        await self._wait_for_event("session.created")
        await self.asr_ws.send(
            json.dumps(
                realtime_event(
                    "session.update",
                    session={
                        "input_audio_format": "pcm",
                        "sample_rate": self.sample_rate,
                        "input_audio_transcription": {"language": self.language},
                        # 设备服务端已有 VAD，由它决定句子结束，避免两套 VAD 互相等待。
                        "turn_detection": None,
                    },
                ),
                ensure_ascii=False,
            )
        )
        await self._wait_for_event("session.updated")
        self.server_ready = True

        # 补发 VAD 确认说话前保留的短预缓冲，避免吞掉第一个字。
        for cached_pcm in list(conn.asr_audio):
            await self._send_audio_frame(cached_pcm)

        self.forward_task = asyncio.create_task(self._forward_results(conn))

    async def _wait_for_event(self, expected_type):
        while True:
            raw = await asyncio.wait_for(self.asr_ws.recv(), timeout=10)
            message = json.loads(raw)
            event_type = message.get("type")
            if event_type == expected_type:
                return message
            if event_type == "error":
                raise RuntimeError(self._error_text(message))

    async def _send_audio_frame(self, pcm_frame):
        if not pcm_frame:
            return
        await self.asr_ws.send(
            json.dumps(
                realtime_event(
                    "input_audio_buffer.append",
                    audio=base64.b64encode(pcm_frame).decode("ascii"),
                )
            )
        )

    async def _send_stop_request(self):
        """只提交音频，收到 completed 后再结束会话。

        如果 commit 后立即 finish，百炼会等待约 10 秒才返回最终文字。
        """
        if not self.asr_ws or not self.server_ready or self.input_committed:
            return
        self.input_committed = True
        self._commit_deadline = (
            asyncio.get_running_loop().time() + self.final_result_timeout
        )
        await self.asr_ws.send(json.dumps(realtime_event("input_audio_buffer.commit")))

    async def _recv_result_event(self):
        if not self.input_committed or self._commit_deadline is None:
            return await self.asr_ws.recv()
        remaining = self._commit_deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError
        return await asyncio.wait_for(self.asr_ws.recv(), timeout=remaining)

    def _trim_audio_buffer(self, conn):
        total_bytes = sum(len(frame) for frame in conn.asr_audio)
        while conn.asr_audio and total_bytes > self.max_buffer_bytes:
            total_bytes -= len(conn.asr_audio.pop(0))

    async def _forward_results(self, conn):
        try:
            while not conn.stop_event.is_set() and self.asr_ws:
                raw = await self._recv_result_event()
                message = json.loads(raw)
                event_type = message.get("type")

                if event_type == "conversation.item.input_audio_transcription.text":
                    partial = "".join(
                        part
                        for part in (message.get("text", ""), message.get("stash", ""))
                        if part
                    )
                    if partial:
                        logger.bind(tag=TAG).debug(
                            f"ASR 实时文字长度: {len(partial)}"
                        )
                elif (
                    event_type
                    == "conversation.item.input_audio_transcription.completed"
                ):
                    self.text = (message.get("transcript") or "").strip()
                    audio_snapshot = conn.asr_audio.copy()
                    await self.asr_ws.send(json.dumps(realtime_event("session.finish")))
                    await self.handle_voice_stop(conn, audio_snapshot)
                    break
                elif event_type == "error":
                    raise RuntimeError(self._error_text(message))
                elif event_type == "session.finished":
                    break
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as exc:
            logger.bind(tag=TAG).warning(f"Qwen3 实时 ASR 连接已关闭: {exc}")
        except asyncio.TimeoutError:
            logger.bind(tag=TAG).error(
                f"Qwen3 实时 ASR 等待最终文字超时: {self.final_result_timeout}s"
            )
        except Exception as exc:
            logger.bind(tag=TAG).error(f"处理 Qwen3 实时 ASR 结果失败: {exc}")
        finally:
            await self._cleanup()
            conn.reset_audio_states()

    @staticmethod
    def _error_text(message):
        error = message.get("error") or {}
        if isinstance(error, dict):
            return f"{error.get('code', 'unknown')}: {error.get('message', error)}"
        return str(error or message)

    async def _cleanup(self):
        current = asyncio.current_task()
        async with self._cleanup_lock:
            self.is_processing = False
            self.server_ready = False
            self.input_committed = False
            self._commit_deadline = None

            ws = self.asr_ws
            self.asr_ws = None
            task_to_cancel = None
            if self.forward_task and self.forward_task is not current:
                task_to_cancel = self.forward_task
            self.forward_task = None

        if ws:
            try:
                await asyncio.wait_for(ws.close(), timeout=2)
                # 让 SSL transport 完成关闭回调，避免短命令行进程退出时留下写任务。
                await asyncio.sleep(0.05)
            except Exception:
                pass

        if task_to_cancel:
            task_to_cancel.cancel()
            try:
                await task_to_cancel
            except (asyncio.CancelledError, Exception):
                pass

    async def speech_to_text(self, opus_data, session_id, artifacts=None):
        result = self.text
        self.text = ""
        return result, None

    async def close(self):
        await self._cleanup()
