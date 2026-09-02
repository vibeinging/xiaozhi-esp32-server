# Serena 音色发布报告

日期：2026-09-02

## 结论

已将“小布”的生产 TTS 音色从 `Momo` 切换为 `Serena`。模型、语速、音调、音量、50% 随机猫叫和儿童安全规则均未改变。

## 生产状态

- 域名：`https://yiyiai.mediaprogram.cn/`
- 发布目录：`/opt/yingxiai/releases/v0.9.6-yiyiai-serena-voice-v7`
- 数据库备份：`/opt/yingxiai/backups/20260902-100322-serena-voice/before-serena.sql`
- 模型：`qwen3-tts-flash-realtime`
- 音色：`Serena`
- 语速 / 音调 / 音量：`1.0 / 1.0 / 50`
- 随机猫叫：开启，普通轻松回复的概率为 `0.5`
- 目标智能体音色：`TTS_Qwen3Realtime_Serena`
- 5 个相关智能体模板音色：`TTS_Qwen3Realtime_Serena`
- `Momo` 音色记录保留，可使用回滚 SQL 恢复。

## 验收结果

- `yingxiai-server`、`yingxiai-manager`、`yingxiai-mysql`、`yingxiai-redis` 均为 `active`。
- 公网 HTTPS 首页返回 `200`。
- 语音服务启动后日志中 `ERROR`、`Traceback`、`Exception` 数量为 0。
- 服务器实际运行环境执行 9 个百炼实时 ASR/TTS 单测，全部通过。
- 只删除 `TTS_Qwen3Realtime`、`Momo` 和 `Serena` 对应的精确缓存键，没有清空 Redis。
- 本次没有使用孩子的真实声音、对话或家庭数据。

## 过程记录

第一次执行迁移时，MySQL 客户端没有显式使用 `utf8mb4`，中文显示名被错误计长，数据库在提交前拒绝了写入。当时发布链接和服务未切换，事务回滚后仍为 `Momo`。改用 `--default-character-set=utf8mb4` 后迁移成功。

## 待现场确认

发布后的几分钟内没有看到硬件重新连入日志。因此，服务端切换已确认，但扬声器上的实际听感需要在设备下次连接并唤醒“小布布”后确认。
