# CC Agent

CC Agent 是 Dify Agent Strategy 插件，提供工具调用、技能、记忆、任务和跨轮会话状态。会话状态统一通过 Dify 的 `agent_state` 变量流转；文件读取、代码执行、检索和文件生成由 Dify 注入的工具或配置的远程 MCP 服务提供。

## 项目结构

- `cc_agent/`：Python ≥3.12 的 Dify 插件，包含共享运行时、两个策略入口、内置技能和测试。
- `copilotkit-dify/`：Vue 3 + Vite 前端，消费 AG-UI / Dify 流并展示工具过程、结构化答案、附件和交互中断。

## 运行流程

```text
Dify AgentStrategy
  -> AgentRunConfig
  -> RunEnvironment
       -> DifyStateBackend：加载 agent_state
       -> SkillCatalog：内置技能 + app_skills_yaml
       -> ToolCatalog：内部认知工具 + Dify 外部工具 + 远程 MCP 工具
       -> ProtocolRenderer
  -> AgentLoop：上下文预算、模型调用、工具串行调度、权限与结果预算
  -> DifyStateBackend：编码新的 agent_state
  -> 输出最终结果和 state_summary
```

两个策略共享同一运行时和状态路径：

| 策略 | 输出与交互 |
| --- | --- |
| `CC Agent (AG-UI)` | AG-UI 事件；提供 `UserPrompt` 中断和 `answers-ui` / `answers-charts` 技能。 |
| `CC Agent (Dify)` | Dify 原生 text、JSON、blob 和 log；不注入结构化答案提示或 `UserPrompt` 工具。 |

## Dify 配置

| 参数 | 用途 |
| --- | --- |
| `model` | 必填。支持工具调用的 Dify 模型。 |
| `query` | 必填。当前用户输入。 |
| `tools` | Dify 注入的外部工具。 |
| `mcp_servers_config` | 可选的远程 MCP 服务 JSON；支持在 headers 中插入 Dify 用户变量。 |
| `instruction` | 应用的业务角色、约束和回答要求。 |
| `max_total_context_tokens` | 上下文窗口，默认 131072 tokens，最低 4096。 |
| `agent_state` | 上一轮输出的编码状态。首轮留空。 |
| `files` | Dify 上传附件的 JSON；提供安全的文件标识、名称、类型和大小信息。 |
| `app_skills_yaml` | 应用级技能定义。 |
| `runtime_config` | 可选的高级运行参数 JSON。 |
| `show_tool_calls` | 是否展示工具过程，默认开启。 |
| `deepseek_thinking_compat` | DeepSeek thinking 兼容回退，默认关闭。 |

将最终输出的 `agent_state` 写回 Dify 对话变量，并在下一轮映射到同名入参。`files` 元数据不代表模型已经读取文件内容；应用需为文件处理配置相应的 Dify 外部工具。

`runtime_config` 示例：

```json
{
  "maximum_iterations": 8,
  "max_observation_chars": 8000,
  "max_history_messages": 40,
  "max_total_context_tokens": 131072,
  "max_repeated_tool_calls": 3,
  "max_consecutive_tool_errors": 3,
  "state_reset": false
}
```

通常可留空。未知字段被忽略。节点上的 `max_total_context_tokens` 优先于 runtime_config；旧 `max_total_context_chars` 配置别名仍被接受，但按 token 限额解释。

## 会话状态

`agent_state` 使用 `ccagent-state:v1:gzip-base64:` 前缀，包含历史与摘要、记忆、任务、工具授权、已加载技能和上一轮执行元信息。编码器会按 Dify 对话变量约 190KB 的限制压缩或裁剪状态。

输出还包含：

- `state_summary`：历史、记忆、任务数量及等待用户、结束原因等只读摘要，不用于恢复状态。
- `state_ref`：`backend=conversation_variable` 的状态元信息，包含会话标识、版本和保存状态。前端可用它恢复会话标识。

上下文溢出时先压缩历史再重试一次。工具失败会生成配对的错误 observation，每个 assistant tool call 都必须在下一次模型调用前得到 tool result。

## 技能和工具

技能来源为随插件打包的 `skills/*/SKILL.md` 和 `app_skills_yaml`。应用技能不能覆盖保留的内置技能名称。`Skill` 按需加载技能正文，`SkillReadResource` 读取技能自身的文本参考资料，并校验路径边界。

内部工具：

- 技能：`SkillList`、`Skill`、`SkillReadResource`。
- 记忆：`MemoryList`、`MemorySearch`、`MemorySave`、`MemoryDelete`。
- 任务：`TaskCreate`、`TaskUpdate`、`TaskGet`、`TaskList`。
- AG-UI 交互：`UserPrompt`。

用户命令包括 `/help`、`/status`、`/context`、`/cost`、`/compact`、`/reset`，以及两个现有的界面演示命令 `/a2ui-demo`、`/weekly-report-card`。

