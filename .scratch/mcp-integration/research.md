# CC Agent 接入 MCP 的路径调查

日期：2026-10-26（Asia/Shanghai）。参考目录：`/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main`，manifest 版本 `0.2.5`；该下载目录没有 Git 元数据，本次按本地文件调查。用户最终确认通过 CC Agent 的 `mcp_servers_config` 参数，由 Dify 替换用户 header 后直连远程 MCP，已授权 implement。实现范围见 [spec.md](spec.md)，以下保留调查过程与方案比较。

## 结论

CC Agent 可以使用 MCP 工具，且当前外部工具调用通道没有排斥 `mcp` provider。应先区别两项需求：

1. 调用由 Dify 配置、授权并注入的 MCP 工具：复用现有 `tools -> ToolCatalog -> ToolAdapter -> session.tool.invoke` 通道。
2. 在 CC Agent 节点直接填 `mcpServers` JSON，由插件连接、发现和调用工具：新增一个远程外部工具来源与客户端生命周期。

第一条符合现有 ADR-0001 的 Dify 注入边界，维护成本更低。第二条是参考插件的形态，技术上可行，但会增加连接、配置、错误、结果映射等职责；不能通过复制它的 AgentLoop 实现，应该复用本项目已有循环和工具调度。

## 参考插件如何工作

- [function_calling.py](/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main/strategies/function_calling.py:85)：解析 `mcp_servers_config`，建立 `McpClients`，发现工具并加入模型的工具列表。
- [mcp_client.py](/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main/utils/mcp_client.py:430)：支持多个服务，以及顶层 `mcpServers` 或直接 server map 两种 JSON 形式。
- 支持远程旧 HTTP+SSE 与 Streamable HTTP，支持 headers、超时；没有 stdio 本地子进程接入。
- 使用自写同步 JSON-RPC 客户端，没有依赖官方 MCP SDK。`requirements.txt` 只有 `dify_plugin==0.7.1`、`httpx-sse`、`orjson`。
- 可选把 resources/resource templates/prompts 包装成可调用工具；这不是仅做 tools/list、tools/call。
- MCP 结果主要转换为字符串后交给模型；图片/资源等会被 JSON 序列化，不能等同于本项目已有的 blob/附件展示路径。

## 当前 CC Agent 已有的通道

- [ToolRegistry](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/tool_registry.py:47) 把 Dify 工具注册为 external，保留原始 provider 与名称。
- [ToolAdapter](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/tool_adapter.py:83) 将 provider 类型、provider、原始工具名称和参数交给 Dify session。
- [_tool_provider_type](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/tool_adapter.py:156) 读取 provider_type/tool_provider_type/tool_type 等字段，没有限定只能 builtin。
- 本地 `dify_plugin-0.7.4` wheel 的 `ToolProviderType` 包含 `MCP = "mcp"`，`ToolInvokeInvocation.invoke` 会将该值作为 `tool_type` 发给 Dify。
- 该 SDK 的 AgentStrategy 工具 schema 转换支持 `parameter.input_schema`；本项目字典工具的 [_parameter_schema](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/runtime.py:808) 也支持 input_schema。实际 Dify 注入对象形态仍需以目标部署联调为准。
- 已执行一次无网络 fake Dify session 验证：MCP 工具进入 catalog 后 kind 为 external，执行时 provider_type 保持 `mcp`，provider/原始工具名/参数正确传递，返回文字 observation 正常。该验证没有导入真实 SDK，也没有连接生产 Dify，不能代替端到端验收。

