# 布偶猫音色与随机猫叫发布报告

> 后续更新：现场试听认为 `Momo` 的撒娇搞怪感过重，生产音色已改为更温柔的 `Serena`。本文保留当时发布 `Momo` 的历史记录。

日期：2026-09-02

## 结论

小布已切换到更贴合布偶猫 AI 宠物的 `Momo（茉兔）` 音色，并增加真实的服务端随机规则：

- 每次普通、轻松的回复独立抽取一次；
- 50% 概率在完整回复后追加“喵～喵～”；
- 危险、受伤、身体不适、被欺负、隐私和求助等严肃内容的概率固定为 0%；
- 回复本身已有猫叫时不再重复追加；
- LLM 保持 `qwen3.7-flash`，没有修改。

Prompt 里保留了相同的 50% 规则，用来告诉模型这个角色习惯。随机抽取不依赖模型“自己猜”，由 TTS 服务代码执行，因此可以确实达到设定概率。

## 音色选择

最终选择 `Momo`，因为它比通用年轻女声更俏皮、亲近，更像毛绒玩偶里的小猫伙伴。

对比过两条百炼实时 TTS 路线：

- `qwen3-tts-flash-realtime + Momo`：首个音频分片约 380 毫秒；
- `qwen3-tts-instruct-flash-realtime + Momo + 音色指令`：首个音频分片约 2.7 秒。

为避免回复变慢，生产继续使用 `qwen3-tts-flash-realtime`。

## 代码与配置

本次改动包括：

- TTS Provider 增加 `cat_meow_enabled` 和 `cat_meow_probability`；
- 连接层把当前用户问题传给 TTS，用于严肃内容判断；
- Prompt 增加 50% 随机猫叫与安全场景 0% 规则；
- 管理端模型配置和当前设备智能体音色改为 `Momo`。

可重放的配置文件：

```text
deploy/yingxiai/roles/ragdoll-cat-xiaobu.prompt.txt
deploy/yingxiai/migrations/2026-09-02-ragdoll-cat-voice-momo.sql
deploy/yingxiai/migrations/2026-09-02-ragdoll-cat-voice-momo.rollback.sql
```

## 测试

- Python 编译检查通过；
- 相关 Ruff 检查通过；
- 11 个定向单元测试全部通过，包含 9 个实时语音/随机猫叫测试和 2 个音频解码选择测试；
- 测试覆盖 49% 随机数命中、50% 随机数不命中、严肃话题不猫叫、已有猫叫不重复；
- 严肃测试输入“插座好像漏电”时，回复正常提示离开危险并找大人，没有猫叫；
- 测试只用了虚构文字和合成语音，没有使用孩子的真实声音。

## 生产发布

当前版本：

```text
/opt/yingxiai/releases/v0.9.6-yiyiai-ragdoll-voice-v4
```

发布前备份：

```text
/opt/yingxiai/backups/20260902T081732-ragdoll-voice
```

上一个稳定版本：

```text
/opt/yingxiai/releases/v0.9.6-yiyiai-realtime-speech-v3
```

上线后只删除了精确命中的 `TTS_Qwen3Realtime` 模型缓存键，没有清空 Redis。管理端实际运行配置已确认：

```text
model=qwen3-tts-flash-realtime
voice=Momo
private_voice=Momo
cat_meow_enabled=true
cat_meow_probability=0.5
prompt_has_50_percent=true
```

`yingxiai-server`、`yingxiai-manager`、`yingxiai-mysql`、`yingxiai-redis` 均为 `active`，`https://yiyiai.mediaprogram.cn/` 返回 HTTP 200。

## 现场验收边界

最后一次服务重启后，设备没有自动重连，很可能处于休眠或断电状态。软件侧的模型、音色、随机规则和安全规则已验证；物理喇叭是否能听到、音量和听感仍需要唤醒设备后现场确认。
