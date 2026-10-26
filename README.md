# CC Agent

CC Agent 是 Dify Agent Strategy 插件，提供工具调用、技能、记忆、任务和跨轮会话状态。会话状态统一通过 Dify 的 `agent_state` 变量流转；文件读取、代码执行、检索和文件生成由 Dify 注入的外部工具提供。

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
       -> ToolCatalog：内部认知工具 + Dify 外部工具
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

内部工具只处理认知与会话状态。外部文件、执行、搜索和浏览能力由 Dify 工具提供，返回的文字、JSON、图片、链接和 blob 仍按原有协议展示。

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
