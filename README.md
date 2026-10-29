# CC Agent

CC Agent 是 Dify Agent Strategy 插件，提供工具调用、技能、任务和跨轮会话状态。会话状态统一通过 Dify 的 `agent_state` 变量流转；文件读取、代码执行、检索和文件生成由 Dify 注入的工具或配置的远程 MCP 服务提供。


## Pi Agent v2（新插件）

`pi_dify/` 是按 v2 规格新建的独立 Dify Agent Strategy 插件，复用固定 0.6.0 的 Python Pi Harness；`pi_workbench/` 是从 Leyline 固定提交抽取的静态 Vue 工作台。两者与旧 `cc_agent/`、`copilotkit-dify/` 并存，旧插件和旧前端不改协议、不迁移旧状态。

- 插件说明、Dify 节点映射、技能/MCP/交互格式与离线构建：[pi_dify/README.md](pi_dify/README.md)
- 工作台构建、静态部署、回放与安全边界：[pi_workbench/README.md](pi_workbench/README.md)
- 逐票实现与已验证/未验证证据：[docs/evidence/v2-implementation.md](docs/evidence/v2-implementation.md)
- 实施决策：[ADR-0008](docs/adr/0008-pi-agent-v2-implementation.md)

当前核心代码与本地测试已完成；真实 Dify 版本、真实 provider 流、真实远程 MCP 和 arm64 执行尚未在本环境验收，不能以本地 fake 或静态构建替代平台证据。

```bash
python -B -m unittest discover -s pi_dify/tests
cd pi_workbench && npm install && npm run test && npm run build && npm run check:static
cd ../pi_dify && python3 scripts/build_offline_package.py --arch amd64
```

## 项目结构

- `cc_agent/`：Python ≥3.12 的 Dify 插件，包含共享运行时、两个策略入口、内置技能和测试。
- `copilotkit-dify/`：Vue 3 + Vite 前端，消费 AG-UI / Dify 流并展示工具过程、结构化答案、附件和交互中断。
- `pi_dify/`：v2 独立 Pi Harness 插件（Python 3.12）。
- `pi_workbench/`：v2 静态 Vue 工作台，消费 `piagent.display.v1`。

## 运行流程

```text
Dify AgentStrategy
  -> AgentRunConfig
  -> RunEnvironment
       -> DifyStateBackend：加载 agent_state
       -> SkillCatalog：内置技能 + app_skills_yaml
       -> ToolCatalog：内部认知工具 + Dify 外部工具 + 远程 MCP 工具
       -> ProtocolRenderer
  -> AgentLoop：编排模型轮次与工具结果配对
       -> ModelRequests：请求预算、压缩与一次溢出重试
       -> UserInterrupts：确认、回答匹配与中断恢复
       -> SerialToolScheduler：策略检查、串行执行与结果预算
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
  "max_model_calls": 32,
  "max_tool_calls": 64,
  "max_run_seconds": 300,
  "max_run_tokens": 0,
  "tool_call_stream_mode": "delta",
  "max_observation_chars": 8000,
  "max_history_messages": 40,
  "max_total_context_tokens": 131072,
  "max_repeated_tool_calls": 3,
  "max_consecutive_tool_errors": 3,
  "state_reset": false
}
```

通常可留空。未知字段被忽略。节点上的 `max_total_context_tokens` 优先于 runtime_config；旧 `max_total_context_chars` 配置别名仍被接受，但按 token 限额解释。

`max_model_calls` 统计实际模型请求，包括摘要、续写、最终请求和重试；`max_tool_calls` 统计实际工具执行，包括批准中断后的执行。总预算在开始下一次调用前检查；达到限制时配对未执行工具结果，以 `budget_exhausted` 结束并保留已完成结果。`max_run_seconds` 为协作式耗时上限，不能强行终止已经开始的同步 SDK 或远程业务操作。`max_run_tokens=0` 不启用累计 token 上限；非零时按 provider 已报告用量检查。

