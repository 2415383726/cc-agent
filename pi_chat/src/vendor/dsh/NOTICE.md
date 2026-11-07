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
| `ui-workspace/src/client/rows/Rows.module.css` | 同名上游文件 | 会话列表行（32px 行、选中/悬停填充、行内重命名输入、时间戳与行操作按钮） |
| `ui-primitives/src/UserMessageBubble.module.css` | 同名上游文件 | 用户气泡面（--dsw-specific-bubble、radius-xl、10px 16px 内距） |
| `ui-primitives/src/DisclosureRow.module.css` | 同名上游文件 | 披露行头部（思考折叠行 24px 行、leading 图标/hover chevron 交换） |
| `ui-primitives/src/TextShimmer.module.css` | 同名上游文件 | 文本 shimmer 扫光（思考摘要流式态、打字指示） |
| `ui-primitives/src/markdown/MarkdownText.module.css` | 同名上游文件 | markdown 正则排版（标题/列表/表格/引用/行内码、compact 次级变体） |
| `ui-primitives/src/markdown/CodeBlock.module.css` | 同名上游文件 | 代码块卡（banner、infostring、复制按钮、pre 包装） |
| `ui-primitives/src/clipboard.ts` | 同名上游文件 | 剪贴板写入（async API + execCommand 回退，框架无关 pure TS） |
| `ui-chat/src/client/chat/MessageItem.module.css` | 同名上游文件 | 用户行/stack 布局、附件卡、错误行、压缩行等消息行样式 |
| `ui-chat/src/client/chat/MessageIconActions.module.css` | 同名上游文件 | 消息 IconActions 行（时钟 + 复制按钮 + hover 显隐） |
| `ui-chat/src/client/chat/AssistantMarkdown.module.css` | 同名上游文件 | 助手正文流（14/24、块间 16px、中断标记） |
| `ui-chat/src/client/chat/ReasoningRow.module.css` | 同名上游文件 | 思考折叠行（摘要单行截断、流式渐隐 mask、thinkBody 缩进） |
| `ui-chat/src/client/chat/TurnProcessNodeView.module.css` | 同名上游文件 | 终态头部行（33px、底部 0.5px 分隔、durationNumber 等宽） |
| `ui-chat/src/client/chat/accessibility.module.css` | 同名上游文件 | visuallyHidden |
| `ui-chat/src/client/chat/ChatView.module.css` | 同名上游文件 | 整文件保留；本票据仅引用 `.running/.runningContent/.runningText/.runningIcon` 打字指示片段 |
| `ui-tool/src/client/tool/components/ToolRow.module.css` | 同名上游文件 | 工具折叠卡（24px 摘要行、sep 点、IN/OUT ioCard、error/stopped 摘要着色、bodyScroll） |
| `ui-skill/src/client/SkillRow.module.css` | 同名上游文件 | 加载技能行（skill glyph、说明卡 instructionsCard/instructions） |
| `ui-chat/src/client/chat/ChatGroupSeat.module.css` | 同名上游文件 | 过程分组（组头 title/activityIcon+chevron 交换、body 滚动帽与渐隐 mask、content 行距） |
| `ui-primitives/src/Tag.module.css` | 同名上游文件 | 只读胶囊徽章（状态徽标复用 neutral/success/danger 等色调） |

CSS Modules 类名与选择器零改动；`onboarding.css`、`gradient-shadow-text.css`、
`shiki.css` 当前未被引用，仅随目录完整保留，后续票据按需引用。

## 重写部分（非拷贝）

- 上游 React 组件（InputBar.tsx、SidebarRoot.tsx、AppFrame.tsx、ConversationRoot.tsx 等）
  的 DOM 结构被忠实**重写为 Vue SFC**（`pi_chat/src/shell/`），类名引用保持一致；
  文案为 zh-CN 基线。Lexical 富文本编辑器未引入（取材黑名单），composer 文本面为
  原生 `<textarea>`，复用同一组 `.input/.scroll/.grow/.placeholder` 类。
- 票据 03：`pi_chat/src/timeline/` 按上游组件 DOM 蓝图重写为 Vue SFC
  （UserMessage/UserContent+MessageIconActions、AssistantMessage/AssistantMarkdown+
  RunningStatus、ReasoningRow+DisclosureRow（内联）、TerminalRow/TurnProcessNodeView、
  MarkdownContent/MarkdownText+CodeBlock、TextShimmer）。代码块/表格包装在
  `timeline/markdown.ts` 经 markdown-it renderer 规则生成（上游为 mdast 渲染器，
  本应用规格固定 markdown-it + highlight.js）。图标 `timeline/icons.ts` 的
  glyph path 逐字取自 ui-primitives icons/artwork.ts（内联常量，不引 sprite）；
  文案取自 ui-chat locale.ts zh 字典；`clock.ts` 平移 message-chrome.ts 的
  formatMessageClock/formatRunDuration；`scrollFollow.ts` best-effort 平移
  use-scroll-follow.ts 的 ScrollFollow（裁掉 WeakMap 归主/动画 retarget）。
- 票据 04：`pi_chat/src/timeline/` 新增 ToolCard/ToolGroupRow/SkillRow/CompactionRow
  Vue SFC（蓝图分别为 ui-tool GenericToolCard+ToolRow+DisclosureRow、ui-chat
  ChatGroupSeat+step-process、ui-skill SkillRow、ui-chat CompactionItem）。
  `timeline/toolModel.ts` 平移 ui-tool tool-call-model.ts 的纯函数子集
  （variant 分类/摘要派生/参数 JSON 格式化），`timeline/grouping.ts` 平移
  process-groups 的类别计数与 processTitle 拼装；文案取 ui-conversation/ui-chat/
  ui-skill locale zh 字典。上游 slot 装配（renderSlot/toolview 注册表）换成
  本组件内的简单 variant 分派；file/web/diff/search/terminal/image 专用卡不
  在本契约事件面内，统一走 generic IN/OUT 卡（偏离已注释）。
- `src/vendor/dsh/theme.css` 与 `pi_chat/src/styles/base.css` 是本项目的装配索引/
  挂载默认，不属于上游文件。

## 许可要点

- DeepSeek Harness 代码：MIT（见 `LICENSE`，保留版权声明）。
- Montserrat 字体：SIL Open Font License 1.1（见 `ui-theme/styles/Montserrat-OFL.txt`）。
- 字体从本目录本地加载（Vite 打包 woff2），不使用任何 CDN。
