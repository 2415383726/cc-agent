# 官方 Pi Web / 事件 / UI 契约核查

核查日期：2026-10-29（Asia/Shanghai）。范围为只读研究，不改实现、规格或实施票。本文以用户最新方向为前提：可换前端和协议，核心体验为聊天、工具与 Skills 进度、AskUser；界面应明显体现 Agent 的工作过程，可参考成熟社区客户端及通用工具展示，无需复刻旧卡片；Tasks 可选；Python `pi-agent-core-lc` + `pi-agent-harness-lc==0.6.0`，各架构一个离线 `.difypkg`，无额外运行服务。旧规格中“沿用现有前端/AG-UI、完整保留全部功能”的表述不作为本轮研究的固定限制。

## 结论

可以复用 Pi 的消息、内容块和工具生命周期模型，并让已选 Python Harness 继续负责执行。当前没有可直接接入该 Python Harness 的、仍由官方维护的 Pi Web 聊天组件包：旧官方 `@earendil-works/pi-web-ui` 已移出仓库；当前官方集成入口是 TypeScript SDK、一次性 JSON 输出和常驻进程 JSONL RPC。[官方 README][Oreadme] [删除提交][Oremove] [RPC 说明][Orpc]

对本项目，适合复用的是**有限的显示事件契约和消息重建规则**。不需要实现另一个 Harness，也不需要仿制整个官方 RPC server。Python 到 Dify 的输出适配仍然必要；AskUser 的跨轮等待与恢复必须由 Dify 状态适配承担，不能靠移植 `extension_ui_request` 字段或保存 Python Future / JavaScript Promise 获得。[Python 事件][Ptypes] [Python Harness][Pharness] [官方 RPC 实现][Orpcimpl]

## 核查版本与可复现来源

| 对象 | 已核实的版本 / 引用 | 适用范围 |
|---|---|---|
| 官方 Pi 当前默认分支 | `earendil-works/pi@556860a386a03113eca146abd9cbb08e9391b7fb`；提交时间 2026-10-28 23:16:28 UTC | 本文“当前官方”源码与文档基线。[提交][Ohead] |
| 官方最新发布 | GitHub latest 为 `v1.4.0`，发布于 2026-10-21；tag 指向 `4a080252f06caf63a525d7873c5d94d3c23887e0` | 发布版本与 main 分开记录。核对过的 `json.md`、agent `types.ts`、RPC mode 文件在这两处的 blob 相同，本文没有将所有 main 内容概括为已发布。[release][Orelease] [tag][Otag] |
| 官方旧 Web UI | 删除提交 `b141e1fa2460868686ffd19c5d4ced743eee6c24`，2026-05-20；删除前父提交 `559a71683d93ac5ff110e89ca0966bdd2a7eeccd` | 历史 API 只能按此基线参考。[删除提交][Oremove] |
| Python 选定版本 | 两个本地已安装 distribution 的 `METADATA` 均为 `0.6.0`；上游 tag `v0.6.0` 的 annotated-tag 对象 `6b92a0d9834eec22d608f2f4cc22423ace3b56b4` 指向 commit `5f73e07964f14a7409f9d1b7f2b7188b06c1fc64` | 下文 Python 判断针对实际安装文件，且关键文件与该 commit 的 blob 一致。[tag][Ptag] [PyPI core][Ppypicore] [PyPI harness][Ppypiharness] |
| 本地 `pi/` | 它是当前项目 Git 仓库中的参考目录，`git rev-parse HEAD` 返回项目提交 `7569ed20…`，不是官方 Pi 提交 | 不能把项目 SHA 当官方 SHA。已用 `git hash-object` 验证本文使用的本地 TS 核心类型、AI 类型、JSON 文档、JSON 变换、RPC mode 与以上官方 main 的 blob 相同。 |

本地 Python 源码根：`pi-agent/.venv/lib/python3.12/site-packages/`。核查的八个文件与 `v0.6.0` 上游 blob 全部一致：

| 文件 | Git blob SHA |
|---|---|
| `pi_agent_core/types.py` | `e140960f123b102d6a54deb4a4d02a944cca194e` |
| `pi_agent_core/messages.py` | `6bc91a5fbcea90f538cf26ad2f9362c9759d8753` |
| `pi_agent_core/agent_loop.py` | `4f6da9f721611ca51d47712f892551a5e78ba94c` |
| `pi_agent_core/extensions/api.py` | `6cd5d90a28829c81549eb9dca22bff37354647de` |
| `pi_agent_harness/types.py` | `bf144343e5bccba3d4235aada170d454e463caa8` |
| `pi_agent_harness/agent_harness.py` | `beba21bc61135e48d4a4512b90bdf75ddf49b1d7` |
| `pi_agent_harness/skills.py` | `43f7b735ba96d75ecdd2cb591fd51015cdf094db` |
| `pi_agent_core/adapters/langchain_stream.py` | `e1cfadaac9ea9bc7524168ef5434f591b9d67f81` |

