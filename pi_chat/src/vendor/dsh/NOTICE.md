# Vendored assets: DeepSeek Harness 展示基座

本目录内的文件按「逐字优先」原则从 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
（MIT 许可）拷贝而来，未做样式改写；来源与范围如下。

## 来源

- 仓库：`deepseek-ai/deepseek-harness`，`master` 分支压缩包快照
  （下载于 2026-11-07；其中 `@deepseek-ai/dsh-client-ui-theme` 版本 `0.2.2-rc.1`）。
- 快照经 codeload tarball 获取，未保留上游 git 元数据，因此未能逐文件标注 commit；
  上游版本以 `ui-theme/package.json` 的 `0.2.2-rc.1` 为准。

## 拷贝范围（逐字未改）

| 本目录路径 | 上游路径 | 说明 |
| --- | --- | --- |
| `LICENSE` | 仓库根 `LICENSE` | 整仓 MIT 许可（Copyright (c) 2026 DeepSeek） |
| `ui-theme/styles/`（全部文件） | `packages/client/ui-theme/src/styles/` | `--dsw-*` 设计令牌（design-platform.css）、基础变量与圆角（base.css）、Montserrat `@font-face`（brand-font.css）、corner-shape/focus/scrollbar 等，含三个 `montserrat-*.woff2` 字体文件与 `Montserrat-OFL.txt` |
| `ui-layout/src/client/AppFrame.module.css` | 同名上游文件 | 三栏 grid 壳（侧栏列 / 中心列 / 右栏列） |
| `ui-sidebar/src/client/SidebarRoot.module.css` | 同名上游文件 | 侧栏根布局（logo 行、新会话按钮、滚动区、底部区） |
| `ui-conversation/src/client/skeleton/ConversationRoot.module.css` | 同名上游文件 | 会话列（头部 76px、滚动体、composer 座位） |
| `ui-conversation/src/client/skeleton/InputBar.module.css` | 同名上游文件 | 输入卡（圆角面板卡、工具行、发送按钮） |

CSS Modules 类名与选择器零改动；`onboarding.css`、`gradient-shadow-text.css`、
`shiki.css` 当前未被引用，仅随目录完整保留，后续票据按需引用。

## 重写部分（非拷贝）

- 上游 React 组件（InputBar.tsx、SidebarRoot.tsx、AppFrame.tsx、ConversationRoot.tsx 等）
  的 DOM 结构被忠实**重写为 Vue SFC**（`pi_chat/src/shell/`），类名引用保持一致；
  文案为 zh-CN 基线。Lexical 富文本编辑器未引入（取材黑名单），composer 文本面为
  原生 `<textarea>`，复用同一组 `.input/.scroll/.grow/.placeholder` 类。
- `src/vendor/dsh/theme.css` 与 `pi_chat/src/styles/base.css` 是本项目的装配索引/
  挂载默认，不属于上游文件。

## 许可要点

- DeepSeek Harness 代码：MIT（见 `LICENSE`，保留版权声明）。
- Montserrat 字体：SIL Open Font License 1.1（见 `ui-theme/styles/Montserrat-OFL.txt`）。
- 字体从本目录本地加载（Vite 打包 woff2），不使用任何 CDN。