工具参数流默认 `delta`：参数片段按顺序追加，保留重复字符；一次性返回完整工具调用同样适用。provider 若返回累计快照，配置 `tool_call_stream_mode=snapshot`，每块替换该工具调用的名称和参数。两种模式均归并同一 index 与后到/省略的 id，不根据 JSON 前后缀猜测模式。Dify 的具体 provider / SDK 输出应按部署版本取样验证。

## 会话状态

`agent_state` 使用 `ccagent-state:v1:gzip-base64:` 前缀，包含历史与摘要、任务、工具授权、已加载技能和上一轮执行元信息。编码器会按 Dify 对话变量约 190KB 的限制压缩或裁剪状态。

输出还包含：

- `state_summary`：历史、任务数量及等待用户、结束原因等只读摘要，不用于恢复状态。
- `state_ref`：`backend=conversation_variable` 的状态元信息，包含会话标识、版本和保存状态。前端可用它恢复会话标识。

`state_ref.persisted` 保留旧字段语义，表示状态已成功编码并通过容量检查；`delivery_status` 区分 `encoded`、`emitted` 和 `failed`。插件先输出 `agent_state` 变量，再输出运行终态。`platform_persisted=null` 表示插件无法确认后续 Dify 工作流已完成对话变量赋值；应通过下一轮读回核实。revision 是上一快照序号加一，不提供原子并发比较。

`execution_metadata.run_status` 区分 `completed`、`awaiting_user`、`failed`、`budget_exhausted`；`RUN_FINISHED` / `agent_finished` 表示本轮结束，不代表业务操作已成功。`run_budget` 包含模型/工具实际次数、已报告 token、耗时、预算原因及工具 outcome 计数。工具结果携带 run_id，异常远程调用继续标记 unknown。诊断默认不记录模型正文或附件原始 JSON。

`state_summary` 根据实际保存的压缩快照生成。会话授权只免除重复确认，仍受工具策略和服务端业务权限限制；批准的待执行工具也经过相同调度检查。

编码后再次检查 JSON 和编码值的容量。待确认操作的参数必须完整保留；无法装入变量时返回 `agent_failed`，其 `code=state_save_failed`、`state_ref.persisted=false`，不输出无效状态或正常完成终态。此前已执行的外部操作不会因此回滚，不能把保存失败当成业务操作失败并直接重试。

上下文预算只计算实际发送给模型的消息字段和工具 schema，展示产物不重复存进工具历史。旧结果在输入预算压力达到 80% 后优先缩减，最新未消费结果优先保留；摘要读取当前仍保留的缩减前内容，成功摘要完整替换旧摘要。当前用户请求与尾部工具组保留在近期历史中。固定指令和 schema 本身超限时直接拒绝，避免无效摘要调用。估算分别累计中日韩文字和其他字符，仍属于近似预算。

上下文溢出时先压缩历史再重试一次。工具失败会生成配对的错误 observation，每个 assistant tool call 都必须在下一次模型调用前得到 tool result。同批 Skill 正文在全部工具结果配对后注入；遇到用户中断，尾部尚未执行的调用收到明确的 skipped 结果，恢复后由模型重新决定是否调用。

未处理的运行异常在两种策略中均返回安全的 `agent_failed` JSON，带 `code`、`stage`、`run_id` 和异常类型，不输出原始异常或 traceback。外部工具传输失败标记 `execution_outcome=unknown`；对于写操作，应先通过业务查询核实结果。

## 技能和工具

技能来源为随插件打包的 `skills/*/SKILL.md` 和 `app_skills_yaml`。应用技能不能覆盖保留的内置技能名称。`Skill` 按需加载技能正文，`SkillReadResource` 读取技能自身的文本参考资料，并校验路径边界。

内部工具：

- 技能：`SkillList`、`Skill`、`SkillReadResource`。
- 任务：`TaskCreate`、`TaskUpdate`、`TaskGet`、`TaskList`。
- AG-UI 交互：`UserPrompt`。

用户命令包括 `/help`、`/status`、`/context`、`/cost`、`/compact`、`/reset`。

