# Dify 1.15.0 原生 Human Input 与插件 AskUser 选项

调查日期：2026-10-29。范围为 Dify **1.15.0**，对应提交 `3aa26fb6374bbd47e5469f7d7cc25f3e0075a60c`；对照最低声明版本 **1.7.0**。只读源码、发行说明和官方文档，未运行 Dify 实例、未提交表单、未改插件/前端/规格。GitHub connector 本次返回 `Transport closed`，改用 GitHub 的 tag 固定源码及官方文档；当前在线文档可能描述比 1.15.0 更新的功能，以下版本判断以固定源码为准。[1.15.0 tag](https://github.com/langgenius/dify/tree/1.15.0)、[tag tree API](https://api.github.com/repos/langgenius/dify/git/trees/1.15.0?recursive=1)

## 结论

**Dify 1.15.0 确实提供完整的原生表单与 workflow 恢复 API，但 `AgentStrategy` 插件不能通过允许的 `AgentInvokeMessage` 直接请求原生暂停。** 当前插件若采用该能力，需要在外层 Chatflow/Workflow 另外配置 Human Input 节点，并在答复后再次调用插件。它能减少自建表单持久化/超时机制，却不会自动恢复 Python 插件中的调用栈，也不能消除插件的待回答问题与会话状态适配。[插件消息类型](https://github.com/langgenius/dify/blob/1.15.0/api/core/agent/entities.py#L89)、[消息枚举](https://github.com/langgenius/dify/blob/1.15.0/api/core/tools/entities/tool_entities.py#L230)、[插件 Agent 节点](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/agent_node.py#L123)、[插件消息转换器](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/message_transformer.py#L284)

对“Python Pi 0.6.0 插件、一个离线 difypkg/架构、不增加服务、较简单 Vue Web UI、保留工具/Skills 进度与 AskUser”的目标，**建议首选现有的“保存问题 → 本轮结束 → 下一次聊天提交回答”路径，缩小前端协议即可；原生 Human Input 暂不作为 AskUser 的替代基础。** 这是基于下面已确认边界作出的架构判断，不是已完成的 Dify 集成验证。

## 已确认：插件接口与原生暂停不是同一层

1. Dify 端 `AgentInvokeMessage` 仅继承 `ToolInvokeMessage`，没有新增字段。允许的消息枚举包含 text、image、link、blob、json、variable、file、log 等，不含 `pause` / `human_input_required` / `form` 消息类型；daemon 调用按 `AgentInvokeMessage` 校验流。插件输出一个含 `event: human_input_required` 的普通 JSON，不会因此变成原生 workflow 事件。[AgentInvokeMessage](https://github.com/langgenius/dify/blob/1.15.0/api/core/agent/entities.py#L89)、[ToolInvokeMessage](https://github.com/langgenius/dify/blob/1.15.0/api/core/tools/entities/tool_entities.py#L147)、[daemon 调用](https://github.com/langgenius/dify/blob/1.15.0/api/core/plugin/impl/agent.py#L78)
2. 插件 Agent 节点 version `1` 消费上述消息，转换成文本 chunk、文件、JSON、变量与 `AgentLogEvent`；流结束后输出 `SUCCEEDED` 的 `StreamCompletedEvent`。这条转换路径没有创建表单或发出 `PauseRequestedEvent` 的分支。因此没有发现可供此插件使用的、受支持的原生 HITL 回调。[Agent node v1](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/agent_node.py#L58)、[转换分支](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/message_transformer.py#L126)、[结束结果](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/message_transformer.py#L284)
3. 原生 `HumanInputRequiredResponse` 是 Dify workflow 的响应实体，携带 form ID、node ID、form content、inputs、actions、form token、expiration 等。响应转换器从已经存在的原生暂停原因和表单记录构造它；它不是 AgentStrategy 输出协议的一种消息。[原生 SSE 实体](https://github.com/langgenius/dify/blob/1.15.0/api/core/app/entities/task_entities.py#L281)、[暂停转换](https://github.com/langgenius/dify/blob/1.15.0/api/core/app/apps/common/workflow_response_converter.py#L388)
4. Human Input 的 Dify runtime 持有表单 repository，并用 workflow execution ID、node 配置、rendered content、delivery methods 等创建表单。公开 Service API 的这里提供的是读表单/提交表单，不是一个让任意插件创建并暂停 workflow 的 API。[节点 runtime](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/node_runtime.py#L849)、[公开控制器](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/service_api/app/human_input_form.py#L74)

### 容易混淆的例外：Dify 新版内置 Agent v2

不能笼统说“Dify 任何 agent 都不能动态 AskHuman”。**同一个 1.15.0 tag 已有另一套内置 Dify Agent v2**：其节点版本是 `2`，调用 `agent_backend_client.create_run`；收到 deferred `ask_human` 时创建原生表单、保存关联并发出 `PauseRequestedEvent`。这个机制支持模型生成问题、字段和 actions。[Agent v2](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent_v2/agent_node.py#L106)、[backend 请求](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent_v2/agent_node.py#L257)、[deferred 到暂停](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent_v2/agent_node.py#L290)、[动态表单转换](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent_v2/ask_human_hitl.py#L245)

这不是第三方 `AgentStrategy` 插件的新消息能力。它属于独立的 Dify Agent runtime / deferred-tool 协议；其自己的文档也明确：agent run 以成功和 deferred call 结束，客户端负责呈现、收集答案并用 `deferred_tool_results` 开下一次 run。不能把这套内置 runtime 的可用性当作 Python Pi 插件能够直接接入的证据。[Ask human layer 官方源码文档](https://github.com/langgenius/dify/blob/1.15.0/dify-agent/docs/dify-agent/user-manual/ask-human-layer/index.md#L3)

## 已确认：外部 Vue 可以访问哪些原生 API

| 操作 | Dify 1.15.0 接口 | 已确认限制 |
| --- | --- | --- |
| 收到暂停问题 | 原聊天/Workflow SSE 的 `human_input_required`，随后 `workflow_paused` | 必须已有原生 form；对 Service API 可操作的通常是 webapp delivery form |
| 读取表单 | `GET /v1/form/human_input/{form_token}` | app API key；表单必须属于此 app/tenant，且是允许的 WebApp recipient；过期/已提交拒绝 |
| 提交 | `POST /v1/form/human_input/{form_token}`，body 为 `{inputs, action, user}` | 同一个 app API key；`user` 必填；校验字段及 action；返回 `{}`，恢复在 Dify worker 中异步排队 |
| 继续接流 | `GET /v1/workflow/{workflow_run_id}/events?user=...` | Chatflow/Workflow；同 app、同创建者；`user` 必须匹配原 run。URL 参数源码名虽为 task_id，查的是 workflow run ID |

上表依据固定源码：[表单控制器](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/service_api/app/human_input_form.py#L109)、[提交校验](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/service_api/app/human_input_form.py#L162)、[recipient 限制](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/human_input_policy.py#L21)、[继续流控制器](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/service_api/app/workflow_events.py#L60)、[异步恢复](https://github.com/langgenius/dify/blob/1.15.0/api/services/human_input_service.py#L195)。官方在线文档也描述该序列，但不是本文认定 1.15.0 支持它的唯一依据。[Human Input Flow](https://docs.dify.ai/en/api-reference/guides/human-input-flow)

继续流还支持 `include_state_snapshot=true` 和 `continue_on_pause=true`；后者可让 Service API 的监听流跨越后续暂停。它只改变监听流的关闭行为，不能证明任意 workflow 循环或任意插件自动续跑已经可用。[1.15.0 查询参数与实现](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/service_api/app/workflow_events.py#L34)

**是否需要新后端/鉴权：**这些 endpoint 已在 Dify 内，不要求本项目另起服务或新增一套 form 账户。沿用现有 app API key + user 的 transport 可调用它们。不过它不是无鉴权 API；部署仍要解决现有 key 分发和跨域访问。当前前端 README 已说明浏览器直连 Dify、key 浏览器可见，因此不能把“原生 forms”说成解决了这项现存问题。官方文档建议 app key 留在服务端；是否使用宿主已有代理，属于现有部署决策，不是本次研究新增服务的建议。[本项目直连说明](../../copilotkit-dify/README.md#L289)、[Dify API 鉴权说明](https://docs.dify.ai/en/api-reference/human-input/get-human-input-form)

**不要混用 WebApp 内部 API 来宣称公开 API 无需鉴权。** 1.15.0 的 `/api/form/human_input/{token}` GET/POST 源码刻意不做账户鉴权，以 form token 作为访问凭证，并限流；但 `/api/workflow/{id}/events` 继承 `WebApiResource`，仍走 WebApp passport/用户校验。公开稳定的集成路径应优先使用上面的 `/v1` app-key API；内部 WebApp API 的存在不等于外部 Vue 可以跳过其身份、域与站点约束。[Web form 控制器](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/web/human_input_form.py#L146)、[Web resume 流](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/web/workflow_events.py#L30)、[Web token 校验](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/web/wraps.py#L40)

## 已确认：问题和选项能动态到什么程度

- **问题正文可以来自上游输出。** 原生节点表单正文允许引用 workflow 变量，适合引用插件输出的 question/说明文字；节点自己提供交互字段。官方文档明确支持正文中的动态数据。[Human Input 节点文档](https://docs.dify.ai/en/cloud/use-dify/nodes/human-input#form-content)
- **单选列表可以来自上游 `array[string]`。** 1.15.0 `SelectInputConfig.option_source` 支持 variable selector；Dify 将 `ArrayStringSegment` 的实际值注入客户端看到的 options。插件可以输出普通变量，转换器把它们加到节点 outputs，因此接到固定表单字段在接口层面成立。[select 解析](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/human_input_policy.py#L113)、[插件变量输出](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/message_transformer.py#L159)、[结果合并](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/message_transformer.py#L287)
- **普通 Human Input 节点的字段结构与 actions 是 workflow 配置。** 其类型是 `form_content`、`inputs[]`、`user_actions[]`；select 的 options 有 variable source，但没有发现“把插件一个 JSON 输出解释成整份动态 form schema”的节点输入口。动态选择值不等于动态字段数量、字段类型和分支按钮。内置 Agent v2 动态创建整份 form 的代码是上节的独立例外。[1.15.0 节点配置](https://github.com/langgenius/dify/blob/1.15.0/web/app/components/workflow/nodes/human-input/types.ts#L12)、[options source](https://github.com/langgenius/dify/blob/1.15.0/web/app/components/workflow/nodes/human-input/types.ts#L73)、[节点创建表单参数](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/node_runtime.py#L849)
- **字段能力不完全等同当前 AskUser。** 1.15.0 有 paragraph、select、file、file-list；这里的 select 是单选。若仍要多选、任意多问题、每选项独立说明或运行中任意变化的表单，需要额外适配/降级，不能据此宣称现有 AskUser 结构完全映射。select/file 选项属于该版新增表单功能。[1.15.0 字段联合类型](https://github.com/langgenius/dify/blob/1.15.0/web/app/components/workflow/nodes/human-input/types.ts#L86)、[发行说明](https://github.com/langgenius/dify/releases/tag/1.15.0)

## 可推导但未实测的架构

原生方案可以是：`插件执行并返回 pending + question + options + state → If/Else → Human Input 节点 → 同插件的另一次调用（带回答与 state）→ 后续结果`。可把正文绑定到 question，固定 select 的 options 绑定到 `array[string]`；固定 Submit action 后将 answer 交回插件。它依赖已确认的变量输出、原生节点、submit/resume 机制，但**完整链路未运行**。[变量输出与完成](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/message_transformer.py#L277)、[Human Input runtime](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/node_runtime.py#L849)、[恢复入口](https://github.com/langgenius/dify/blob/1.15.0/api/services/human_input_service.py#L265)

这条路会引入以下应用层工作：

1. 插件在正常返回时保存完整待回答状态；native pause 不会保存或继续 Python generator 的中间栈。答复后第二次 Agent node invocation 必须显式接回同一逻辑会话。
2. 显式配置原生 form 节点和回答后的插件节点；第一次、第二次 invocation 的状态写回、问题 ID 和重复提交保护都要设计。仅把 UI 换成原生 form，不能删除这些责任。
3. 多次 AskUser 需要重复图结构或可靠循环；当前研究没有在 **1.15.0** 验证其可用性。Dify **1.17.0** 才将 Human Input 在 Loop/Iteration 内的支持列为新功能，所以不能用最新版本的示例为 1.15.0 作成熟度背书。[1.17.0 发行说明](https://github.com/langgenius/dify/releases/tag/1.17.0)
4. 新 Vue 还要处理原生 paused/form-filled/form-timeout、表单 token 与过期、submit、接回同一 workflow 流及刷新恢复。这可能比在现有聊天 SSE 上显示一张轻量提问卡片更重。

上面 1–4 是从接口边界推导的实施成本，并非本次发现所有这些问题已经发生。尤其**不要把模型答复/业务 AskUser 与工具执行授权混为一体**：原生 form 的一次提交本身不证明 Dify/插件的模型或工具策略允许该动作。当前任务已约定模型与工具授权仍由 Dify 管理。

## 与保存问题后下一轮聊天的比较

| 方案 | 可复用内容 | 本项目仍需承担 | 判断 |
| --- | --- | --- | --- |
| 保存 pending，下一次 chat 带回答 | 现有 `UserPrompt`/`UserInterrupts` 的问题关联、历史结果修补和跨轮状态；Dify 的现有聊天传输 | 简洁 question/options DTO、轻量 Vue 卡片、输入回答与刷新恢复 | 最适合此次移除 AG-UI 依赖，同时保留 AskUser |
| 配置原生 Human Input 节点 | Dify 表单存储、token、过期、原生 worker resume、SSE 生命周期 | 外层图编排、再次调用插件、pending/state 桥接、更多 API/UI 状态 | 可作为限定业务流程的独立验证，不能作为插件直接暂停的替换 |
| 改用 Dify Agent v2 AskHuman | Dify 内置 agent 的动态 form/deferred results | 迁移到其 agent runtime，不是当前 Python Pi AgentStrategy 交付边界 | 不属于这次前端简化的直接选项 |

本地已有实现依据：`UserPrompt` 返回 `requires_user_input` 和规范问题；`UserInterrupts.resume()` 核验 pending tool-call ID 后把既有 tool result 改成用户回答；普通 query 也有识别为回答的入口。说明下一轮恢复并非必须依赖 AG-UI 的原生暂停，前端协议可以另行简化。这里仅确认现有代码，不声明换为 Pi 后已验证行为。[UserPrompt](../../cc_agent/core/internal_tools.py#L168)、[现有恢复](../../cc_agent/core/interrupts.py#L38)、[query 回答入口](../../cc_agent/core/interrupts.py#L144)

## 版本与验证限制

- **最低 1.7.0 不能依赖这套 native form 契约。** 固定 tag 的节点枚举没有 Human Input；递归源码树也没有 `human_input`/`human-input` 路径。不能因目标生产是 1.15.0，就把 native form 变成所有 `>=1.7.0` 安装的必需能力。若未来采用，须做清晰的 capability/version 限制和回退，或另行重新决定支持范围。[1.7.0 节点枚举](https://github.com/langgenius/dify/blob/1.7.0/api/core/workflow/nodes/enums.py#L4)、[1.7.0 完整 tree API](https://api.github.com/repos/langgenius/dify/git/trees/1.7.0?recursive=1)
- **源码有 API 和测试，不等于本部署已验证。** 未连生产 Dify；未测 CORS、宿主代理、WebApp delivery、并发提交、断流重连、worker 延迟、刷新、同会话再提问、插件状态写回，也未测离线环境该版完整运行。
- **1.15.0 有公开的 resume 输出异常报告。** 用户报告经过 Human Input 后 Answer 节点运行成功，但 UI/持久化答案缺失，涉及条件分支或多次暂停。它们是第一方 issue 中的用户报告，本文没有复现或确认其根因/所有适用范围，因此不能直接判定每个原生流程都坏；但不足以把该版方案称为已验证、成熟且更简单。[#38432](https://github.com/langgenius/dify/issues/38432)、[#38824](https://github.com/langgenius/dify/issues/38824)

若后续真要评估原生路线，先用一个固定单选问题在 **1.15.0 实例**验证“插件返回 state → native form → 答复 → 第二次插件调用 → 正常答案”，再验证第二次 AskUser 与刷新恢复。未完成这项小验证前，不应删除现有 pending 恢复机制或据此承诺动态 native AskUser。