内部工具只处理认知与会话状态。外部文件、执行、搜索和浏览能力由 Dify 工具或配置的远程 MCP 服务提供，返回的文字、JSON、图片、链接和 blob 仍按原有协议展示。

## MCP 工具

两个策略都支持 `mcp_servers_config`。Dify 1.15.0 的 Agent 参数变量替换即可使用，无需依赖原生 MCP 的动态 header 功能。在节点的 MCP 配置框中填写 JSON，并通过变量选择器插入 `sys.user_id`：

```json
{
  "business": {
    "transport": "sse",
    "url": "http://mcp-service:8000/sse",
    "headers": {
      "X-User-Id": "{{#sys.user_id#}}"
    },
    "timeout": 50,
    "sse_read_timeout": 50
  },
  "search": {
    "transport": "streamable_http",
    "url": "http://search-mcp:8001/mcp"
  }
}
```

也接受 `{ "mcpServers": { ... } }` 包装。留空不连接 MCP；省略 transport 默认为 sse，两个超时值默认均为 50 秒，必须是正数。地址需能从 Dify 插件运行环境访问，`127.0.0.1` 指插件所在环境。配置错误或任一服务初始化失败会结束本轮并返回错误，避免静默缺少工具。

Dify 在调用插件之前完成变量替换，插件不再解释模板。通过 Service API 发起会话时，前端请求中的 `user` 对应 `sys.user_id`；控制台调试使用调试账号身份。MCP 服务根据已验证的身份执行授权；用户 ID 本身不是认证凭证。需要业务 token 时，可在 Authorization 等 header 中插入开始节点或上游节点的 token 变量。复杂动态值可先在代码节点用 JSON 编码生成完整配置，再绑定此参数。

每轮重新建立 MCP 连接并发现 tools，包含分页；工具暴露为 `mcp__服务名__工具名`，特殊字符和过长名称使用稳定摘要，实际请求保持远端原始工具名。它们与 Dify 注入的工具共存，复用结果预算和失败配对。保留工具错误标记、结构化结果与文件产物；不自动包装 MCP resources/prompts，也不支持 stdio。结束、失败、中断或提前关闭运行时释放连接，下一轮重新使用当次注入的 header。

接入 MCP Apps 服务时，只注册普通且对模型可见的工具。带 `_meta.ui.resourceUri` 的 App 入口，以及 `_meta.ui.visibility` 明确不含 `model` 的工具均过滤；兼容旧字段 `_meta["ui/resourceUri"]` 和 `_meta["openai/outputTemplate"]`。未声明 visibility 时默认模型可见；声明格式无效时不注册。普通数据工具的 `["model", "app"]` 可见性仍保留，不按工具名称前缀判断。过滤后的工具不进入提示，也不能通过本地工具目录调用。

当前 CT MCP 默认 21 个契约工具经过过滤后保留 12 个普通业务工具，移除 5 个 App 入口和 4 个 App helper。连接使用 `streamable_http` 与 `/mcp` 地址；身份头是 `X-Employee-Id`，值需为真实工号，并按 CT 服务的鉴权方式配置 API Key 或 token。只有 Dify 的 `user` 本身就是工号时，才直接将 `sys.user_id` 用作该值。

插件不把 MCP 配置写入提示、会话状态或自身输出日志，并脱敏服务回显的配置凭证。Dify 平台对输入变量和节点参数的日志记录仍由 Dify 自身管理。边界取舍见 [ADR-0002](docs/adr/0002-runtime-mcp-tools.md)。

## 升级说明

MinIO 模式及其配置参数 `capability_mode`、`storage` 已移除。工作区、内置文件 CRUD、`run_python`、`SkillRunScript`、`SkillInstall`、`SkillRemove` 和 `/skill` 管理命令一并撤除。

升级旧工作流时，请重新配置节点，移除旧参数并接好 `agent_state` 对话变量。运行时不再读取旧存储参数，也不提供模式兼容或远端状态迁移；原 MinIO 桶内数据不会被访问或删除。需要的文件和执行能力请改为 Dify 外部工具。

该取舍见 [ADR-0001](docs/adr/0001-dify-owned-state.md)。

## 测试与打包

从仓库根目录运行：

```bash
python -B -m unittest discover -s cc_agent/tests
```

前端：

```bash
cd copilotkit-dify
npm install
npm run test
npm run build
```

离线包（Python 3.12，依赖 wheel 已在 `cc_agent/wheels/`）：

```bash
python cc_agent/scripts/build_offline_package.py
```

脚本验证 Linux amd64/arm64 的离线依赖解析，再生成 `cc_agent/dist/*.difypkg`。更新依赖时需同时维护依赖声明、锁文件和离线 wheels。

手工验收：连续两轮传递 `agent_state`，确认记忆和任务保留；调用一个 Dify 外部工具并检查结果展示；在 AG-UI 中完成一次 `UserPrompt` 中断与恢复；确认 Dify blob 附件可展示和下载。