这些是文件来源核对，不是 Dify 接入、浏览器或双架构运行验收。

## 官方 Web UI、历史包与社区项目不能混称

### 官方现状

当前官方 README 列出 agent、AI、coding-agent、TUI、Durable、telemetry、Chord 等包，没有 `pi-web-ui`。官方删除提交同时移除了 `packages/web-ui`、示例 workspace 及对应 build/check 步骤，能直接证明工作区已移除；不能只凭 npm 还能安装便称它为当前维护的官方方案。[官方包表][Oreadme] [删除提交][Oremove]

2026-10-29 直接读取 npm registry 元数据，`@earendil-works/pi-web-ui` 的 latest 仍为 `0.75.3`，发布时间 `2026-05-18T09:59:23.813Z`，latest version 对象的 `deprecated` 字段缺省。因此“未被 npm 标记 deprecated”与“官方源码仍维护”不是同一事实。[registry][Onpmweb]

另一个容易误判的旧方案是 `@earendil-works/pi-client` / `pi-protocol` / `pi-server`。当前官方 changelog 的 **1.2.0 Removed** 记录：相关 experimental server/client/plugin 源码及 source-only exports 已移除；这些包不再发布。不要据此提出部署一个“当前官方 Pi Web server”。常规 CLI JSONL RPC 仍存在，是另一个接口。[changelog][Ochangelog] [RPC][Orpc]

### 删除前的官方 Web UI 是什么

历史 `0.75.3` 是 mini-lit / Lit web components + Tailwind CSS 的浏览器聊天组件库。`ChatPanel` 包装 `AgentInterface` 和 artifacts；示例在浏览器创建 TypeScript `Agent`，管理模型、API key 和 IndexedDB 会话；工具还包括浏览器 JavaScript REPL、文档提取与 artifacts。这些默认职责不符合本项目“Dify 拥有模型、工具和状态”的边界。[旧 README][Ooldweb]

它并不是任意后端的即插即用事件播放器。`AgentInterface.session` 的类型就是 TS `Agent`；源码读取 `session.state`、调用 agent 方法并订阅累计消息快照。若保留该 UI，需要实现相应远端 Agent facade 并处理状态、发送、abort、工具结果等契约；这项工作不能称为“只换事件名称”。可以参考其中的消息或工具渲染方式，但现有 Vue 前端也能承担这些显示职责。[旧组件源码][Ooldinterface]

### 社区 Web 项目

`xing-shuyin/pi-web-ui` 的 npm 名称是无 scope 的 `pi-web-ui`，作者是 xingshuyin。官方 pi.dev 的 Packages 目录收录它，不表示它属于 `earendil-works/pi` 的官方源码包。其 README 描述的是围绕 TS coding-agent SDK / DSH 的 Web 和桌面工作台；源码 package.json 包含 Express、WebSocket、PTY、SSH 等服务端依赖。其 AskUser、刷新恢复等声明属于该项目的实现，不能用于证明官方 RPC 或 Python 0.6.0 自带这些能力。[作者 README][Creadme] [package.json][Cpackage] [目录条目][Cdirectory]

本次记录的该项目 main 为 `c9c86cfc071bf6019bd660677b2e5e7cc2617b2f`（2026-10-28）；源码 package version 为 `0.113.1`，而 pi.dev 目录页面当时显示 `0.112.0`。目录版本不用于判断其最新发布。它可以提供交互参考；直接部署会引入额外服务与另一套会话/工作区，与本轮交付限制不合。未核实它与旧官方组件库的继承关系，故称“社区替代项目”，不称“官方继任者”。[社区 commit][Chead] [源码 manifest][Cpackage]

`jmfederico/pi-web` 是另一个独立社区客户端，本次固定到 `762bbfdc5e7736fe90f33abd2e19e950d5f4d496`（2026-10-28 20:54:52 UTC）。README 明确以本机/服务端的真实工作区、持续运行的 Pi sessions 和浏览器监督为模型，安装要求 Node/Pi 并启动自己的 runtime。其完整界面和 transcript 驱动的 AskUser 值得参考，但不意味着它的服务端可以直接塞进当前 Python 插件，或只下载前端就能直接连接 Dify。下面单独分析了它不等待 Promise 的问卷语义。[README][Jreadme] [AskUser tool][Jasktool]