内部工具只处理认知与会话状态。外部文件、执行、搜索和浏览能力由 Dify 工具或配置的远程 MCP 服务提供。Dify 工具返回重复两半的结果时继续按语义去重，JSON 键顺序不同也保留一份。Dify 注入工具的文件、图片、链接等产物继续沿用原输出路径，插件不额外转发；直连 MCP 的 blob 由插件转发，包括批准中断后的执行结果。

`SkillCatalog` 统一技能选择、恢复和激活；旧会话的已激活技能仍受当前输出策略、入口资格和定义完整性约束。slash 与模型 `Skill` 调用使用同一激活路径，资源仍通过 `SkillReadResource` 按需读取。工具 allowlist / denylist 与技能 denylist 已移除；外部工具能力由应用配置和业务服务授权。重复调用、连续错误、总执行预算与旧中断恢复继续生效。

工具 schema 仍全量提供，匹配技能优先由提示驱动。技能正文承担流程和参数用法；长参考资料通过 `SkillReadResource(skill, path, offset=0, limit=12000)` 连续读取。`offset` / `limit` 按 Unicode 字符计算，`limit` 至少 128、最多 12000；最终页还受单条和批次结果预算限制。返回头部及 `resource_page` 元数据记录实际交付区间和 `next_offset`，继续读取时使用该位置，直至其为 `null`。页始终保留连续前缀，不按头尾截断后跳过中间内容。预算不足以容纳分页信息时明确报错。

`disable_model_invocation=true` 的技能不出现在模型目录中，也不能由模型直接激活；`user_invocable=false` 禁止 slash 激活。恢复已加载技能时校验定义摘要和完整性，定义变化、旧格式记录或保存时被裁剪的正文会重新变为可加载状态。本轮内保留完整已加载正文；跨轮仍受状态变量容量限制，不承诺恢复已经丢弃的远端原文。

前端 `runStream.ts` 统一解释原生 AG-UI 和 Dify fallback 运行流，保留原生事件字段、附件及中断。`conversationCoordinator.ts` 管理会话/thread 关联、历史加载请求和过期结果，切换期间不会把消息发送给旧 clone；不自动恢复上次会话。

加载已选会话时，前端同时从 Dify 会话变量接口读取 `agent_state`，有界解码并仅保留 revision、run_id、终态和待处理中断作为恢复视图；沿用相同历史 ticket 和过期结果检查。变量读取失败仍展示已保存历史，并提示交互状态不可用。前端检查停止请求响应；停止接收、停止请求成功和服务端业务结果分别表达。缺少可信终态的断流显示结果尚未确认，不自动重放在途工具。部署需验证会话变量读取接口、权限及 `agent_state` 映射。

技能正文在模型请求中只出现一份，历史保存简短激活记录。请求超限时优先释放较旧的活跃技能，保留最新完整正文；退出的技能可再次加载。当前任务投影聚焦未完成任务，全部任务仍可通过 TaskGet / TaskList 读取。预算元数据列出固定目录、工具、活跃技能、任务、附件、摘要和历史的估算成本。

业务成功验收、作业引用与未知结果核实见 [harness 验收指引](docs/harness-validation.md)。

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

0.0.4 移除四个 Memory 工具及 `/a2ui-demo`、`/weekly-report-card`，保留任务工具。旧 v1 状态中的 `memory` 在加载时忽略，下一次保存时移除；历史、任务、授权、已加载技能和待处理中断继续恢复。升级前请保存仍需要的旧记忆数据。该取舍见 [ADR-0003](docs/adr/0003-agent-feature-scope.md)。

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
npx tsc --noEmit
npm run build
```

离线包（Python 3.12，依赖 wheel 已在 `cc_agent/wheels/`）：

```bash
python cc_agent/scripts/build_offline_package.py
```

脚本验证 Linux amd64/arm64 的离线依赖解析，再生成 `cc_agent/dist/*.difypkg`。更新依赖时需同时维护依赖声明、锁文件和离线 wheels。

手工验收：连续两轮传递 `agent_state`，确认任务和授权保留；调用一个 Dify 外部工具并检查结果展示；在 AG-UI 中完成一次 `UserPrompt` 中断与恢复；确认 Dify blob 附件可展示和下载。
