# Vue / Nuxt Pi Web 客户端补充研究

调研时间：2026-10-29，最后核对 2026-10-29 00:05 UTC（Asia/Shanghai 08:05）。仅源码与公开 API 研究；只新增本文，未修改实现、规格或工单，未安装、运行、构建候选应用。

约束沿用：Dify Python 插件使用 Pi core-lc / harness-lc 0.6.0；每环境一个离线 difypkg；不增加常驻 Pi/Node/WebSocket 后端。界面应体现 Agent 在工作，重点复用聊天、思考、工具/Skills 的调用与进度、AskUser 等成熟交互；不要求保留旧卡片，也不要求重新绘制所有 Vue 组件。

## 结论与推荐

**确实存在真正的 Vue/Nuxt Pi 客户端。按本次源码核查，建议把 Leyline 的静态 Vue 聊天组件作为 Vue 首选基线，替换 Dify controller，补结构化 AskUser；jmfederico 保留为问答记录/表单行为参考与后备。** Leyline 的工具、技能、思考、图片、聚合轨迹、输入框已有可复用实现，组件具备 props/emits 接缝，根许可证为 Apache-2.0。其完整服务不适合搬入本项目，但浏览器本身不运行 Agent；可保留成熟客户端展示层，不必保留原 Node/Pi 后端。[Leyline README](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/README.md#L3)、[许可证](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/LICENSE)、[TranscriptEntry 接口](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L29)、[SessionComposer 接口](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/SessionComposer.vue#L12)

这比最初只比较 React/Lit 样本时多出一个实质选择。**不能说只补一张问卷卡就直接完成替换**：仍需抽取聊天组装、替换会话/流控制层、保留 Dify 的持久恢复语义、解耦一处 Pi 包内高亮资源。静态研究未发现不可解的许可或构建障碍，但未证明抽取后的 build 已通过。首个实施验收应是抽取构建与事件回放，验证工具、Skills、问卷和会话恢复；通过后再固化为主要客户端。[App 中聊天组装](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/App.vue#L4768)、[controller 与原 API 耦合](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/composables/useSessionWorkspace.js#L11)、[高亮资源路径](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/lib/transcript.js#L1)

本次未找到另一个**许可明确、同时已有工具/Skills 与完整结构化 AskUser、且在已核查路径中更易直接复用**的 Vue/Nuxt 候选。这个结论仅限下面列明的搜索范围，不表示全生态不存在。stars 仅是检索快照，不作为成熟度或质量证明。

## 有界搜索范围

GitHub connector 查询了：

- `"pi coding agent" vue`
- `"pi-coding-agent" language:Vue`
- `"pi agent" nuxt`
- `"pi-web" vue`
- `"pi-coding-agent" vue in:readme sort:stars`
- `"pi-mono" language:Vue`
- `"pi-web" language:Vue`
- `"pi-coding-agent" nuxt in:readme`

每个查询最多读取 30 个结果，另用公开网页搜索 `site:github.com "pi-coding-agent" "Vue" "web"` 等补足 GitHub 仓库语言分类与 README 搜索的漏项。对四个主要候选读取 README、package.json、固定 commit 的目录树与相关源码；Leyline、pi-web-vue、pi-simple-web 均为真正 Pi 浏览器客户端，Gdou 是可通过浏览器连接其本地桥的 Vue 桌面工作台。

也查询官方 [Package Catalog](https://pi.dev/packages)。按该页面实际表单参数 `name` 过滤，[vue](https://pi.dev/packages?name=vue) 得到四项（pi-polyglot-lsp、nue-ui-skill、lsp-pi、pi-frontend-kpc-agent），均是 LSP/界面开发技能或 Pi 扩展，不是现成聊天客户端；[nuxt](https://pi.dev/packages?name=nuxt) 本次返回零项。目录过滤只覆盖名称、描述、作者，不检索全部源码，也不能覆盖所有未发布 npm 的 GitHub 项目。目录计数会变化，不据此断言没有 Vue 产品。

筛掉了 Raspberry Pi/Pi Network、一般 Vue LLM 聊天页、仅因使用 Pi 开发而提到 Pi 的仓库。另有：

- `tickernelz/dinotty-omp` 是 Oh My Pi 的会话 HUD/技能面板插件，不是本次目标的独立 Pi Web 聊天客户端。[REST](https://api.github.com/repos/tickernelz/dinotty-omp)
- `Danmoreng/qwen3-8-27b-iq3-xxs-vs-bonsai` 是本地模型 benchmark，不能因为 GitHub language=Vue 就算客户端。[REST](https://api.github.com/repos/Danmoreng/qwen3-8-27b-iq3-xxs-vs-bonsai)
- `intelliriffer/pi-omlx-model-manager` 管理 models.json，不是会话/工具/AskUser UI。[README](https://github.com/intelliriffer/pi-omlx-model-manager)
- `ckvv/lumos-agent` 是真实 Vue/Electron Pi Agent 工作台，README 声明 MIT，但依赖 Electron 主进程、oRPC、SQLite 和账户启动模型；本次未深入核查其独立浏览器抽取成本，不把它当作已验证 Web 基座。[README](https://github.com/ckvv/lumos-agent/blob/main/README.md)

## 四个候选快照与实际能力

以下 stars、updated_at、pushed_at 来自当天 GitHub REST 接口；updated_at 不等于代码最近提交。

| 仓库 | stars | updated_at（UTC） | pushed_at（UTC） | 许可元数据 |
| --- | ---: | --- | --- | --- |
| [spmurrayzzz/leyline](https://github.com/spmurrayzzz/leyline) | 5 | 2026-10-28T23:14:01Z | 2026-10-28T23:13:57Z | Apache-2.0 |
| [saohuahua/pi-web-vue](https://github.com/saohuahua/pi-web-vue) | 1 | 2026-10-15T06:51:23Z | 2026-10-15T06:51:19Z | REST 未识别 |
| [Barbapapazes/pi-simple-web](https://github.com/Barbapapazes/pi-simple-web) | 1 | 2026-10-17T23:23:36Z | 2026-10-17T23:23:33Z | REST 未识别 |
| [NaLanBoO0/Gdou-agent](https://github.com/NaLanBoO0/Gdou-agent) | 2 | 2026-10-09T12:59:59Z | 2026-10-09T12:59:55Z | REST 未识别 |

元数据：[Leyline](https://api.github.com/repos/spmurrayzzz/leyline)、[pi-web-vue](https://api.github.com/repos/saohuahua/pi-web-vue)、[pi-simple-web](https://api.github.com/repos/Barbapapazes/pi-simple-web)、[Gdou](https://api.github.com/repos/NaLanBoO0/Gdou-agent)。

| 候选 | package.json / 架构核查 | 工具 / Skills / AskUser | 对当前项目的判断 |
| --- | --- | --- | --- |
| **Leyline** | Vue 3.5.34 + Vite 8；Node 22.19；服务端 Pi coding-agent 1.2.0；HTTP + WebSocket；可选 Electron | 原生工具状态、预览/diff/图片/聚合；技能调用与 read/read-skill 特殊卡；扩展 confirm 有完整 UI，但 select/input 是空实现，未发现完整多题 AskUser 往返 | **Vue 首选复用基线**；抽静态聊天组件，加 Dify controller 与结构化问卷卡；不带原服务 |
| **saohuahua/pi-web-vue** | Nuxt 4.5 + Vue 3.5 + Pinia；官方 Pi SDK 0.85.1；服务端 Node + SSE；参考 agegr | 工具卡、activeTools 真实 start/end、实时输出、思考、队列、分支、技能管理与 slash 目录；检查的核心协议/命令分发没有结构化 AskUser renderer/response 通道 | 可参考 Vue/Nuxt 的事件与卡片；未找到自有代码的明确许可，且缺少问卷接缝，不能仅因 Vue 就当首选整体复制 |
| **Barbapapazes/pi-simple-web** | Nuxt + Nuxt UI + Pinia Colada；web/api 分离两个 Nuxt app；服务端 Pi SDK；SSE/后台 run | 工具 ID 配对、状态、文字/思考、diff、会话恢复、队列；所读事件联合只有 queue/started/message/conversation/status/error/done，无结构化问卷事件；未见独立技能进度卡 | Nuxt 轻量会话/渲染实现可研究；未找到明确自有许可，也没有可直接复用的完整 AskUser |
| **NaLanBoO0/Gdou-agent** | Vue3/Vite 工作台 + Node 本地 JSON-RPC 2.0/WS 桥；Pi kernel vendored；Electron 可选壳 | 详细工具时间线、Skills Center/SkillToken/load_skill；UserQuestionComposer 有单/多选、自由文本、跳过和翻页 | 交互覆盖多，但原桥持有 AskUser Promise 与 rpc_id waiter；未找到自有代码许可，不能把 vendored Pi 的许可自动当作全仓许可 |

依据：

- Leyline：[package.json](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/package.json)、[工具/技能 UI](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L308)、[扩展 UI 方法](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/server/pi-api/extension-ui.js#L319)。
- pi-web-vue：[package.json](https://github.com/saohuahua/pi-web-vue/blob/9a2ccf6055b34337447824fd05c59405fdc3ffa1/package.json)、[工具 reducer](https://github.com/saohuahua/pi-web-vue/blob/9a2ccf6055b34337447824fd05c59405fdc3ffa1/app/stores/chat.ts#L442)、[工具卡](https://github.com/saohuahua/pi-web-vue/blob/9a2ccf6055b34337447824fd05c59405fdc3ffa1/app/components/ToolCallCard.vue#L42)、[SkillsPanel](https://github.com/saohuahua/pi-web-vue/blob/9a2ccf6055b34337447824fd05c59405fdc3ffa1/app/components/capabilities/SkillsPanel.vue#L1)、[命令分发](https://github.com/saohuahua/pi-web-vue/blob/9a2ccf6055b34337447824fd05c59405fdc3ffa1/server/utils/rpc-manager.ts#L202)。
- pi-simple-web：[web 依赖](https://github.com/Barbapapazes/pi-simple-web/blob/8830b37a610b1817e7a2580e32f358a377660738/apps/web/package.json)、[README](https://github.com/Barbapapazes/pi-simple-web/blob/8830b37a610b1817e7a2580e32f358a377660738/README.md)、[事件联合](https://github.com/Barbapapazes/pi-simple-web/blob/8830b37a610b1817e7a2580e32f358a377660738/packages/shared/src/conversations/types/conversation.ts#L8)、[工具卡](https://github.com/Barbapapazes/pi-simple-web/blob/8830b37a610b1817e7a2580e32f358a377660738/apps/web/modules/conversations/runtime/app/components/ConversationTool.vue#L1)。
- Gdou：[Vue 依赖](https://github.com/NaLanBoO0/Gdou-agent/blob/e9c62e4c3a07cc1cf170dea2bd4eacec3d2733fb/shell/package.json)、[工具卡](https://github.com/NaLanBoO0/Gdou-agent/blob/e9c62e4c3a07cc1cf170dea2bd4eacec3d2733fb/shell/src/components/timeline/ToolCallCard.vue#L1)、[load_skill](https://github.com/NaLanBoO0/Gdou-agent/blob/e9c62e4c3a07cc1cf170dea2bd4eacec3d2733fb/src/tools/load-skill.ts#L34)、[问卷组件](https://github.com/NaLanBoO0/Gdou-agent/blob/e9c62e4c3a07cc1cf170dea2bd4eacec3d2733fb/shell/src/components/UserQuestions/UserQuestionComposer.vue#L11)、[桥接等待](https://github.com/NaLanBoO0/Gdou-agent/blob/e9c62e4c3a07cc1cf170dea2bd4eacec3d2733fb/bridge/server.ts#L207)。

许可边界：Leyline 的根 LICENSE 是 Apache-2.0。其余三个 REST license=null，固定目录树没有自有 LICENSE/COPYING；pi-web-vue 的 THIRD_PARTY_NOTICES 明确仅记录从 agegr 移植的模块及其 MIT 文本，不能据此把新写的全部 Vue 代码认定为 MIT。可读作参考，但本次不把它们列为许可已明确的复制来源。[Leyline LICENSE](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/LICENSE)、[pi-web-vue notices](https://github.com/saohuahua/pi-web-vue/blob/9a2ccf6055b34337447824fd05c59405fdc3ffa1/THIRD_PARTY_NOTICES.md#L1)、[pi-web-vue 树](https://api.github.com/repos/saohuahua/pi-web-vue/git/trees/9a2ccf6055b34337447824fd05c59405fdc3ffa1?recursive=1)、[pi-simple-web 树](https://api.github.com/repos/Barbapapazes/pi-simple-web/git/trees/8830b37a610b1817e7a2580e32f358a377660738?recursive=1)、[Gdou 树](https://api.github.com/repos/NaLanBoO0/Gdou-agent/git/trees/e9c62e4c3a07cc1cf170dea2bd4eacec3d2733fb?recursive=1)。

## Leyline：实际架构、组件与复用接缝

### 浏览器不运行 Agent

浏览器入口只创建 Vue App；AgentSession、模型凭据、文件、终端、MCP 和内存等由 Node 服务持有。生产服务通过 node:http 建立 HTTP server，并配置 WS；开发时 Vite plugin 挂接 Pi API。可选 Electron 也把后台放在 utility process。**复用静态 Vue 组件不必复用这套运行服务，也不意味着模型或工具在浏览器执行。**[浏览器入口](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/main.js#L1)、[Node 服务](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/server/leyline-server.js#L1)、[Vite 配置](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/vite.config.js#L1)、[SDK runtime](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/server/pi-api/runtime.js#L83)、[README 后台说明](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/README.md#L177)

### 已有工具与 Skills 交互

TranscriptEntry 接收 entry、toolStatus、toolExpanded、skillExpanded 等 props，发出 copy、edit、fork、reset、retry、toggle-tool、toggle-skill、open-image、open-tool-fullscreen 等事件；展示组件自身没有创建 SDK session。工具卡区分 running/completed/error/stopped/unknown，支持命令、路径、展开、JSON/文本、图片、diff/预览及全屏；MobileToolActivity 将多个工具聚合显示。[组件接缝](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L29)、[工具状态与展开](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L308)、[通用结果体](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L449)、[工具聚合逻辑](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/lib/tool-activity.js#L87)

Skills 不只是管理页：投影识别 `<skill ...>` 调用和 `/skill:`，read/read-skill 指向 skills/.../SKILL.md 时标注技能；TranscriptEntry 显示专用技能工具卡、状态和可折叠调用内容。当前 Python 的技能激活/资源读取不一定叫 read(path)，需由 Dify adapter 映射真实技能事件，不能盲用路径规则，也不能臆造执行百分比。[技能解析](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/lib/transcript-projection.js#L285)、[加载识别](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/lib/transcript-projection.js#L326)、[技能工具 UI](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L322)、[技能调用 UI](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L471)

LiveAssistantMessage 接收 blocks/streaming 等 props，并发出 copy/fork/open-image/reset；可保留流式思考与答案交互。SessionComposer 是 props/emits，提供 draft、agentRunning、contextUsage、附件、模型/思考与队列状态，发出 submit/interrupt/update:draft 等事件；但现有输入框还有 dictation、research、terminal 等工作台功能，抽取时应将不使用的宿主能力改为可选或隐藏，并保留有价值的输入体验。[流式组件](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/LiveAssistantMessage.vue#L6)、[输入框 props](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/SessionComposer.vue#L12)、[输入框 emits](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/SessionComposer.vue#L157)

### 原协议与 Dify controller 替换范围

原应用要求 API v2 与 WebSocket。浏览器 `useRuntimeEvents` 连接 `/api/pi/events?sessionId=...`，处理 active_session、runtime_event、runtime_roster、runtime_removed、extension_ui/error；runtime_event 内包含原始 Pi 消息/工具生命周期。useLiveTurnProjection 维护实时消息、工具、活动状态，接收 snapshot 与事件，并通过 onIntent 通知宿主刷新/滚动。它没有网络请求，可保留其投影/合并思路或部分函数，但输入模型仍需适配。[WS composable](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/composables/useRuntimeEvents.js#L10)、[事件分发](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/composables/useRuntimeEvents.js#L75)、[无网络投影入口](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/composables/useLiveTurnProjection.js#L1)、[工具生命周期合并](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/composables/useLiveTurnProjection.js#L567)、[投影导出](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/composables/useLiveTurnProjection.js#L1265)

| 原 Leyline 能力 | 原接口 / 状态 | 当前复用边界 |
| --- | --- | --- |
| 列表、会话选择、历史 | GET /api/pi/projects、/sessions、/sessions/:id；POST /active-session；会话 path/cwd、entries、snapshotRevision | 新 Dify controller 提供 conversation/thread 与历史；无需模拟真实本机工作区 |
| 实时 Agent 工作状态 | WS /api/pi/events；active_session/runtime_event；state 含 isStreaming、pendingTools、queue、activity | Dify HTTP 流映射为 UI 事件与状态；不增加 WS 后台 |
| 发送/停止/队列 | POST /api/pi/sessions/:id/prompt；session action 路由、queue；输入框 submit/interrupt emits | 由现有 Dify 发送/停止/后续输入能力接管；不暴露没有后端等价能力的动作 |
| 模型与设置 | /api/pi/state、models、thinking、provider/settings 等 | 按 Dify 的配置权限保留显示或裁掉设置；不能导入原凭据管理 |
| 结构化问卷 | 原产品只有扩展确认回路；不存在已核查的完整多题 AskUser | 新的工具结果问卷卡 + Dify resume/answer 回调，不沿用扩展 Promise |
| 工作台 | 文件、Git、终端、memory、research、dictation、traces、多 backend | 可按实际价值选择性复用展示；不是完成聊天/工具/Skills/AskUser 的服务前置条件 |

依据：[客户端 API](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/lib/pi-api.js#L1)、[激活与状态](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/lib/pi-api.js#L131)、[发送与队列](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/lib/pi-api.js#L255)、[runtime DTO](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/server/pi-api/dtos.js#L48)、[原会话 controller](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/composables/useSessionWorkspace.js#L11)。

### AskUser 可以补成普通工具结果中的结构化卡

**可以补，而且不需要复制原 extension UI 的长期 Promise 协议。** 这是基于现有组件接缝的适配推断，不是已有功能声明：

1. Dify controller 从当前持久 pending/工具结果中构造结构化问卷 entry，保留 request ID、题目/选项、状态和已提交结果；刷新时从 Dify 权威历史/状态重建。
2. 在 TranscriptEntry 或其上层聊天组装里将相应自定义工具结果路由到一个 Vue 问卷表单，保持其他工具卡、思考、Skills 和滚动逻辑。
3. 表单通过 submit/cancel emit 交付给 Dify controller，调用现有 answer/resume 流程，服务端配对、同批工具与幂等仍由 Python 插件处理。
4. 原通用工具结果渲染只展示文本/JSON，不能仅塞 JSON 就宣称用户已有可操作问卷；必须增加真正的表单与状态。原 `projectMessageEntry` 也没有保留所有 toolResult.details，需显式透传问卷的安全结构，不能在投影时丢掉。

可参考 jmfederico 的 question/option ID、自由文本/多选、草稿、部分作答、历史结果，以及“问题作为完成结果”的数据形状；**不等于采用其允许重复回答或仅依赖 terminate 的后端语义**。Dify 的 pending 恢复仍是当前项目自己的契约。[Leyline 通用结果渲染](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L449)、[当前结果投影](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/lib/transcript-projection.js#L137)、[jmfederico AskUserCard](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/AskUserCard.ts#L97)、[jmfederico 问答类型](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/shared/apiTypes.ts#L798)、[jmfederico 语义限制研究](community-web-comparison.md#深看二jmfederico-的-askuser-完整调用链)。

Leyline 原 `extension-ui.js` 只将 confirm 转成 pending Map + Promise + boolean 回答；select/input 返回 undefined。这条路线是扩展确认，不是目标结构化 AskUser。其进程内 waiter 不能作为 Dify 持久恢复机制。[确切方法实现](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/server/pi-api/extension-ui.js#L319)、[原等待实现](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/server/pi-api/extension-ui.js#L243)。

### 构建与抽取的实际工作，未发现硬障碍

Leyline 没有独立的聚合 ChatView，聊天列表/聚合/流式组件的组装在约 5,857 行 App.vue 中；useSessionWorkspace 约 2,004 行且直接 import 原 REST API。实际应抽出一层聊天容器，复用其 props/emits 子组件、投影、样式、滚动/展开等模块，再接 Dify controller，而不是保留整个 App.vue 并只换 WS URL。[聊天模板](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/App.vue#L4768)、[原 composable](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/composables/useSessionWorkspace.js#L1)。

`src/lib/transcript.js` 的第 3 行直接 import `../../node_modules/@earendil-works/pi-coding-agent/dist/core/export-html/vendor/highlight.min.js?raw`。这是浏览器构建时读取 SDK 包内静态资源，不是浏览器执行 Agent。静态 UI 抽取要替换/独立提供高亮资产，并核对该资产的上游许可；这样才能去掉只为构建资源而牵入的完整 Pi SDK 安装。其他保留依赖包括 Vue、MarkdownIt、Pierre diff/preview、工具/技能投影与 CSS；应按实际引用裁剪，不能只复制三个 .vue 文件。[具体资源路径](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/lib/transcript.js#L1)、[依赖清单](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/package.json)。

Apache-2.0 是明确的可复用许可证；保留许可证/归属和需要的 notices，记录改动来源。当前未发现必须维持其后台或禁止静态组件抽取的条件。此处是仓库许可事实核对，未完成所有第三方资源的逐项许可盘点。[LICENSE](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/LICENSE)。

## 与 jmfederico 核心 + Dify controller 的成本比较

| 方面 | Leyline Vue 核心 | jmfederico Lit 核心 |
| --- | --- | --- |
| 现有项目框架 | 原生 Vue3/Vite，能保留现有 Vue 工程经验，避免额外框架桥接 | Lit 可在 Vue 消费，但需注册自定义元素、属性/回调桥与样式隔离验收 |
| 可复用工作感 | 工具/Skills 卡、聚合轨迹、状态、流式思考、图片、预览、输入已有实现 | 工具/Skills、运行状态、思考、图片、输入与完整 AskUser 已有实现 |
| 聊天聚合接缝 | 需从 App.vue 抽聊天容器；子组件 props/emits 清楚 | 已有集中 ChatView props/callbacks，抽取边界更直接 |
| AskUser | 需补结构化 Vue 表单与问卷结果投影；可借鉴已有语义 | 表单与历史答案已完成，仍需映射 Dify 恢复语义 |
| 网络/后端耦合 | 原 REST/WS composable 全替换，不能带 Node/Pi 后台 | 原 REST/WS/controller 全替换，不能带 session daemon |
| 构建依赖 | 需替换 Pi 包内 raw 高亮资产，收拢 Vue/CSS/预览模块 | 需收拢 Lit/本地化/插件样式/格式化与共享类型 |
| 静态判断 | **中等适配，Vue 偏好下优先** | **中等适配，问卷与集中接口优势；明确后备** |

这不是按 stars 给质量评分，也不是工时承诺。Vue 同构带来的维护收益与 Leyline 的实际 UI 覆盖足以支持把它提升为首选静态组件基线；jmfederico 更集中的 ChatView 和现成问卷使它仍是有价值的后备。两者都不能省略 Dify controller 与持久状态适配。[Leyline 接口](https://github.com/spmurrayzzz/leyline/blob/a368c8b7590b88bb138c024b7dd8414b3dcc2a73/src/components/TranscriptEntry.vue#L29)、[jmfederico ChatView](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ChatView.ts#L117)、[jmfederico PromptEditor](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/PromptEditor.ts#L59)。

## Vue 外壳消费现成 Lit Web Components 的可行范围

这是后备路线，**不要求把 Lit 组件转写成 Vue**。Vue 官方文档明确支持消费自定义元素；Vite 编译配置可将选定标签标为 isCustomElement。messages/status/问卷对象和函数回调应传 DOM properties，必要时用 .prop；不能把对象序列化成 HTML attribute，也不能把 onSubmitAsk 属性误当成组件一定会 dispatch 的 submit 事件。[Vue 官方：使用自定义元素](https://vuejs.org/guide/extras/web-components.html#using-custom-elements-in-vue)、[DOM properties](https://vuejs.org/guide/extras/web-components.html#passing-dom-properties)、[jmfederico 实际回调属性](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ChatView.ts#L149)。

可行范围是让 Vue 管应用路由/登录/Dify controller，让 Lit ChatView、PromptEditor 或单独 AskUserCard 管内部展示。两边共享结构化 DTO 和显式回调，Dify 仍掌握权威会话状态。原 jmfederico 组件不是无依赖 npm 黑盒，还依赖本地化、主题、插件样式和格式化模块；需要抽取/打包后使用。Nuxt/SSR 场景还要把依赖 HTMLElement/customElements 的组件放在客户端初始化边界。[实际 import/样式依赖](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ChatView.ts#L1)、[AskUserCard](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/AskUserCard.ts#L1)。

未验证项：真实 Vue/Lit 混用 build、TS decorator 配置与自定义元素注册时机、对象/函数属性更新、Shadow DOM/CSS 变量与字体、本地化单例、挂载/卸载后的监听清理、焦点与键盘、滚动定位、刷新/切会话、附件 URL 和问卷提交失败恢复。本文没有编写或运行嵌入示例，不把框架文档的通用支持等同于本仓库已验收。

## 固定源码快照与后续验收

| 仓库 | 固定 commit |
| --- | --- |
| spmurrayzzz/leyline | [a368c8b7590b88bb138c024b7dd8414b3dcc2a73](https://github.com/spmurrayzzz/leyline/commit/a368c8b7590b88bb138c024b7dd8414b3dcc2a73) |
| saohuahua/pi-web-vue | [9a2ccf6055b34337447824fd05c59405fdc3ffa1](https://github.com/saohuahua/pi-web-vue/commit/9a2ccf6055b34337447824fd05c59405fdc3ffa1) |
| Barbapapazes/pi-simple-web | [8830b37a610b1817e7a2580e32f358a377660738](https://github.com/Barbapapazes/pi-simple-web/commit/8830b37a610b1817e7a2580e32f358a377660738) |
| NaLanBoO0/Gdou-agent | [e9c62e4c3a07cc1cf170dea2bd4eacec3d2733fb](https://github.com/NaLanBoO0/Gdou-agent/commit/e9c62e4c3a07cc1cf170dea2bd4eacec3d2733fb) |
| jmfederico/pi-web（前次主调研） | [762bbfdc5e7736fe90f33abd2e19e950d5f4d496](https://github.com/jmfederico/pi-web/commit/762bbfdc5e7736fe90f33abd2e19e950d5f4d496) |

建议的第一道实施门：**只抽静态 Leyline 聊天核心，先通过独立前端 build，再用固定 Dify 事件回放验证文本/思考、并行工具起止与 partial、技能激活/读资源、AskUser/答案、断线恢复与会话切换。** 这一步不需要启动 Leyline Node 后台或在浏览器运行 Agent。源码研究支持这条路线值得执行；能否保持完整交互且降低维护成本，应由该验收给出实证。