## 三层事件契约

### 1. Core / SDK 进程内事件

官方 Agent 的基本事件为：`agent_start/end`、`turn_start/end`、`message_start/update/end`、`tool_execution_start/update/end`。一次 turn 是一条 assistant 响应及其工具执行和结果；它不是整个用户请求。`message_update` 在 SDK 中同时带累计 `message` 和嵌套 `assistantMessageEvent`；后者又有累计 `partial`。当前 `partial` 是实时响应对象，不能依赖它永远保留事件发生时的快照。[core types][Oagenttypes] [AI stream types][Oaitypes]

`toolcall_*` 表示模型正在生成工具调用参数；`tool_execution_*` 表示实际执行。UI 应分清参数生成和执行，不因为看到 `toolcall_start` 就认为外部动作已经开始。工具 partial result 的含义由工具决定，可能是累计值，也可能是片段；通用 UI 不能把所有 `partialResult` 一律拼接。[core types][Oagenttypes] [JSON tools 说明][Ojson]

### 2. Coding-agent session 事件

官方 `AgentSessionEvent` 在 core 基础上增加 `agent_settled`、queue、compaction、auto retry、entry/session 信息等；session 的 `agent_end` 还增加 `willRetry`。`agent_end` 后可能继续压缩、重试、steer/follow-up；要判断官方 session 完成，使用 `agent_settled`，并读取 `aborted`。[session types][Osession] [RPC 生命周期][Orpc]

这些不是 Python 包拥有的同名完整 contract。Python 0.6.0 的 Harness 使用自己的 `settled {nextTurnCount}`，其 core `agent_end` 没有 `willRetry`；Harness 在处理 `agent_end` 时先转 idle、发出 core 事件和 hooks，再发送 `settled`。不能机械改名成官方 `agent_settled {aborted}`，更不能据此推断外层 Dify 重试已经结束。[Python Harness types][Pharnesstypes] [实际发送位置][Pharness]

### 3. 官方 JSON / RPC 线上事件

JSON 模式是一轮命令执行的单向输出，先发 session header，结束后进程退出；RPC 是常驻子进程 stdin/stdout 双向 JSONL，不发同一个 session header。RPC 的 command response、session event 和 extension UI record 是不同记录族。prompt 成功响应仅代表接收/排队/处理，不等于模型完成。[JSON][Ojson] [RPC][Orpc]

当前线上 `message_update` **不发送累计 `message` 和 `partial`**。`toJsonEvent()` 输出 `usage` 和去掉 `partial` 的内容块事件，并专门在 `toolcall_start` 从累计块提取 `id`、`toolName`，避免长消息反复全量传输。[实际变换][Ojsonimpl]

浏览器重建时可复用以下规则：

1. `message_start.message` 初始化当前消息；按 `contentIndex` 定位内容块。
2. 文本和 thinking 的 delta 追加到所属块；工具 arguments delta 先作为尚未完整的 JSON 文本显示。
3. `text_end.content`、`thinking_end.content`、`toolcall_end.toolCall` 替换对应临时值，不再追加一次。
4. `message_end.message` 替换整条消息，作为最终权威值。
5. 工具卡按 `toolCallId` 关联；`tool_execution_end` 与后续 `toolResult` 消息是同一次结果的两种生命周期表现，不能渲染成两次执行。并行工具 end 可按完成顺序到达，工具结果消息仍可按 assistant 原始顺序提交。[重建文档][Ojson] [并行执行契约][Oagenttypes] [Python 执行顺序][Ploop]

线上仅保留有限的累计 usage，允许模型结束时才有实际值。没有观测到用当前 JSON/RPC 协议直接恢复中途断开的任意浏览器订阅的序列号、ACK 或 replay 契约；完整重连恢复不能仅靠事件名称推得。[JSON][Ojson] [RPC][Orpc]

## 与已安装 Python 0.6.0 的具体差异