Dify 从 1.6.0 引入内置双向 MCP，见[官方发布说明](https://dify.ai/blog/v1-6-0-built-in-two-way-mcp-support)。当前[官方工具文档](https://docs.dify.ai/en/cloud/use-dify/workspace/tools#connect-an-mcp-server) 说明可配置 HTTP MCP 服务、授权并导入工具，供应用/Agent 节点调用。目标部署版本和服务可达性尚未确认，不能据此宣称生产已经接通。

## 参考代码中不应照搬的行为

1. **同名工具路由不完整。** [_iter_tools](/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main/utils/mcp_client.py:473) 在内部映射冲突时改成 `server__name`，但 yield 的 schema 仍保留原始 name；[execute_tool](/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main/utils/mcp_client.py:614) 又直接把展示名称传给远端。多个服务同名时，模型可见 schema 与内部路由可能不一致，远端也可能收到它不认识的别名。应始终分开 exposed name、server identity 与原始工具名。
2. **返回语义被丢弃。** [call_tool](/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main/utils/mcp_client.py:71) 只返回 `result.content`，没有保留 `isError` 或 `structuredContent`。`tools/list` 也未遍历 `nextCursor`。这些字段在[固定版本 MCP 工具规范](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) 中有明确语义。
3. **SSE 等待不完整。** [send_message](/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main/utils/mcp_client.py:267) 使用不带 timeout 的 `Event.wait()`；监听线程后续失败时，此处没有检查失败事件，存在请求长期等待的路径。
4. **Streamable HTTP 处理过于简化。** [send_message](/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main/utils/mcp_client.py:351) 使用非流式 POST，遍历 SSE 后仅保留最后一个消息，没有按 JSON-RPC id 定位响应；初始化仍声明 `2024-11-05`，没有完整处理协商版本。这不是一个可直接宣称适配所有当前服务的实现。旧 HTTP+SSE 与 Streamable HTTP 是不同传输，参见[固定版本规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)。
5. **敏感信息进入日志。** 客户端记录 response headers、完整响应体、调用参数与工具结果；SSE endpoint URL 也会被记录。若服务将凭证放在 URL/header 或返回内容中，这会违反本项目不记录配置秘密的约束。
6. **清理不覆盖异常退出。** [function_calling.py](/home/ygao/Downloads/dify-plugin-agent-mcp_sse-main/strategies/function_calling.py:451) 在主流程尾部 close，没有包裹整个调用的 finally；部分初始化失败、模型异常或生成器提前退出时可能跳过释放。

以上为本地源码静态观察，没有运行该参考插件或其服务端。

## 如果选择直连

建议作为 ToolCatalog 的另一种外部工具来源，复用 ToolAdapter/调度/预算/权限/结果事件，不向 InternalToolExecutor 加入通用文件或执行能力。AG-UI、Dify 两个输出策略共享此工具来源，前端继续消费现有工具事件。

第一版候选范围是远程 tools：Streamable HTTP 为优先，是否需要旧 SSE 由目标服务决定；resources/prompts 包装、stdio、MCP elicitation/sampling 不自动纳入。连接按本轮运行管理，在 finally 释放；用户中断结束本轮后，下一轮重新发现并按稳定身份路由。配置凭证不能进入 prompt、agent_state、工具 metadata 或错误原文。

工具 schema 保留嵌套对象/数组；同名采用稳定命名并维护原名映射；保留结果错误标记和结构化输出；图片/blob/resource 需要映射到 Dify 的产物输出，而不能把 base64 全量塞进历史。新依赖需同步 pyproject、requirements、lock 与双架构离线 wheels。

直连意味着重新讨论现有“外部能力统一经 Dify 注入”的边界，需在选择方案时明确记录；当前调查不替用户做这个决定。

## 当前问题

已明确：通过 Dify 接入 MCP；需要每次调用按当前业务用户鉴权，而非仅使用全应用固定身份。

生产版本已由用户确认为 Dify 1.15.0。因此不能使用本次在 1.16.0 核对到的 `request.headers` 动态替换；当前原生 MCP 的静态 header 不足以直接满足每次调用传递不同用户凭证的需求。

重要区别：这个限制不适用于参考策略插件的整份配置入参。参考插件在每次 `_invoke` 时读取 `mcp_servers_config`、解析 JSON、创建新的 McpClients，并将其中 headers 交给 HTTP 客户端；Dify 可以直接在 Agent 参数中替换变量，也可由上游节点生成完整 JSON 后绑定到策略参数。这不依赖 Dify 原生 MCP header 模板功能，也不需要因此升级 Dify。插件本身不解释 `{{token}}` 占位符。

进一步核对 [1.15.0 AgentRuntimeSupport](https://github.com/langgenius/dify/blob/1.15.0/api/core/workflow/nodes/agent/runtime_support.py)：Agent 参数的 variable 类型直接读变量；mixed/constant 类型会执行 `variable_pool.convert_template`。因此，上游模板/代码节点不是必须步骤。CC Agent 的新 string 参数可以开启 `template.enabled: true` 以提供明确的模板编辑入口，配置 JSON 中通过 Dify 变量选择器插入用户变量，解析 JSON 前由 Dify 完成替换。

用户提出的候选配置为单个 `mcp_servers_config` 参数，保留 server/transport/url/headers/timeout，headers 内引用本次用户 ID。Service API 的 `user` 被存入 EndUser.session_id，[EndUserService](https://github.com/langgenius/dify/blob/1.15.0/api/services/end_user_service.py) 和 [AdvancedChatAppGenerator](https://github.com/langgenius/dify/blob/1.15.0/api/core/app/apps/advanced_chat/app_generator.py) 表明该值用于外部 API 调用的系统 user_id；控制台调试则使用账号 ID，不应混同。简单用户标识的模板插入可直接使用；包含任意特殊字符的动态值或动态结构应由代码节点做 JSON 编码。

参考项目是 Agent 策略插件，不能作为普通工具直接选入 CC Agent。若 CC Agent 采用相同方式，需要在自身策略增加运行时配置/用户凭证入参及 MCP 外部工具适配；可以复用现有循环、状态与输出协议。本文中的“Dify 原生管理 MCP”与“在 Dify 中运行的策略插件自行连接 MCP”不应混称为同一种接入。

已决定：保持 1.15.0，新增策略参数和远程 MCP 适配。每轮带当前用户 header 发现、调用工具，不复用其他用户的工具目录；最终授权由 MCP 服务实施。本次不增加另一套本地用户权限管理或手工工具筛选产品。

## 按用户传递 header 的补充调查

- [Dify 当前官方工具文档](https://docs.dify.ai/en/cloud/use-dify/workspace/tools#custom-headers) 支持配置自定义 header，并记录 `{{request.headers.X-Custom-Auth}}` 的动态替换。它读取 HTTP 请求 header，不读取 body 的 `user`，也不读取 workflow 的 `inputs.token`。
- 已通过 GitHub connector 对比源码：[1.16.0 MCPClient](https://github.com/langgenius/dify/blob/1.16.0/api/core/mcp/mcp_client.py) 有基于 Flask request context 的模板替换；[1.15.0 同文件](https://github.com/langgenius/dify/blob/1.15.0/api/core/mcp/mcp_client.py) 没有。对应 [PR #37938](https://github.com/langgenius/dify/pull/37938) 已合并。这里仅说明核对版本的差异，不以最新文档推断用户部署已支持，也不推断所有旧版本/定制版本的行为。
- 模板匹配缺失 header 时替换为空字符串；没有 request context 时保留占位符。因此仍需验证 CC Agent 的 `session.tool.invoke` 回调 Dify 之后，读取到的是否为原始 Service API 请求的上下文，不能只凭 MCPClient 单元行为声称整个插件路径可透传。
- 当前前端 [difyTransport.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/difyTransport.ts:305) 只发送 App API Key 与 Content-Type；`user` 在 JSON body 中。[DifyAgUiAgent.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/DifyAgUiAgent.ts:583) 把配置中的 token 放到 `inputs.token`。当前没有业务用户凭证到 MCP header 的自动映射。
- 候选接线：调用 Dify Service API 时保留 `Authorization: Bearer <Dify App Key>`，额外发送 `X-Business-Token: <当前业务用户 token>`；Dify 的 MCP header 配置为 `Authorization: Bearer {{request.headers.X-Business-Token}}`（假设传入值不含 Bearer 前缀）。这只是接线样例，最终 header 名称与 token 格式需匹配业务服务。
- 请求 body 的 `user` 继续作为 Dify 用户/会话标识。MCP 服务依据已验证的用户凭证执行授权；客户端可改写的 userId 不能单独作为授权凭证。工具列表筛选与每次调用的数据/操作授权是两个需求，后者不能由前者代替。
