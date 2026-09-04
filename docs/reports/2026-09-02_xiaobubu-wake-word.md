# “小布布”唤醒词改造与发布记录

日期：2026-09-02  
目标硬件：正晨 MiniCam 1.28 英寸双屏，Wi-Fi 与 ML307/4G 两种版本  
线上服务：`https://yiyiai.mediaprogram.cn/`

## 结论

唤醒词已从“喵喵同学”改为“小布布”。

这项修改分为两层：

1. 设备固件使用中文命令词模型识别 `xiao bu bu`，识别成功后向服务器上报“小布布”。
2. 服务器唤醒词列表加入“小布布”并移除“喵喵同学”。

只改服务器不能改变设备本地的声音识别。设备必须刷入新固件后，才会真正通过“小布布”唤醒。

## 固件修改

仓库：`vibeinging/xiaozhi-esp32-firmware`  
分支：`feature/dual-eye-emotions`  
提交：`54038ec feat: 将唤醒词改为小布布`

修改了两种硬件：

- `zhengchen-minicam-128`
- `zhengchen-minicam-ml307-128`

主要配置：

- 识别拼音：`xiao bu bu`
- 中文展示及上报：`小布布`
- 中文识别模型：MultiNet 7
- 识别阈值：20
- 保留唤醒声音数据上报

云端构建：[GitHub Actions #33578809898](https://github.com/vibeinging/xiaozhi-esp32-firmware/actions/runs/33578809898)

两个构建任务均成功。构建日志已确认：

- 自定义唤醒词为 `xiao bu bu (小布布)`。
- `mn7_cn` 中文模型和 `fst` 已打入资源包。
- Wi-Fi 和 ML307/4G 版都已生成 `merged-binary.bin`。

本地成品目录：

```text
/Users/Four/PersonalProjects/一一玩偶计划/firmware-builds/54038ec-xiaobubu
```

SHA-256：

- Wi-Fi：`2e6d3693e6f53b6e5fc8a47bf9f872fb2e6e74106d324ab1121feb8c0f2c1b5a`
- ML307/4G：`73fcd7d7ceec9f19065cca2d79f1471a25ab3882077e18ad433a835713dc32b4`

## 服务器修改与部署

仓库：`vibeinging/xiaozhi-esp32-server`  
分支：`feature/yiyi-ai-console`  
提交：`59e04347 feat: 配置小布布唤醒词`

线上版本：

```text
/opt/yingxiai/releases/v0.9.6-yiyiai-wake-word-v6
```

上一版本：

```text
/opt/yingxiai/releases/v0.9.6-yiyiai-eye-emotion-v5
```

备份：

```text
/opt/yingxiai/backups/20260902T0930-wake-word
```

数据库当前词表已包含“小布布”，不再包含“喵喵同学”；其他通用唤醒词保持不变。

## 验证

- 两份硬件配置均通过 JSON 解析。
- 两种硬件都已通过云端完整编译和成品上传。
- 编译日志已确认自定义唤醒词和中文 MultiNet 7 模型实际打入。
- 两个仓库均通过 `git diff --check`。
- 线上数据库词表已读回确认。
- `yingxiai-server`、`yingxiai-manager`、`yingxiai-mysql`、`yingxiai-redis` 均为 `active`。
- 智控台与 OTA 地址均返回 HTTP 200。
- 语音服务重启后没有出现 ERROR、Traceback 或 Exception。

## 尚未执行

没有给真实设备刷固件，也没有把新包放进会自动升级的 OTA 入口。刷写会改变设备，需取得明确同意后再执行。