| 能力 / 字段 | Python 0.6.0 实际实现 | 复用判断 |
|---|---|---|
| 聊天和工具生命周期 | core 有对应的十类生命周期；Harness `subscribe(listener)` 按事件等待 subscriber，`on(event, handler)` 是影响行为的 hook | 足够驱动简单 UI；输出适配用订阅，不能把 UI 渲染失败变成任意业务策略。subscriber 抛错会转成 Harness hook 错误。[Python types][Ptypes] [Harness][Pharness] |
| 字段格式 | 事件为 `assistant_message_event`、`content_index`、`tool_call_id`、`tool_name`、`partial_result`、`is_error`、`tool_results`；消息本身又有 `toolCallId`、`stopReason` 等 camelCase | 不能直接 `model_dump()` 后声明兼容官方 JSON。需明确字段映射或诚实地发布 Python 自己的有限契约。[Python types][Ptypes] [messages][Pmessages] |
| 关联 ID | core event 自带 `run_id` / `turn_id`；类型注释定义其语义 | 可保留作 Dify run 关联参考，但 Dify conversation、浏览器 message、跨轮 pending ID 仍需宿主自己的明确关联。[Ptypes] |
| Provider 完成 / 错误事件 | Python `DoneEvent` / `ErrorEvent` 的最终消息在 `partial`；官方 done/error 分别用 `message` / `error`；正常 core loop 将两者转为 `message_end` | 优先消费 core message 生命周期，避免将 provider-level done/error 生搬到官方线上 union。[Python types][Ptypes] [loop][Ploop] [官方 AI types][Oaitypes] |
| 工具执行 partial | `AgentTool.execute(..., on_update)`；loop 将 update 转成 `tool_execution_update`，结束前等待已排入的 update delivery；失败也形成工具结果 | 工具已有真实 partial 时可显示；未提供 partial 的 Dify/MCP 工具不应伪造百分比。Python end 没有官方 `durationMs`，如需耗时由宿主观测或省略。[Python types][Ptypes] [loop][Ploop] |
| 最终工具结果 | Python `AgentToolResult` 只有 `content`、`details`、`terminate`；`ToolResultMessage` 有 `isError` | 当前 TS 还支持 structuredContent/usage 等更多字段。Dify 附件或 MCP blob 需现有适配层的专门投影，不能假定 Python 原生消息包揽这些产物。[Python types][Ptypes] [messages][Pmessages] [官方 types][Oagenttypes] |
| 队列 / settled | `queue_update {steer, followUp, nextTurn}`，队列成员是消息；`settled {nextTurnCount}` | 与官方 `queue_update {steering, followUp}` 和 `agent_settled {aborted}` 不同；简单聊天可不暴露队列 UI。[Python Harness types][Pharnesstypes] [官方 session][Osession] |
| 压缩 | `session_before_compact` hook、`session_compact` 等类型；没有官方相同的 reason / willRetry 线上记录 | 如产品需要“正在压缩”，在实际操作边界发送本项目状态，不伪称拥有官方所有 retry/session 语义。[Python Harness types][Pharnesstypes] [官方 session][Osession] |
| Skills | resources 中有 skills，`resources_update` 表示资源变化；`skill(name)` 把完整说明格式化后交给 `prompt()`；系统提示让模型用 read 加载 skill | 没有现成 `skill_started/progress/completed` 状态机。目录可显示已配置技能；真正加载时可用宿主已有受限技能工具的普通 tool 生命周期显示“加载技能 X”；仅列入目录不等于正在执行。[skills][Pskills] [Harness][Pharness] [Harness types][Pharnesstypes] |
| 扩展 UI | Python `ExtensionAPI` 明确是 minimal subset；可 `notify(text)`，最终是 `NoticeEvent {text}`；未定义 TS `ctx.ui`、`ExtensionUIContext`、select/confirm/input/editor 或 extension UI request/response 类型 | 能转发普通通知，不能据此声称已支持官方 AskUser。[API][Papi] [Harness types][Pharnesstypes] |

### 哪些原生事实能让界面显示 Agent 工作过程

不需要专属业务卡片，通用工具过程列表即可消费以下事实。这个展示目标比“只流式打印最终回答”更丰富，但不要求新增执行框架。

