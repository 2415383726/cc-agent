# Pi 社区 Web 前端与浏览器协议比较

调研快照：2026-10-29（Asia/Shanghai）；最后核对时间 2026-10-28 23:43 UTC。仅研究、未运行外部项目，未修改实现、规格或工单。适用约束：Dify Python 插件继续使用 Pi core-lc / harness-lc 0.6.0；每环境一个离线 difypkg；浏览器只需要聊天、工具与 Skills 进度、AskUser，Tasks 可选；不增加常驻 Pi、Node 或 WebSocket 后端。

## 结论

**优先建议 fork/抽取 `jmfederico/pi-web` 的成熟聊天核心，保留其 Lit 界面，替换 controller/transport 接入 Dify；`agegr/pi-web` 是完整 React 聊天界面与 SSE 恢复机制的另一强候选。** 不以继续使用 Vue 或保留旧卡片为前提。jmfederico 已有工具、技能调用/加载、思考、运行状态、问卷和相应交互；其问卷作为完成结果返回，在单独且最后调用等约束满足时可结束本轮，回答再作为 follow-up。两者完整产品都依赖自己的 Node/Pi 常驻运行环境，适合复用客户端，不能直接把原服务带进 difypkg。stars 仅说明本次搜索中的关注度，不代表成熟度已验收。[agegr README](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/README.md)、[jmfederico ChatView](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ChatView.ts#L117)、[ask_user 工具](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserTool.ts#L83)

**没有发现能在本样本内直接替换 CopilotKit、同时天然连接 Python Dify 插件的即插即用前端。** 所核对的三个主要 Web 应用分别用 React/Next.js、Lit/Vite、React/Vite；它们的网络消息格式不同。可借鉴 UI 与状态重建方法，但仍需 Dify 传输适配。这里不建议把社区 WebSocket 协议强行变为新的后端服务。[agegr package.json](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/package.json)、[jmfederico package.json](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/package.json)、[xing-shuyin package.json](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/package.json)

**特别注意：jmfederico 的持久 AskUser 是“已完成工具结果 + 可重复回答的历史问卷”，不是“恢复未完成的工具调用”。** 它没有解决当前 Dify pending、审批恢复、同批尾部工具或答案幂等语义；这些必须继续由当前 Python 插件定义。[问题解析](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserDomain.ts#L39)、[提交与唤醒](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.ts#L1946)

## 搜索范围与热度口径

通过 GitHub connector 搜索公开仓库，查询包括 `"pi-web-ui"`、`"pi-webui"`、`pi-agent-studio`、`"pi coding agent" web in:description sort:stars`、`"pi" "web UI" "coding" in:description sort:stars`、`"pi-web" in:name sort:stars`；每个查询读取最多 30 个结果，再对候选调用 GitHub REST 仓库接口读取真实 `stargazers_count`、`updated_at`、`pushed_at`，未使用搜索摘要的星数。

下表是**八个详细比较样本**的排序，不是全球 Pi Web 排名，也不表示下载量、用户数或协议占有率。包含四个指定方向候选与搜索发现的四个相关 Web UI。搜索并非穷尽 GitHub；同名 Raspberry Pi、Pi Network、网页搜索工具等均排除。`nicobailon/pi-web-access` 虽有 1,733★，其仓库自述是搜索/内容提取扩展，不是聊天前端；`pithings/pi-vscode` 有 188★，是 VS Code 扩展，不把它算作独立浏览器应用。托管型 `thecodacus/pithagoras`（296★、Apache-2.0）与 Pi Durable 应用 `HazAT/ultimate`（268★、MIT）也在搜索结果中出现，但因增加服务或运行体系，未进入本次八项深入比较。[web-access REST](https://api.github.com/repos/nicobailon/pi-web-access)、[pi-vscode REST](https://api.github.com/repos/pithings/pi-vscode)、[pithagoras REST](https://api.github.com/repos/thecodacus/pithagoras)、[ultimate REST](https://api.github.com/repos/HazAT/ultimate)

| 样本 | stars | updated_at（UTC） | pushed_at（UTC） | 元数据来源 |
| --- | ---: | --- | --- | --- |
| [agegr/pi-web](https://github.com/agegr/pi-web) | 7,880 | 2026-10-28T22:43:12Z | 2026-10-20T16:53:57Z | [REST 元数据](https://api.github.com/repos/agegr/pi-web) |
| [jmfederico/pi-web](https://github.com/jmfederico/pi-web) | 911 | 2026-10-28T23:38:53Z | 2026-10-28T20:54:53Z | [REST 元数据](https://api.github.com/repos/jmfederico/pi-web) |
| [xing-shuyin/pi-web-ui](https://github.com/xing-shuyin/pi-web-ui) | 344 | 2026-10-28T17:32:43Z | 2026-10-28T17:32:43Z | [REST 元数据](https://api.github.com/repos/xing-shuyin/pi-web-ui) |
| [BlackBeltTechnology/pi-agent-dashboard](https://github.com/BlackBeltTechnology/pi-agent-dashboard) | 336 | 2026-10-28T16:40:52Z | 2026-10-28T16:40:59Z | [REST 元数据](https://api.github.com/repos/BlackBeltTechnology/pi-agent-dashboard) |
| [JohnnyZ93/pi-agent-studio](https://github.com/JohnnyZ93/pi-agent-studio) | 41 | 2026-10-20T23:51:32Z | 2026-10-08T09:46:05Z | [REST 元数据](https://api.github.com/repos/JohnnyZ93/pi-agent-studio) |
| [Zetaphor/pi-webui](https://github.com/Zetaphor/pi-webui) | 14 | 2026-09-02T05:05:04Z | 2026-05-01T20:40:12Z | [REST 元数据](https://api.github.com/repos/Zetaphor/pi-webui) |
| [gallen/pi-web-ui](https://github.com/gallen/pi-web-ui) | 1 | 2026-10-18T01:46:41Z | 2026-10-18T01:46:38Z | [REST 元数据](https://api.github.com/repos/gallen/pi-web-ui) |
| [Watercol/pi-web-ui](https://github.com/Watercol/pi-web-ui) | 0 | 2026-08-25T17:05:47Z | 2026-08-25T16:59:13Z | [REST 元数据](https://api.github.com/repos/Watercol/pi-web-ui) |

`updated_at` 包括仓库元数据变化，不能当作最近代码提交；判断活跃度时同时列 `pushed_at`。上表值是本次读取时的快照，链接将来会返回新值。

## 八项比较

| 项目 | UI / 运行方式 | 流与恢复、工具与 AskUser | 许可证与复用判断 |
| --- | --- | --- | --- |
| **agegr/pi-web** | React + Next.js；Node ≥22.19；服务端直接构建 Pi SDK session，使用本机 Pi 配置和 JSONL 会话 | HTTP 命令 + SSE；Pi 事件投影，工具 start/update/end；连接时恢复正在流式输出的消息与待答 extension UI；支持 confirm/select/input/editor/custom | MIT。适合作为主要产品交互、SSE 重建与卡片参考；其会话管理、文件系统和 SDK 服务不适合整体搬入 Dify |
| **jmfederico/pi-web** | Lit Web Components + Vite；Fastify/WS；持久 session daemon 与 Pi npm SDK；机器/项目/工作区体系 | 自定义 WebSocket 增量事件 + HTTP 历史/状态快照；seq 水位去重；完整工具卡；ask_user 结果持久化，答案 follow-up；另有运行中 extension dialogs | MIT。优先参考 AskUserCard、ToolExecutionView 和问答记录；组件仍依赖其主题、本地化与插件样式，需要抽取适配 |
| **xing-shuyin/pi-web-ui** | React + Vite；Express/WS；本机/SSH/PTY、多引擎、插件工作台 | snapshot / snapshot_delta + rev/baseRev、get_state 重同步；思考/工具执行输出；问卷、审批可在当前服务的快照中恢复；ask_user_question 仍等待 Promise | MIT。问卷表单和快照一致性值得参考，整套工作台明显超出最小聊天需求 |
| **BlackBeltTechnology/pi-agent-dashboard** | React；Node Dashboard Server；Pi bridge extension 与浏览器各自用 WebSocket 接入 | 多会话/TUI 共存、事件缓冲、聊天/工具/进度；PromptBus 路由 confirm/select/input/editor/multiselect，首个回答解决等待 | MIT。适合参考工具轨迹、通知和多端提示关闭；双向 bridge 与大量 IDE/终端功能不适合当前部署 |
| **JohnnyZ93/pi-agent-studio** | VS Code 扩展；可选 Webview 聊天；每面板 pi --mode rpc 子进程，侧栏后台 session | 流式聊天、工具、问卷、Todo、技能设置；侧栏隐藏后重新解析可重建状态 | MIT；是 pithings/pi-vscode 的 fork。适合观察 IDE 问卷/工具卡，不是独立 Web 站点基座 |
| **Zetaphor/pi-webui** | Lit + 旧 @mariozechner/pi-web-ui 0.66.1 组件；Express/WS 直接持有 Pi SDK | 轻量 agentEvent / stateSync、会话切换、流与工具显示；检查的共享协议没有 extension_ui_response 或结构化 AskUser 往返 | GitHub license=null，根目录未见 LICENSE；不能据公开代码推定有复制授权。可读作小型协议示例，非优先复用来源 |
| **gallen/pi-web-ui** | mini-lit/Lit Web Components + Tailwind；恢复保存旧官方组件的独立包；AgentInterface 绑定进程内 Agent | 消息/流式容器/工具结果与 IndexedDB；不是独立远程 Web 协议；AgentInterface 默认会配置模型流与 ProviderKeysStore | README/package 声明 MIT，但 GitHub license=null，根目录未见独立 LICENSE。若复用需保留可证明的上游许可来源；更适合渲染器参考，不能直接把浏览器 Agent 当作 Dify |
| **Watercol/pi-web-ui** | React + Vite；Node ≥20；服务端 spawn 独立 pi --mode rpc 子进程 | SSE /api/events；映射 message/tool_start/tool_update/tool_end；按 eventId 回复 extension UI；读取消息重建 UI | MIT。比大型工作台更小，适合读事件 reducer 与时间线；仍要求 Pi 子进程及其服务 |

表中代码与许可证依据：

- agegr：[README](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/README.md)、[依赖](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/package.json)、[SDK session](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/rpc-manager.ts#L1)、[extension UI 类型](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/types.ts#L139)。
- jmfederico：[README](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/README.md)、[依赖](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/package.json)、[工具卡](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ToolExecutionView.ts#L20)、[AskUserCard](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/AskUserCard.ts#L52)。
- xing-shuyin：[README](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/README.md)、[依赖](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/package.json)、[协议](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/server/protocol.ts#L195)、[等待式问卷工具](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/server/ask-user-question-tool.ts#L93)。
- Dashboard：[架构（连接与 PromptBus）](https://github.com/BlackBeltTechnology/pi-agent-dashboard/blob/7d07c461aac948c49e58d9a9393a21aaa1c05ab4/docs/architecture.md#L8)、[package.json](https://github.com/BlackBeltTechnology/pi-agent-dashboard/blob/7d07c461aac948c49e58d9a9393a21aaa1c05ab4/package.json)。
- Studio：[README](https://github.com/JohnnyZ93/pi-agent-studio/blob/4aa3e1a6900896f89220693de94ac9c9dd63ad58/README.md)、[fork 元数据](https://api.github.com/repos/JohnnyZ93/pi-agent-studio)。
- Zetaphor：[README](https://github.com/Zetaphor/pi-webui/blob/ddad698a1aad5af009480c3c5b753d361a6c09ff/README.md)、[协议](https://github.com/Zetaphor/pi-webui/blob/ddad698a1aad5af009480c3c5b753d361a6c09ff/shared/protocol.ts)、[依赖](https://github.com/Zetaphor/pi-webui/blob/ddad698a1aad5af009480c3c5b753d361a6c09ff/package.json)、[固定根目录清单](https://api.github.com/repos/Zetaphor/pi-webui/git/trees/ddad698a1aad5af009480c3c5b753d361a6c09ff)。
- gallen：[README](https://github.com/gallen/pi-web-ui/blob/fe570d78a6ed51f55af9ab58e39ad02b08f99dc5/README.md)、[AgentInterface](https://github.com/gallen/pi-web-ui/blob/fe570d78a6ed51f55af9ab58e39ad02b08f99dc5/src/components/AgentInterface.ts#L137)、[声明许可](https://github.com/gallen/pi-web-ui/blob/fe570d78a6ed51f55af9ab58e39ad02b08f99dc5/package.json#L52)、[固定根目录清单](https://api.github.com/repos/gallen/pi-web-ui/git/trees/fe570d78a6ed51f55af9ab58e39ad02b08f99dc5)。
- Watercol：[README](https://github.com/Watercol/pi-web-ui/blob/b7af6603b15bd80296a366ded805bcbf60385e35/README.md)、[依赖](https://github.com/Watercol/pi-web-ui/blob/b7af6603b15bd80296a366ded805bcbf60385e35/package.json)、[RPC 子进程/事件映射](https://github.com/Watercol/pi-web-ui/blob/b7af6603b15bd80296a366ded805bcbf60385e35/server/src/pi-rpc-client.ts#L111)、[SSE hook](https://github.com/Watercol/pi-web-ui/blob/b7af6603b15bd80296a366ded805bcbf60385e35/web/src/hooks/useSseStream.ts#L124)、[extension dialogs](https://github.com/Watercol/pi-web-ui/blob/b7af6603b15bd80296a366ded805bcbf60385e35/web/src/lib/interactive-dialog.tsx#L1)。

## “Pi Web 协议”实际包含不同层次

本样本没有证据证明一个统一的“最流行 Pi Web 标准”。**按本次样本仓库 stars 看，最受关注的 agegr 使用 HTTP + SSE。** 多个其他项目用 WebSocket，只能说明存在多个 WS 实现，不能按项目数量推导用户占比。所读源码显示下列边界：

| 层次 / 项目 | 实际格式 | 可借鉴边界 |
| --- | --- | --- |
| Pi SDK 事件 | agent_start/end、message_start/update/end、tool_execution_start/update/end 等进程内事件 | 是语义事件，不指定浏览器必须用哪种传输 |
| Pi CLI RPC | JSON 命令、响应及事件，经子进程 stdio | Watercol / Studio 由宿主进程桥接；不能假定浏览器能直接连接，也不能要求 Dify 内新增 Pi CLI |
| agegr 浏览器 API | POST /api/agent/:id 发送命令；GET /api/agent/:id/events 为 SSE，传递过滤/压缩后的 Pi 事件及 connected 等应用帧 | 请求与事件流分开；重连时先建立监听并缓冲，再发送当前状态，避免快照与事件之间丢失 |
| jmfederico 浏览器 API | WS /sessions/:id/events；assistant.delta、tool.start/update/end、message.append、dialog.opened/closed 等应用 DTO；HTTP transcript-snapshot | Pi SDK 事件先映射为 UI DTO；同一次快照中的历史、流式 partial 与 seq 水位协调，客户端过滤 seq≤水位 |
| xing-shuyin 浏览器 API | 纯 JSON WS；全量 snapshot 与 snapshot_delta；rev/baseRev、序列号以及 get_state | 客户端缺更新时主动重建；pendingQuestion 属于当前会话的服务端状态，避免只靠一次性通知 |
| Zetaphor 浏览器 API | WS prompt / steer / followUp / abort / getState；agentEvent / stateSync | 极简协议可读，但 any 负载与缺失问卷往返不足以覆盖目标需求 |

依据：[Pi 1.3 事件类型](https://github.com/earendil-works/pi/blob/71023aec1546d6d677a65669c5665c0927ce0dd0/packages/agent/src/types.ts#L480)、[agegr 命令路由](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/app/api/agent/[id]/route.ts#L5)、[agegr SSE 路由](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/app/api/agent/[id]/events/route.ts#L1)、[agegr 连接快照](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/agent-event-stream.ts#L233)、[jmfederico 路由](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/sessionRoutes.ts#L560)、[jmfederico 事件投影](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.ts#L5890)、[序号水位](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/realtime/sessionEventHub.ts#L55)、[xing rev](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/server/protocol.ts#L205)、[xing resync](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/web/src/use-chat.ts#L2035)。

三个主要应用的 package.json 与已读 wire/source 中没有体现必须通过 AG-UI 或 CopilotKit 才能使用 Pi。它们各自定义浏览器层是可行性的实例证据；这不等同于验证了当前 Dify 流到任一社区前端的兼容性。

## 深看一：agegr 的 SSE 与工具生命周期

它保留消息开始/结束和工具开始/结束作为结构边界，工具更新按 toolCallId 合并，150ms 内只保留最新 partial；积压过大时断开流让客户端重连重建。不是把每个原始大对象无条件转发到浏览器。对于长输出，工具结束事件本身不重复携带结果，而从权威消息拿结果。这种“可丢中间显示更新，保留起止事实”的分层值得参考。[事件流合并与背压](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/agent-event-stream.ts#L15)、[工具事件投影](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/agent-event-wire.ts#L80)

连接时先订阅并暂存事件，再发送 connected（包括 isStreaming 和 pendingExtensionUiIds），重放待答请求与进行中消息；前端按 request id 排队/去重，重连时移除服务端已不再持有的请求。confirm/select/input/editor 与 custom overlay 分别排队，避免并发工具请求被后一个覆盖。[连接顺序](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/agent-event-stream.ts#L233)、[队列](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/extension-ui-queue.ts#L1)

这些待答扩展 UI 的 waiter 与 session 属于服务端内存；所读实现证明浏览器断线/刷新恢复，不证明进程重启后还能接回原先的扩展 Promise。不能把它等同于 Dify 持久中断。UI 自定义终端组件还需服务端 headless TUI 支持，完整复用会把不需要的运行层一起带进来。[内存 pending map 与 headless TUI](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/rpc-manager.ts#L305)、[custom UI 类型](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/rpc-manager.ts#L80)

## 深看二：jmfederico 的 AskUser 完整调用链

### 1. 产生问题并完成工具结果

createAskUserRequest 用 randomUUID 产生独立 askId，保存 askedAt、题目 ID、选项 value；此 askId 与模型的 toolCallId 是不同身份。ask_user 返回 content + details.ask + terminate:true，并限制 exposure 为 model-only。问题不是只留在浏览器或某个 WS 请求里，而在成功 toolResult.details 中。[问题构造](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserDomain.ts#L29)、[执行返回](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserTool.ts#L96)

### 2. terminate 的保证有限

该项目开发依赖是官方 TypeScript Pi ^1.3.0，运行时选择已安装的 Pi npm SDK。为避免把版本语义混在一起，下面核查固定官方 v1.3.0 commit `71023aec1546d6d677a65669c5665c0927ce0dd0`，不是 Python core-lc/harness-lc 0.6.0 的兼容保证。[社区依赖](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/package.json)、[运行时 SDK 选择](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/piRuntime.ts#L39)、[官方版本 ref](https://api.github.com/repos/earendil-works/pi/git/refs/tags/v1.3.0)

官方 agent-loop 会执行整个工具批次，再检查 finalized results；**只有所有结果都 terminate:true，才不因工具调用自动继续下一次模型请求。** sequential 路径没有因为某个 terminate 结果提前 break，parallel 路径也执行/收集同批调用。终止判断后仍检查 steering/follow-up 队列，finishTurn 也可参与后续决策。因此它不是“问卷一出现就硬停整个调度器”。ask_user 的 alone and last 来自工具提示约束，不是源码中的同批尾部工具闸门。需要暂停严格受控的副作用时，不能直接把这套做法当成充分保证。[官方循环与队列](https://github.com/earendil-works/pi/blob/71023aec1546d6d677a65669c5665c0927ce0dd0/packages/agent/src/agent-loop.ts#L258)、[顺序工具执行](https://github.com/earendil-works/pi/blob/71023aec1546d6d677a65669c5665c0927ce0dd0/packages/agent/src/agent-loop.ts#L530)、[批次终止条件](https://github.com/earendil-works/pi/blob/71023aec1546d6d677a65669c5665c0927ce0dd0/packages/agent/src/agent-loop.ts#L690)、[ask_user 提示约束](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserTool.ts#L99)

### 3. 浏览器重建问卷

AskUserCard 支持单选、多选、自由文本、自定义答案、附加评论、跳过、部分作答确认与历史答案显示；草稿以 sessionId + askId 在 localStorage 保存。活跃问卷从已加载 transcript 的尾部推导，只有历史已就绪、位于当前尾部且可写才打开；后续正常消息可以使其不再是当前活跃表单，而旧问题仍是可回答的历史事实。[表单](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/AskUserCard.ts#L97)、[草稿](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/askDrafts.ts#L37)、[尾部判断](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/chatQuestions.ts#L11)、[行为测试](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/chatQuestions.test.ts#L13)

### 4. 提交答案并唤醒

浏览器 POST /sessions/:sessionId/ask/submit，带 cwd、askId 和 answers。服务端打开会话，查当前选中分支上相同 askId 的成功 ask_user toolResult，校验 question ID、option value 和单/多选约束；拒绝未知或已不在该分支的请求。随后通过 sendCustomMessage 写入 `pi-web.ask.answers`，details 包括 askId、原题、答案和未回答题目，使用 triggerTurn:true / deliverAs:followUp。空闲时启动新运行，忙碌时排队到后续。这是结构化普通 follow-up，不是向原 toolCallId 补发迟到工具结果。[客户端请求](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/api/clients.ts#L265)、[服务端入口](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/sessionRoutes.ts#L392)、[查找/校验](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserDomain.ts#L39)、[交付](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.ts#L1946)、[官方 sendCustomMessage](https://github.com/earendil-works/pi/blob/71023aec1546d6d677a65669c5665c0927ce0dd0/packages/coding-agent/src/core/agent-session.ts#L2311)

**askId 只是问题关联键，不是答案幂等键。** 源码明确允许重复回答、较晚回答、回答后的 skip；没有一次性消费或 stale/duplicate gate。因此多个标签页重复提交可以多次唤醒模型。不可把这个行为带入应当严格一次处理的 Dify 恢复或审批流程而不重新定义语义。[不消费请求](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserDomain.ts#L39)、[无答案去重门](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.ts#L1965)

### 5. 持久化与跨服务重启证据

仓库含真实 SessionManager JSONL + 官方 SDK 的集成测试：第一次模型只产生 ask_user，断言模型请求仅一次；读取磁盘确认成功工具结果带 details.ask；dispose 第一 service，再创建第二 service，用相同 askId 回答两次并 skip；读取同一 JSONL 确认三个 custom_message outcome，且后续模型上下文收到答案。模型传输与资源发现被隔离，持久化走真实 SDK。**这是已持久化问卷在正常 service/runtime 重建后可继续回答的证据**，本次没有执行该测试，也不是强制杀进程/磁盘故障实验。[测试完整流程](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.askUser.test.ts#L220)

不能从上述测试推导“任何提交成功返回都具备 crash-safe exactly-once”。官方 sendCustomMessage 在已有流运行时先把 follow-up 放入内存队列，所读路径没有在入队瞬间同步写入答案 JSONL；因此已入队但尚未被消费的答案在突然进程死亡时的保证仍需另证。测试也没有覆盖这种故障窗口。[官方流中入队分支](https://github.com/earendil-works/pi/blob/71023aec1546d6d677a65669c5665c0927ce0dd0/packages/coding-agent/src/core/agent-session.ts#L2336)

### 6. 与 extension dialog 的区别

同一产品的 ctx.ui.confirm/select/input 使用另一套 daemon-owned PendingExtensionDialogStore（内存 Map + waiter），并在状态快照中恢复浏览器卡片。dialog answer 解决原扩展代码里的 Promise，不产生模型 follow-up；ask_user 则原工具已经完成。两者不是一种协议、不能混称“AskUser 已支持重启恢复”。[两条交付路径的相邻代码](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.ts#L1965)、[dialog 状态类型](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/shared/apiTypes.ts#L936)、[内存 store](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/pendingExtensionDialogStore.ts#L64)

## 深看三：xing-shuyin 的问卷快照

它的 ask_user_question 工具等待 clientSession.askUser 的 Promise，再把答案变为工具结果；取消会产生工具错误。UiState.pendingQuestion 携带 id、questions、deadline、conversationId，目的是刷新、WS 重连、切会话或第二标签页时补回问卷。客户端 rev 不匹配时 get_state 重同步。这能借鉴“当前待答问题是可查询状态，不只是一闪而过的事件”，但服务端仍持有等待，不符合本项目想避免的长期运行插件会话。源码与注释没有证明同一个待答 Promise 可以跨后端进程重启。[工具等待](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/server/ask-user-question-tool.ts#L93)、[pendingQuestion](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/server/protocol.ts#L279)、[问题类型](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/server/protocol.ts#L1840)、[重同步](https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/web/src/use-chat.ts#L2035)

## 能否直接 fork 成熟客户端，而非重新写 Vue

**可以优先 fork 或抽取成熟聊天客户端；本次最合适的切入点是 jmfederico 的聊天核心，保留其 Lit UI，替换其应用 controller/transport。** 用户需要的 Agent 工作感在该项目已有具体表现：运行状态文字与视觉反馈、流式思考与答案、pending/running/success/error 工具卡、参数/命令/路径、结果与 diff、技能调用与已加载技能行、折叠轨迹、问卷、图片和滚动定位。保留这些交互可比只借鉴外观后重写 Vue 更接近目标。此判断来自组件职责和 source 结构，**stars 只用于筛选关注度，不作为成熟度或质量证明**。[ConversationLayout](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ConversationLayout.ts#L16)、[ChatPart 模型](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/chatTypes.ts#L11)、[工具卡](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ToolExecutionView.ts#L36)、[轨迹模板](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/chatTranscriptTemplates.ts#L221)

### 推荐的复用边界

| 方案 | 可保留什么 | 必须适配什么 | 相对成本判断 |
| --- | --- | --- | --- |
| **jmfederico 聊天核心 fork/抽取，新的 Dify controller** | ChatView、PromptEditor（CodeMirror）、ConversationLayout、ToolExecutionView、AskUserCard、Markdown/图片、主题/本地化、折叠/滚动/复制/草稿；可继续加入原客户端中有价值的消息操作 | Dify 会话身份与历史 → ChatLine/ChatPart；Dify 流 → reducer；发送/停止/AskUser → 回调；删除或替换 composer 内部补全 API；梳理本地化/样式/Markdown 依赖 | **中，首选验证方向**。核心组件已接收 props/callbacks，能保留整体交互而不是重写 |
| jmfederico 整个 PiWebApp 不裁功能，只换 transport | 原导航、工作区、多机、插件、终端、模型设置、聊天等完整应用 | 除 WS 还有机器/项目/工作区、配置、插件、模型、文件等大量 REST；SessionController/AppState 的领域身份和服务状态都需替代 | **高**。不是单个网络适配器就完成；保留无对应后端的功能会扩大适配面 |
| agegr 完整聊天 UI fork，改 useAgentSession 及相关客户端 API | React/Next 聊天布局、MessageView、ChatInput、思考/工具/状态、自定义扩展对话框、技能命令等 | useAgentSession、聊天/输入组件内直接 fetch、Next 绑定、本机文件/上下文/模型能力；需要选定保留的完整交互 | **中到高**。适合偏好其成品 UI 的团队；接口耦合比 jmfederico ChatView 更分散 |
| 新写同等 Vue 聊天 UI | 可复用当前 Vue 工程与 Dify 接入经验 | 重新实现同等工具/技能/问卷/思考/滚动/草稿/附件/主题交互，并处理状态竞态 | **中到高，非默认首选**。框架一致不是比成熟 UI 复用更重要的条件 |

成本仅为静态源码边界的比较，不是开发时长估算；没有执行 build、浏览器验收或做代码抽取验证。若原产品的完整布局交互更符合偏好，整体 fork 也成立；上述推荐只是避免为了保留完整应用壳而重建它所有工作台服务。

jmfederico 的 ChatView 通过 messages、status、activity、historyReady、pendingDialogs、onSubmitAsk、onAnswerDialog、onLoadMore 等属性/回调接入，PromptEditor 通过 onSend/onStop 接入。两者不是从全局 Pi runtime 读取消息的封闭黑盒，因此有真实的替换 seam。必须同时保留/收拢其主题、本地化、格式化、共享类型和样式集成；并把 PromptEditor 内部 commands/files/models 直接 API 请求提取或禁用对应补全。可 fork 独立 Lit/Vite 前端作为替代客户端，不要求继续保留旧 Vue shell，也不要求把 Lit 转写成 Vue。[ChatView 接口](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ChatView.ts#L117)、[PromptEditor 接口](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/PromptEditor.ts#L59)、[composer 的 API 调用](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/PromptEditor.ts#L481)

### 原 jmfederico 客户端实际要求的服务接口

下表是**原客户端依赖调查，不是建议 Dify 新增这些路由**。`S` 表示 `api/machines/:machineId/sessions/:sessionId`；原协议会同时传 cwd，使用 machine/project/workspace/session 四层身份。本项目可以由浏览器内 Dify controller 提供等价的 UI 数据/回调，不必增加常驻 Node 或 WS 服务。[URL 与身份构造](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/api/clients.ts#L63)、[组件组装](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/PiWebApp.ts#L4015)

| 功能 | 原客户端请求 / 服务状态 | 抽取聊天核心后 |
| --- | --- | --- |
| 会话与历史 | GET api/machines/:m/sessions、POST 同路由；GET S/transcript-snapshot、S/messages?before&limit、S/status；快照含 page/status/partial/seq | 必需能力由 Dify 会话列表、历史与持久状态提供；不必保留 machine/cwd 模型 |
| 实时轨迹 | WS S/events?cwd&media=...；assistant.start/delta/thinking.delta、tool.start/update/end、message.end、agent.start/end、activity/status 等 | 必需；改为消费 Dify HTTP 流并驱动原 ChatPart/reducer，无需 WS |
| 发送与停止 | POST S/prompt（text、streamingBehavior、attachments）、S/stop 或 S/abort；流状态、compaction、queue | 发送/停止与运行状态必需；只开放 Dify 实际支持的 steer/followUp/compaction 操作 |
| AskUser | POST S/ask/submit、S/ask/cancel；askId 与完整问卷/答案来自历史 | 必需；UI 形状可复用，回调映射当前 Dify 的 user-answer/resume 语义 |
| 扩展对话框 | POST S/dialogs/answer、S/dialogs/cancel；status.pendingDialogs、dialog.opened/closed | 若保留确认卡则适配当前 pending 结构，不能虚构原 daemon waiter |
| 图片与附件 | GET S/media/:mediaId；POST S/attachments；composer 捕获附件/上传并显示 | 保留有价值交互，替换为 Dify 上传与产物 URL；不依赖本机文件夹交付 |
| 输入补全、模型设置 | GET S/commands、S/models、S/models/catalog、S/thinking-levels；其他模型/默认设置 mutation；file suggestions 来自 workspace API | 可以保留命令/技能补全但接当前 catalog；模型由 Dify 管理时移除不成立的选择与设置能力 |
| 队列、历史编辑/树 | S/queue/message、queue/clear、commands/run/respond、tree/navigate/fork 等 | 有后端等价能力才开放；可从聊天核心首版裁掉，不影响现有工具/思考/问卷展示 |
| 完整壳与工作台 | api/config、api/pi-web/status/runtime、api/machines、projects、workspaces、插件后端/能力目录、文件、终端、通知/未读等 | 可保留主题/语言/对话列表的本地 UI；机器/项目/工作区/插件运行层不是核心展示前置条件 |

来源：[客户端 API 清单](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/api/clients.ts#L240)、[媒体/事件路径](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/api/urls.ts#L15)、[完整壳控制器](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/PiWebApp.ts#L229)、[完整 controller](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/controllers/sessionController.ts#L1)。原壳还创建 MachineController、ProjectController、WorkspaceController、RealtimeSocket 等；因此“替换 transport”若指完整 PiWebApp，其工作量超过换 URL/事件名称。保留 ChatView/PromptEditor 等成熟核心并换 controller 是更窄、可解释的 fork 路线。

### Skills 与 Agent 工作感已经有哪些现成能力

jmfederico 明确区分 `skillInvocation`（命令式技能调用的折叠内容）和 `skillRead`（加载 SKILL.md 的展示），而不只是给工具名加图标。流中遇到 read 的 path 为 .../SKILL.md，会生成 role=skill 的临时行，完成消息到来时按身份/路径合并；模板显示已加载技能名称与路径。这非常贴合“Agent 在工作”的需求，值得直接保留。[ChatPart](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/chatTypes.ts#L30)、[工具到技能行投影](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/chatTranscript.ts#L159)、[完成后的合并](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/chatTranscript.ts#L117)、[技能 UI](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/chatTranscriptTemplates.ts#L221)

当前 Python 插件的技能激活与资源读取不一定叫 `read(path)`，所以 adapter 应从其真实事件映射技能行，不能机械依赖社区实现的 SKILL.md 路径识别。此处已具备“技能调用/加载”的展示能力，仍没有通用的“技能执行百分比”事实；工具运行状态与真实阶段应支撑进度显示。

### agegr fork 的具体边界

agegr 的 ChatWindow 内部调用约 3,000 行的 useAgentSession；ChatInput 内部另有 file-index、skills 等请求，MessageView 还会按需取 thinking/工具图像/长输出。因此保留成品聊天交互是可行候选，但不能只把 EventSource 改地址就完成。至少会触及 agent/new、agent/:id、agent/:id/events、lease、sessions/:id、state/context、models/default、file-index、skills、上传与媒体/长输出客户端调用。可把这些请求统一到浏览器侧 Dify adapter，或对不成立的本机工作台功能裁除/替换；React/Next UI 本身无需重写 Vue。[ChatWindow 的 hook 绑定](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/components/ChatWindow.tsx#L250)、[useAgentSession](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/hooks/useAgentSession.ts#L512)、[输入补全](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/components/ChatInput.tsx#L1172)、[技能目录请求](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/components/ChatInput.tsx#L1595)、[MessageView](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/components/MessageView.tsx#L169)


## 对当前 Dify 前端替换的适配判断

1. **优先复用成熟聊天核心，整体替换旧卡片与旧客户端也可行。** 首先考虑 jmfederico 的 Lit 聊天核心 fork，保留有价值的完整交互并替换 Dify controller；React 方向则核查 agegr。无需把所有组件重写 Vue。若嵌入现有 Vue shell，Web Components 也有技术可行性，但需收拢主题、本地化和格式化依赖；这属于适配推断，仍待一次真实 fork/build 验证。[ChatView 属性与回调](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/ChatView.ts#L117)、[PromptEditor](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/components/PromptEditor.ts#L59)

2. **直接保留工具生命周期与 Skills 展示，适配真实的 Python 事件。** jmfederico 的 toolExecution、skillInvocation、skillRead 与 agegr 的起止保留、partial 合并可以分别复用/参考；都不要求复制 WebSocket 服务。技能调用/加载已有 UI，技能百分比或更细阶段则必须有 runtime 事实支撑。[jmfederico 工具投影](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.ts#L5913)、[Skills 展示模型](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/client/src/chatTypes.ts#L30)、[agegr 工具流边界](https://github.com/agegr/pi-web/blob/e533d9b3975f8a74b378d5007c92fdf4d15d3fba/lib/agent-event-stream.ts#L39)

3. **AskUser 优先参考 jmfederico 的卡片、稳定 request ID、草稿和历史答案展示；恢复机制继续由当前 Dify 状态负责。** 若产品需要恢复原工具调用或处理同批剩余工具，必须保持对应结果配对和调度语义；若采用“问题作为完成结果，答案作为下一条用户输入”，则是明确的产品/领域语义选择，不能仅由 UI 组件决定。上述源码只提供后者的一份成熟参考。

4. **会话恢复以 Dify 的 conversation/thread 和持久状态为权威。** 可以参考 snapshot + revision/seq 消除断线和切会话竞态，但不应引入社区项目的本机 JSONL、文件浏览器、ProviderKeysStore、工作区管理或常驻 session daemon。gallen 的低层 MessageList/StreamingMessageContainer 可研究，完整 AgentInterface 会配置浏览器侧模型/API key/工具运行，不是安全的 Dify 默认入口。[gallen AgentInterface](https://github.com/gallen/pi-web-ui/blob/fe570d78a6ed51f55af9ab58e39ad02b08f99dc5/src/components/AgentInterface.ts#L137)、[jmfederico 快照](https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.ts#L2607)

5. **Tasks 可暂不进入新前端核心。** 样本的大量终端、Git、任务编排、插件市场与多机功能是完整 coding workspace 的产品面，不是实现聊天、工具/Skills、AskUser 的前置条件。这里仅作为范围判断，不要求改变现有 Tasks 后端。

## 固定源码快照

以下是 GitHub refs API 实时解析后的 commit，用于本文源码链接；stars 与日期保留在前文 REST 快照表。官方 TypeScript v1.3.0 只用于核查 jmfederico 依赖所使用的 terminate/SDK 行为，不能推导 Python 0.6.0 移植包同样支持。

| 仓库 | commit |
| --- | --- |
| agegr/pi-web | [e533d9b3975f8a74b378d5007c92fdf4d15d3fba](https://github.com/agegr/pi-web/commit/e533d9b3975f8a74b378d5007c92fdf4d15d3fba) |
| jmfederico/pi-web | [762bbfdc5e7736fe90f33abd2e19e950d5f4d496](https://github.com/jmfederico/pi-web/commit/762bbfdc5e7736fe90f33abd2e19e950d5f4d496) |
| xing-shuyin/pi-web-ui | [c9c86cfc071bf6019bd660677b2e5e7cc2617b2f](https://github.com/xing-shuyin/pi-web-ui/commit/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f) |
| BlackBeltTechnology/pi-agent-dashboard | [7d07c461aac948c49e58d9a9393a21aaa1c05ab4](https://github.com/BlackBeltTechnology/pi-agent-dashboard/commit/7d07c461aac948c49e58d9a9393a21aaa1c05ab4) |
| JohnnyZ93/pi-agent-studio | [4aa3e1a6900896f89220693de94ac9c9dd63ad58](https://github.com/JohnnyZ93/pi-agent-studio/commit/4aa3e1a6900896f89220693de94ac9c9dd63ad58) |
| Zetaphor/pi-webui | [ddad698a1aad5af009480c3c5b753d361a6c09ff](https://github.com/Zetaphor/pi-webui/commit/ddad698a1aad5af009480c3c5b753d361a6c09ff) |
| gallen/pi-web-ui | [fe570d78a6ed51f55af9ab58e39ad02b08f99dc5](https://github.com/gallen/pi-web-ui/commit/fe570d78a6ed51f55af9ab58e39ad02b08f99dc5) |
| Watercol/pi-web-ui | [b7af6603b15bd80296a366ded805bcbf60385e35](https://github.com/Watercol/pi-web-ui/commit/b7af6603b15bd80296a366ded805bcbf60385e35) |
| earendil-works/pi v1.3.0 | [71023aec1546d6d677a65669c5665c0927ce0dd0](https://github.com/earendil-works/pi/commit/71023aec1546d6d677a65669c5665c0927ce0dd0) |

未做：安装/运行社区应用、视觉交互验收、负载测试、许可证历史溯源、Dify 兼容性验证。本文是一次源码与 API 调研，不是迁移实现或兼容性承诺。
