# YIYI AI 控制台界面定制

基线：`xiaozhi-esp32-server v0.9.6`（`f5ed1aaec88471ba00ac778045331514066d63dc`）

## 修改内容

- 网页标题和顶部品牌改为 `YIYI AI`。
- 登录页改为暖色陪伴风格，保留原有登录、验证码、注册开关和语言切换逻辑。
- 登录字段增加可见标签和浏览器自动填充提示。
- 登录页增加桌面端与手机端响应式布局。
- 后台顶部、菜单选中颜色和版本页脚使用同一套视觉样式。
- 移除不再使用的旧登录图片引用，避免继续打包无用品牌素材。

## 修改范围

修改仅位于 `main/manager-web`：

- `.env`
- `src/views/login.vue`
- `src/views/auth.scss`
- `src/components/HeaderBar.vue`
- `src/components/VersionFooter.vue`
- `src/styles/global.scss`

后端接口、设备 WebSocket、OTA、ASR、LLM 和 TTS 逻辑没有改动。

## 验证命令

```bash
cd main/manager-web
npm ci --no-audit --no-fund
npm run check:i18n
npm run test:unit
npm run test:snapshot
npm run build
```

验证结果：国际化检查通过，5 个单元测试和 13 个快照测试通过，生产构建通过。构建仍会提示上游字体、唤醒词模型和部分图片体积较大，本次没有改这些资源。