| 界面信息 | 可观察来源 | 边界 |
|---|---|---|
| 当前在思考 / 回答 | message 生命周期和 thinking/text 内容块事件 | thinking 内容取决于 Dify 模型实际是否输出；没有内容时可显示运行状态，不能生成假推理。 |
| 工具将被调用、参数形成 | `toolcall_*`；最终 `toolCall` | 取决于 StreamFn 的字段与时序；先验收再开启实时参数展示。 |
| 工具调用开始、输入、局部结果、成功/失败结束 | `tool_execution_*` | 这部分 Python 原生已有；工具没有 partial 则展示开始/结束和最终结果。 |
| 技能加载 | 宿主技能加载工具的真实执行事件，或宿主在激活后投影的明确事实 | 官方及 Python 没有通用专属 skill-progress 事件；不要把工具日志里的任意“skill”文本推断成已激活。 |
| 正在压缩、压缩完成 | 官方有 `compaction_start/end`；Python `_compact_internal` 用 `session_before_compact` hook、成功后向 subscriber 发 `session_compact` | Python 的 before 只发给 hook，不发给普通 subscriber；要显示开始，需挂接这个观察 hook 或宿主压缩操作边界。失败/取消结束也需宿主明确投影，不能只等成功事件。 |
| 上下文用量 | assistant usage、配置的 model context window、压缩 preparation 的 `tokensBefore` | Python `ContextBudget` 来自上一次请求 usage，不能把它当当前请求的实时完整预算；结构化结果、系统提示等还受 Dify 适配预算影响。可以显示最后已知/估计用量，标明来源。 |
| 当前在等用户 | 成功问卷结果或宿主持久化 pending 投影 | 可从 transcript 恢复表单；不需要保持 HTTP/插件执行一直打开。 |

上表为源码事实与界面建议的映射；尤其 Python 的 hook/subscriber 区分及预算来源见 [Harness 实现][Pharness]、[ContextBudget 类型][Ptypes]。工具更新事实见 [Python loop][Ploop]，官方阶段语义见 [JSON 文档][Ojson]。可以据此评估成熟社区客户端的过程面板，再决定复用组件还是实现本项目通用 renderer；本次未完成组件级抽取评估。

### Python 默认 LangChain adapter 的额外流限制

这里必须区分**core 的扩展点能力**与**自带 adapter 的当前输出**。在安装的 `langchain_stream.py` 中：

- 首次工具 chunk 到达时，先发送 `ToolCallStartEvent`，之后才把 chunk 的 id/name 合并到内部 accumulator；当时 `partial.content` 只来自文本/thinking 的 `current_blocks()`，不含工具块。
- text 和 thinking 的 `content_index` 都可为 0；工具用 `idx + 1`。这不能直接满足当前官方“最终 content 数组的稳定块索引”重建假设。
- 直到 `toolcall_end.tool_call` / 最终消息才能获得完整工具名、ID 和参数。因此直接执行官方 `toJsonEvent()` 的“在 start 的 partial.content[contentIndex] 读取工具块”算法会失败。[实际 adapter][Pstream]

Dify 接入计划本来就要提供自己的 `StreamFn`，core 也允许替换默认 `langchain_stream`。因此这不要求重写 Harness；它要求在 Dify 模型适配的验收中核实稳定内容索引、工具 ID/name 的到达时机及最终消息一致性。若 Dify SDK 只能较晚提供工具调用，可从完整调用/`tool_execution_start` 开始显示工具卡，省略实时参数生成。不能把默认 LangChain adapter 的问题未经验证地归因于所有 Dify 流。[core StreamFn 分支][Ploop]

## AskUser：可借用简单交互形状，不能借用恢复语义

官方 RPC `extension_ui_request` 提供这些对话方式：

| method | 请求的主要字段 | 响应 |
|---|---|---|
| `select` | `id`, `title`, `options: string[]`, 可选毫秒 timeout | `value: string` 或 `cancelled: true` |
| `confirm` | `id`, `title`, `message`, 可选 timeout | `confirmed: boolean` 或 cancelled |
| `input` | `id`, `title`, 可选 placeholder/timeout | value 或 cancelled |
| `editor` | `id`, `title`, 可选 prefill | value 或 cancelled |

notify/setStatus/setWidget/setTitle/set_editor_text 为无回复通知；setWidget 仅支持字符串数组。`custom()` 返回 undefined，TUI 组件、header/footer、自定义 editor 等不通过 RPC 传输。多问题、多选、选项描述/结构化答案并非以上简单 RPC union 的能力。[RPC UI 文档][Orpcui] [类型定义][Orpctypes]

当前官方 `question.ts` 和 `questionnaire.ts` 示例实际使用 `ctx.ui.custom()`，并在 `ctx.mode !== "tui"` 时返回 UI unavailable；不能因为示例目录列出问卷就推断它能在 RPC / Web 中直接工作。`question.ts` 在示例 README 的简述仍提及 select，实际代码应作为此处判断依据。[question 实码][Oquestion] [questionnaire 实码][Oquestionnaire]

