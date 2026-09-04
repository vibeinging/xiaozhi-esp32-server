# 双眼情绪控制发布报告

日期：2026-09-02

## 结论

服务器已经能稳定向设备发送与回答内容对应的眼睛情绪：

- 小布每次回复首字符输出一个固定集合内的情绪符号；
- 情绪符号会被现有 TTS 清理，不会从喇叭朗读；
- `🤩` 和 `⭐` 映射为 `excited`，供固件显示星星眼；
- 模型没有给出有效情绪符号时，从错误的默认 `happy` 改为安全的 `neutral`；
- 严肃和安全场景只能使用平静或难过眼神。

## 协议示例

```json
{"type":"llm","text":"🤩","emotion":"excited"}
```

固件原本已经支持接收 `emotion` 字段。本次服务器修改不改变 ASR、LLM 或 TTS 模型，也不改变音频协议。

## 测试

- 新增 3 个定向测试：星星眼、无标记回退中性、多个标记取第一个；
- 3 个测试全部通过；
- Ruff 检查通过；
- `git diff --check` 通过；
- 生产 Python 编译检查通过。

## 生产发布

当前版本：

```text
/opt/yingxiai/releases/v0.9.6-yiyiai-eye-emotion-v5
```

发布前备份：

```text
/opt/yingxiai/backups/20260902T0910-dual-eye-emotion
```

数据库检查结果：当前智能体和 5 个模板都已经包含“眼睛表情”规则。`yingxiai-server`、`yingxiai-manager`、`yingxiai-mysql`、`yingxiai-redis` 均为 `active`，网站返回 HTTP 200。

## 边界

服务器现在可以下发新情绪，但两个圆屏要显示新的蓝色猫眼、星星、爱心和泪滴，仍需使用编译后的新固件刷写真实硬件。刷机不在本次服务器发布中。
