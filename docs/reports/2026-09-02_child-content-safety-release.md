# 小布儿童内容安全第一阶段发布报告

日期：2026-09-02

## 结论

已在生产上线不依赖外部审核 API 的儿童安全底座。本次按要求没有开通、安装或调用 `TextModerationPlus`。

生产发布目录：

`/opt/yingxiai/releases/v0.9.6-yiyiai-child-safety-v8`

## 已上线能力

- ASR 文字进入意图识别、工具和 LLM 之前，先处理自伤、受侵害、走失、紧急危险、隐私、危险做法和需家长操作的请求。
- 高风险输入不进入 LLM 和工具，不保留原文，直接使用短而明确的固定安全回应。
- 小布的工具权限改为服务端白名单。当前数据库只保留 `SYSTEM_PLUGIN_WEATHER` 和 `SYSTEM_PLUGIN_MUSIC`，`NewsNow` 已移除。
- 普通 LLM、`direct_answer` 和工具直接回复都通过同一个句子级安全队列；文本通过后才会进入 TTS。
- 危险输出会换成固定回应，丢弃该轮后续文本，并禁止随机“喵～喵～”。
- ASR/TTS、说话人、工具参数和完整对话日志已收紧为长度、摘要、风险类别和参数名。
- 工具结果会移除控制标记、明显提示注入和密钥/手机号/验证码。

## 数据和记忆状态

- 生产仍为 `Memory_nomem`。
- `chat_history_conf=0`，不上报聊天文本或原始音频。
- 发布源码包含之前已完成的 MemMe 适配器，但生产没有选中它，不会发起 MemMe 请求。

## 验证

- 本地回归：34 个测试通过，另包含 12 组风险子样例。
- 覆盖正常陪学/英文/故事、自伤、受侵害、走失、隐私、危险请求、工具白名单、提示注入、TTS 旁路和安全回应禁止猫叫。
- 服务器实际 Python 3.10 环境的安全策略、TTS 队列、ASR/TTS 协议和输入旁路测试通过。
- `yingxiai-server`、`yingxiai-manager`、`yingxiai-mysql`、`yingxiai-redis` 均为 `active`。
- 语音服务进程工作目录已确认为 v8，启动后 `ERROR/Traceback/Exception/Fatal` 计数为 0。
- `https://yiyiai.mediaprogram.cn/` 返回 HTTP 200，本地管理 API 健康检查返回 200。

## 备份与回滚

- 发布前数据库备份：`/opt/yingxiai/backups/20260902T104656-child-safety`。
- 上一稳定版本：`/opt/yingxiai/releases/v0.9.6-yiyiai-serena-voice-v7`。
- 回滚脚本：`deploy/yingxiai/migrations/2026-09-02-child-content-safety.rollback.sql`。
- 第一次迁移因生产 MySQL 排序规则不同在提交前失败，未切换服务且事务未落库。改为二进制精确比较后迁移成功。

## 当前边界

- 本地规则只负责高确定性风险，无法覆盖所有隐喻、方言、ASR 误识别和长上下文语义。`TextModerationPlus` 暂缓后，这项语义审核缺口仍存在。
- 句子级输出安全会等待句号/问号/感叹号或 80 字上限，相比原先逐字进 TTS 会增加一小段首句等待。
- 发布时设备没有建立 WebSocket 连接，因此真实喇叭、眼睛情绪和首句延迟需要设备下次唤醒后现场确认。