RPC UI 实现的执行过程是：生成 UUID → 把 resolve/reject 放入 `pendingExtensionRequests` 内存 Map → stdout 发请求 → 扩展函数 `await Promise` → stdin 收同 ID response 后调用 resolve。没有匹配 ID 的 response 被忽略，不生成普通 command response；timeout/abort 对简单对话解析为默认值。这是常驻进程会话中的等待，没有把待续 Promise、调用栈和 continuation 持久化成下轮请求的机制。[RPC 实现][Orpcimpl]

由此对 Dify 得出的工程判断是：结束本次插件调用、保存 `agent_state`、下次重新实例化 Harness 后，只有请求字段还在，并不能恢复原来的 await。即使把 UI 请求名字完全沿用，也必须处理 pending request、答案匹配、历史工具配对、暂停后的批次处理和继续执行；这属于 Dify 宿主适配，不是现成官方 RPC 功能。现有 CC Agent `UserInterrupts.resume()` 已有“从状态中定位 pending 工具结果、校验答案 ID、更新结果、继续调度”的可参考行为。[本地 interrupts](../../cc_agent/core/interrupts.py) [本地 runtime](../../cc_agent/core/runtime.py)

若重做前端，可借用 select/confirm/input 的简单形状；若需要保留当前多问题/多选 AskUser，则应承认是本项目自己的扩展。对原生 Dify 聊天界面，可按宿主最终验证结果退化为文本问题和下一轮文本答案；不应为模仿官方 TUI 引入常驻 Node/Python 服务。**AskUser 与工具授权也不是同一业务语义**：可共用表单显示，授权结果仍需重新经过工具策略检查。[RPC UI][Orpcui] [本地授权恢复](../../cc_agent/core/interrupts.py)

### 更适合本项目的候选：完成问卷工具，再接收下一轮答案

`jmfederico/pi-web` 的 `ask_user` 不等待用户：验证并创建 `{askId, askedAt, questions}`，在一次**成功的完整工具结果**中写入 `details.ask`，返回 `terminate: true`。工具结果文字明确告诉模型本次结束、答案将作为 follow-up 到来。这样提问的工具调用已经完成，无悬空 tool call、Future 或需之后替换的占位结果。[工具实码][Jasktool]

该项目后端从当前 branch 上成功 `ask_user` 的 toolResult 解析问卷，验证答案后追加带结构化 details 的 custom message，以 `{triggerTurn:true, deliverAs:"followUp"}` 唤醒 Agent；它不是把原 toolResult 改成答案。其源码刻意允许较早问卷收到后续答案、再次回答及晚到的 skip；普通自由文本对话不会自动合成取消。相关测试包含关闭 service、重新打开磁盘会话、再回答的路径。这些是该项目代码/测试表达的语义，本次没有执行它的测试。[领域逻辑][Jaskdomain] [实际答复路径][Jservice] [重启测试][Jasktests]

**对 Dify 的判断：这能明显减少历史编辑复杂度，是提问功能值得优先验证的方案。** Dify 中可以把问卷完整结果随普通历史保存在 `agent_state`，下一轮把已验证的答案追加为普通 user 消息或一个明确可转换为模型消息的 custom entry。`pending question` 可以只是当前需显示的投影/ID，而不是执行到一半的工具结果；若能从保留历史可靠重建，也不必维护独立问卷数据库。Dify 对话状态大小压缩时，需明确保留仍需回答的问卷或其完整投影。这里是对该模式的适配推断，不声称 Python 原生已经实现了该 tool。

但“提示词要求单独最后调用 + 返回 terminate”还不够，Python 0.6.0 的批次语义是：

- `_should_terminate_batch()` 只有在**本批所有 finalized result 的 terminate 都为 true**时才终止自动 follow-up；它没有“遇到一个 ask 就立刻停止其余工具”的内建规则。
- 混合 ask + 外部操作时，默认并行路径可能让另一工具已开始；即使给 ask 设置 sequential，同批其他工具也可能在它之前或之后执行。
- core 有 `should_stop_after_turn`，但当前 `AgentHarness.__init__` 和 `_create_loop_config` 并未向宿主暴露/传入这个配置。不能把“core 存在字段”描述成 Harness 的现成公开开关。
- `before_tool_call` 返回 block 会生成 immediate error result，当前路径不会自动保留 `terminate:true`；所以只给 siblings 加 block hook 也不能直接保证整批终止。[实际 Python loop][Ploop] [Harness 配置][Pharness]

