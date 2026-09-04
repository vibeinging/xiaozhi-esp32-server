# 百炼流式 ASR/TTS 改造与生产发布报告

> 后续更新：2026-09-02 的 v4 已将音色从 `Cherry` 改为 `Momo`，并加入普通回复 50% 概率的“喵～喵～”。详见 `docs/reports/2026-09-02_ragdoll-cat-voice-release.md`。下文保留 v3 发布时的历史记录。

## 结论

小布已改为百炼实时语音链路：

- ASR：`qwen3-asr-flash-realtime-2026-02-10`；
- LLM：保持 `qwen3.7-flash`，未修改；
- TTS：`qwen3-tts-flash-realtime`；
- 音色：`Cherry`；
- 所有模型请求继续使用同一个百炼北京业务空间。

生产发布版本：

`/opt/yingxiai/releases/v0.9.6-yiyiai-realtime-speech-v3`

## 音频链路

### ASR

1. 硬件上传 Opus 音频帧。
2. 服务端入口将它解码为 16 kHz、单声道 PCM。
3. PCM 以 60 ms 左右的分片连续发送给百炼实时 ASR。
4. 服务端本地 VAD 判定说话结束后发送 `input_audio_buffer.commit`。
5. 收到 `conversation.item.input_audio_transcription.completed` 后，再发送 `session.finish`，然后将文字交给 LLM。

实测发现：如果在 `commit` 后立即 `finish`，百炼会延迟约 10 秒返回最终文字。改成上述顺序后，合成语音的尾部到最终文字为 168–172 ms。

### TTS

1. LLM 返回的文本按首个逗号、句号或最大 18 字分成短句。
2. 每个短句使用 `input_text_buffer.append + commit` 立即提交，不等待整段 LLM 回答结束。
3. 百炼返回 PCM 分片时，服务端立即编码为设备需要的 Opus 帧。
4. 音频已全部收到后立即向设备发送 `LAST`，不等待最多会晚约 10 秒的 `session.finished`。

直连实测首个 PCM 分片为 257–279 ms。真实 Provider 测试生成了 30 个 Opus 帧，队列顺序是 `FIRST -> MIDDLE -> LAST`。

## 唤醒词缓存兼容

设备第一次重连时，日志发现唤醒词缓存的后台刷新会直接调用 `to_tts()`，不会先发送 TTS `FIRST`。初版因此忽略了这段文本。

修正版为该路径增加了独立 WebSocket 和独立 Opus 编码器，不与正在进行的对话共享状态。使用“我一直都在呢，您请说。”实测生成 33 个 Opus 帧。

v2 使用临时事件循环运行后台缓存，WebSocket 关闭后仍可能有 SSL 回调，导致事件循环已关闭异常。v3 改为把缓存任务放到设备连接的长期事件循环中执行。按生产调用方式测试生成 40 个 Opus 帧，没有再出现 SSL 异常。

## 验证

- Python 编译检查通过。
- Ruff 检查通过。
- 7 个定向单元测试通过。
- 百炼 TTS 直连：首包 257–279 ms。
- 百炼 ASR 直连：合成语音识别为“你好，小布在这里。”，尾部延迟 168–172 ms。
- 设备在 v3 发布后自动重连，服务日志确认加载 `ASR_Qwen3Realtime`、`TTS_Qwen3Realtime`、`LLM_AliLLM/qwen3.7-flash`。
- 真实设备连续识别出“行。”“谢谢。”“今天周几啊？”和“今天天气怎么样？”。
- “今天天气怎么样？”从 ASR 最终文字到 TTS 首段音频约 1 秒；回复完成后正常发送 `LAST`。
- 从 v3 启动到实际对话完成，日志中没有 `Fatal`、SSL、ASR 或 TTS 异常。
- `yingxiai-server`、`yingxiai-manager` 均为 `active`。
- `https://yiyiai.mediaprogram.cn/` 返回 HTTP 200。

测试只使用了合成语音“你好，小布在这里。”，没有使用孩子的真实语音。

## 生产备份与回滚

- 数据库备份：`/opt/yingxiai/backups/20260902T074725-realtime-speech/before.sql`；
- 备份已校验，包含 5 张相关表；
- 上一个稳定版本：`/opt/yingxiai/releases/v0.9.6-yiyiai-audio-v1`；
- 回滚脚本：`deploy/yingxiai/migrations/2026-09-02-bailian-realtime-speech.rollback.sql`。

回滚会恢复：

- ASR：`ASR_Qwen3Flash`；
- TTS：`TTS_EdgeTTS`；
- 小布旧音色：`TTS_EdgeTTS0008`；
- LLM 始终保持 `LLM_AliLLM / qwen3.7-flash`。

## 人工听感

生产日志已经证明真实硬件完成了“设备音频 -> 流式 ASR -> qwen3.7-flash -> 流式 TTS -> 音频帧发送回设备”整条数据链路。日志不能证明喇叭实际发声；是否能听到、是否足够自然、音量是否合适，仍以现场听感为准。