因此需要一个**小而确定的宿主批次约束**：问卷必须独立形成可提交批次，或混合批次在任何外部副作用之前被识别、所有调用均得到配对结果，并保证成功提问后不再触发真实模型请求。具体是通过现有模型/工具适配边界规范化，还是给库补一个窄的停批次扩展点，需要针对 0.6.0 选定并测试；本次没有宣称已有零修改的现成开关。不应复制一套调度循环来绕开这个问题。

这只解决**向用户提问**。执行审批另外涉及待执行操作、允许范围、业务权限、重复点击和副作用是否已发生；不能因为 AskUser 可以追加下一轮消息，就宣布工具审批也已自动解决。若本轮不保留审批功能，可明确省略，而不是偷偷把“用户选择了一个选项”当作执行授权。

## Tasks / todo 是否原生自带

官方 coding-agent 的默认工具明确为 `read/bash/edit/write`；`todo.ts` 放在 `examples/extensions` 中，以 `registerTool("todo")` 和 `/todos` 命令展示扩展方式，todo 状态保存在工具结果 details，并非默认工具。当前官方另有 `pi-durable` 的 task runtime，但那是独立包/运行模型，不能与默认 coding-agent todo 或所选 Python Harness 混同。[默认工具源码][Odefaults] [todo 扩展示例][Otodo] [官方包表][Oreadme]

Python 0.6.0 的 built-in coding tools 工厂只有 `read/bash/edit/write/grep/find/ls`，默认 coding group 也是前四个；`AgentHarness` 构造器接受调用方传入的 `tools`，缺省为空，没有内建 Tasks/todo 状态或工具自动注册。若项目保留原 CC Tasks，需要作为宿主普通工具/扩展实现和持久化；用户已允许可有可无，因此可以先省略，或只用通用工具过程显示而不做单独面板。[Python 工具工厂][Ptools] [Harness 构造器][Pharness]

## 建议的复用边界（研究建议，尚非实施规格）

| 层 | 可保留 / 复用 | 必要的本项目适配 |
|---|---|---|
| 执行 | 已选 Python core + Harness：prompt、工具调度、消息配对、订阅和 hook | Dify 模型 StreamFn、Dify/MCP 工具、Dify state backend；不另写调度内核。 |
| 展示事件 | Pi 风格 message_start/update/end，tool_execution_start/update/end，最终消息覆盖临时消息 | 选择明确的有限 wire subset；字段映射、必要脱敏、稳定 run/message/tool 关联；在 Dify 可承载的流记录中运输。运输方案留给 Dify 实测决定，不需实现 stdin command server。 |
| 聊天 UI | Vue 或其他普通前端都可消费该 subset；过程列表、thinking、通用工具输入/局部输出/结果、上下文与压缩状态 | 可参考完整社区客户端的布局和组件；无需复刻旧业务卡片。不需要为了使用 Pi 而绑定 CopilotKit，也不需要为已退休官方组件实现 TS Agent facade。 |
| Skills 进度 | 技能加载作为有名字的普通工具过程；目录/已加载状态可另外读取宿主投影 | 仅报告可验证的加载/状态；无通用“技能百分比”或“执行完成”推断。 |
| AskUser | 优先验证 transcript 中完整问卷 toolResult + 下一轮答案；可支持结构化问卷 | `agent_state` 中保留问卷/显示投影、校验下一轮答案；成功提问后的确定停批次约束；不需要 process-local Promise 或替换占位结果。 |
| Tasks | 若保留，可继续作为普通任务工具及可选状态展示 | 当前范围允许不做独立 Tasks 面板；不要为前端复用目标扩张成另一套 task server / Durable 平台。 |

以上建议的事实基础是 Python 现有扩展点与官方显示事件，而非“Python 等同 TS 1.4.0”。需要一个明确的输出适配模块是正常宿主接入工作；若开始移植官方命令全集、会话文件管理、模型认证、目录/终端、websocket 服务器或扩展 TUI，就已超出简单 Dify 前端的必要范围。[Python loop][Ploop] [Harness][Pharness] [官方 RPC 范围][Orpc]

只向前端投影允许的显示字段。Python Harness 自己还有 `before_provider_request`、`before_provider_payload` 等内部事件，其中可带 headers、metadata、payload；这些不是聊天进度，不能把所有 `subscribe` 事件无差别转发。此处直接受项目秘密不进入输出的边界约束。[Python Harness types][Pharnesstypes] [项目 AGENTS](../../AGENTS.md)

## 尚未验证与明确限制

- 本次没有运行 Dify、真实模型、浏览器对接或包安装验收；没有验证 Dify 对自定义流记录、断连、取消、conversation ID、附件和下一轮状态的具体传输行为。事件复用可行性不等于 Dify 集成已经通过。
- 没有证明任意社区 Web 工作台只抽前端即可无损接入，也没有验证其长期维护质量、发布包双架构运行或与旧官方库的代码继承关系。
- 没有发现 Python 0.6.0 的官方 TS extension UI 兼容层。这个结论限于实际安装的 core/harness 与对应源码；不排除上层 CLI/ACP 或第三方扩展另外提供交互，但它们不能自动当成本项目依赖已经提供的能力。
- Dify 自定义 StreamFn 是否提供 thinking、真实参数 delta、工具 ID 的完整时机，仍要按 Dify SDK 实测。可以省略不可靠的实时参数细节，保留开始/结束和最终结果；不要为了字段完整而编造事件。
- 双架构离线交付仍需各自锁定依赖和实机验收。复用这些 UI 契约不要求增加 Node 运行时，但本次没有证明完整依赖树已经符合离线约束。

## 固定来源链接

[Ohead]: https://github.com/earendil-works/pi/commit/556860a386a03113eca146abd9cbb08e9391b7fb
[Orelease]: https://github.com/earendil-works/pi/releases/tag/v1.4.0
[Otag]: https://api.github.com/repos/earendil-works/pi/git/ref/tags/v1.4.0
[Oreadme]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/README.md
[Oremove]: https://github.com/earendil-works/pi/commit/b141e1fa2460868686ffd19c5d4ced743eee6c24
[Onpmweb]: https://registry.npmjs.org/@earendil-works%2fpi-web-ui
[Ooldweb]: https://github.com/earendil-works/pi/blob/559a71683d93ac5ff110e89ca0966bdd2a7eeccd/packages/web-ui/README.md
[Ooldinterface]: https://github.com/earendil-works/pi/blob/559a71683d93ac5ff110e89ca0966bdd2a7eeccd/packages/web-ui/src/components/AgentInterface.ts
[Ochangelog]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/CHANGELOG.md
[Oagenttypes]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/agent/src/types.ts
[Oaitypes]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/ai/src/types.ts
[Osession]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/src/core/agent-session.ts#L196
[Ojson]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/docs/json.md
[Ojsonimpl]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/src/modes/json-event.ts
[Orpc]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/docs/rpc.md
[Orpcui]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/docs/rpc-extension-ui.md
[Orpcimpl]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/src/modes/rpc/rpc-mode.ts
[Orpctypes]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/src/modes/rpc/rpc-types.ts
[Oquestion]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/examples/extensions/question.ts#L52
[Oquestionnaire]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/examples/extensions/questionnaire.ts#L92
[Ptag]: https://api.github.com/repos/zy1233/pi-python/git/tags/6b92a0d9834eec22d608f2f4cc22423ace3b56b4
[Ppypicore]: https://pypi.org/project/pi-agent-core-lc/0.6.0/
[Ppypiharness]: https://pypi.org/project/pi-agent-harness-lc/0.6.0/
[Ptypes]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/types.py
[Pmessages]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/messages.py
[Ploop]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py
[Papi]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/extensions/api.py
[Pharnesstypes]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/types.py
[Pharness]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py
[Pskills]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/skills.py
[Pstream]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/adapters/langchain_stream.py#L573
[Chead]: https://github.com/xing-shuyin/pi-web-ui/commit/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f
[Creadme]: https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/README.md
[Cpackage]: https://github.com/xing-shuyin/pi-web-ui/blob/c9c86cfc071bf6019bd660677b2e5e7cc2617b2f/package.json
[Cdirectory]: https://pi.dev/packages/pi-web-ui?name=search
[Odefaults]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/src/core/settings-manager.ts#L85
[Otodo]: https://github.com/earendil-works/pi/blob/556860a386a03113eca146abd9cbb08e9391b7fb/packages/coding-agent/examples/extensions/todo.ts
[Ptools]: https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/coding_tools/__init__.py
[Jreadme]: https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/README.md
[Jasktool]: https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserTool.ts
[Jaskdomain]: https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/askUserDomain.ts
[Jservice]: https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.ts#L1947
[Jasktests]: https://github.com/jmfederico/pi-web/blob/762bbfdc5e7736fe90f33abd2e19e950d5f4d496/src/server/sessions/piSessionService.askUser.test.ts
