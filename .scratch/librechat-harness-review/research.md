# LibreChat 对照：Dify Agent 执行内核

> 以下保留调查阶段的证据与当时状态；2026-10-28 后续实施已完成，最终行为、验证及审查见 spec.md、validation.md、review.md。

日期：2026-10-27。只读代码调查与本地故障探针；本轮未改运行代码，未连接生产 Dify/MCP，未运行全量回归。

- CC Agent 基线：`951526723eb2f32eb90e52bc43e889c7762a5d16`。
- LibreChat 本地基线：`8ff185759e12eddd509dd84304a408276603c10f`。
- 用户已选择：Dify 插件内核；可靠性与问题定位优先；先恢复已保存状态并明确未知结果。最新已撤回排队，维持回复未完成前不发送新普通消息。
- 已有 `.scratch/agui-protocol-review/` 与本调查无关，未修改。

## 最新重点：skill first

用户明确具体 MCP 工具及参数会在后续优化，本轮希望 skill first。Q6 已澄清：**工具及参数 schema 全量提供，描述简洁；应用技能提供业务流程、参数用法、示例等调用知识，模型先读匹配技能再调用工具。** 保留现有完整工具目录，不采用按技能隐藏 schema、动态注册工具或固定技能执行器。

### 当前结构与技能契约缺口

| 代码事实 | 对设计的含义 |
| --- | --- |
| [prompt_builder.py:64](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/prompt_builder.py:64) 先提供技能索引，正文由 Skill 按需注入。 | 已有技能渐进加载，不需要重新建设 SkillCatalog。 |
| [model_requests.py:228](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/model_requests.py:228) 每轮取全部 `prompt_tools()`；[tool_catalog.py:80](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/tool_catalog.py:80) 返回全目录的 schema。 | 符合用户已确认的工具曝光方式。无需增加动态工具视图；总 schema 成本仍计入 ModelRequests 的现有预算。 |
| [app_skills.py:217](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/app_skills.py:217) 解析 `allowed_tools`，但目前只作为元数据展示。 | 不为 skill first 把它改造成授权或工具可见性限制；保留现有行为，避免无关的权限模型扩张。 |
| [skill_catalog.py:50](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/skill_catalog.py:50) 统一 slash/模型激活，但不检查 `user_invocable` / `disable_model_invocation`。 | skill first 放大了入口资格的重要性，应在共享激活边界落实，不能只隐藏目录。 |
| [skill_catalog.py:42](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/skill_catalog.py:42) 跨轮恢复最多八个已加载记录，保留旧 summary；activate 仅保留正文前 5000 字符。 | 指令更新后可能继续使用旧摘要；正文后部的流程和参数说明也可能缺失。模型又被提示不要重复加载 active 技能，需要让实际执行时能取得当前完整指令。 |

子代理无 SDK 内存 probe：技能声明 `allowed_tools=['read_report']`、`disable_model_invocation=True`、`user_invocable=False`，模型工具集在激活前后仍同时包含 read_report/delete_report，模型 `Skill` 调用也成功。新加未知字段 `tool_dependencies` 只进入 metadata，不产生行为。主代理已核查相关源代码，未将 probe 加成正式测试。

### LibreChat 实际值得借鉴的技能机制

1. **目录、正文、资源分层。** [initialize.ts:2586](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/initialize.ts:2586)、[skills.ts:787](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/skills.ts:787)、[handlers.ts:5288](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/handlers.ts:5288) 将技能目录放入模型上下文，激活后再注入正文和可选文件。CC 已有相似边界，可借预算和资格校验，不引入其工作区。
2. **手动技能工具声明与 agent 基线工具取并集。** [initialize.ts:1444](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/initialize.ts:1444)、[skills.ts:1757](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/skills.ts:1757) 在初始化前合并工具；动态模型 skill handler 返回正文/资源，没有依据 allowed-tools 动态改写工具表。因此它不是已实现“首轮隐藏全部业务 schema”的现成方案。
3. **资格在目录与执行入口都检查。** [skills.ts:549](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/skills.ts:549)、[handlers.ts:5232](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/handlers.ts:5232) 区分可访问、启用、模型可调用、手动可调用。技能声明不能越过应用政策或业务服务权限。
4. **技能目录有独立预算。** [skills.ts:95](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/skills.ts:95) 设置目录数量和 description 长度上限，遗漏有诊断。具体 context 比例算法位于外部 Agents SDK，本轮没有验证其实现。
5. **deferred tools 是独立机制。** [classification.ts:425](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/tools/classification.ts:425)、[run.ts:2512](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/run.ts:2512) 接入 registry/tool_search/已发现 schemas；真正模型绑定行为依赖外部 SDK。不能据此直接决定 CC 要新增 tool_search，也不能把技能激活等同于工具发现。

### 适合已确认方向的候选改进

1. 沿用技能目录 → Skill 正文 → SkillReadResource 参考资料的加载路径，明确“哪些任务适用、如何组织流程、参数含义、成功/失败例子”。工具 schema 保持真实的类型和必填约束，具体描述精简留给后续 MCP 改造。
2. 用户 Q7 已确认先加载匹配技能保持提示驱动，不增加运行时门禁；当前 blocking requirement 提示与这一方向一致。
3. 已加载记录应能识别技能定义变更；恢复后必须有渠道取得当前完整指令，不把旧的前 5000 字摘要当成永远完整且有效的正文。采用重载、更新标记或重建上下文的具体方式留待实施设计，不提前扩展状态格式。
4. 在共享激活边界落实 user_invocable / disable_model_invocation，覆盖 slash、模型和恢复；继续保留 denylist、输出策略差异和资源路径检查。
5. 借鉴 LibreChat 的目录/正文/资源预算与遗漏诊断，在现有 ModelRequests 总预算之内识别技能上下文成本。全量工具的执行仍由 scheduler 政策与业务服务授权约束，加载技能不产生新权限。

先前提出的按技能选择 schema 是对“skill first”的另一种解读，用户已明确本轮保留全量工具，因此该方案不进入本轮候选，不据此新增 tool_search、依赖选择器或动态注册层。

## 结论与现有优势

值得借鉴的是执行生命周期、失败与未知结果的语义，以及执行权由谁持有。LibreChat 自己拥有 HTTP 入口、generation store、持久化和恢复服务，CC Agent 处于 Dify Strategy 插件边界，不能把这些能力视为可直接移植的代码模块。

CC Agent 已具备共享 runtime、RunEnvironment、ModelRequests、UserInterrupts、ToolCatalog、SkillCatalog、ProtocolRenderer。上轮架构优化也已经实施；再次提出拆 loop、集中工具目录或统一模型重试，并不能解释本轮的新收益。会话授权仍经 scheduler 策略检查、工具结果配对、一次上下文溢出恢复、MCP 每运行隔离等应继续保留。

## 1. 首先修复状态容量与保存结果契约

现状：

- [state_variable.py:266](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/state_variable.py:266) 最小化后直接返回，没有最终容量失败分支。
- [state_variable.py:190](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/state_variable.py:190) 只以编码非空设置 `persisted=True`。
- [state_backend.py:76](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/state_backend.py:76) 据此构造 `state_ref`；它准备变量输出，无法观察后续 Dify 工作流是否真正写回对话变量。

主代理独立复现：真实 UserInterrupts 产生带 40000 字符参数的待确认工具，编码结果为 `encoded_bytes=404037`、`payload_bytes=403062`、`persisted=True`、`error=None`，配置上限为 `190000`。待确认参数被保留，但超限未触发保存失败。未测试 Dify 对该输出的真实接收结果。

复现命令（在 `cc_agent/` 目录运行，不依赖 Dify SDK，不写文件）：

```bash
python3 -B - <<'PY'
import json, random, string
from core.interrupts import UserInterrupts
from core.messages import AgentState, AssistantTurn, ToolCall, assistant_message
from core.state_variable import encode_agent_state, DEFAULT_MAX_ENCODED_BYTES
body = ''.join(random.Random(20261027).choices(string.ascii_letters + string.digits, k=40000))
call = ToolCall(id='probe_pending', name='send_report', arguments={'body': body})
interrupts = UserInterrupts(AgentState(), confirmation_tools={'send_report'})
pending = interrupts.before_call(call)
history = [assistant_message(AssistantTurn(tool_calls=[call])), pending.to_history()]
saved = encode_agent_state(
    history={'messages': history},
    last_execution_metadata={
        'finish_reason': 'awaiting_user',
        'question': interrupts.question_from_result(pending),
    },
)
print(json.dumps({
    'limit_bytes': DEFAULT_MAX_ENCODED_BYTES,
    'persisted': saved.persisted,
    'encoded_bytes': saved.encoded_bytes,
    'payload_bytes': saved.payload_bytes,
    'error': saved.error,
    'warning': saved.warning,
}))
PY
```

子代理另以真实 runtime、Loop、UserPrompt、backend 和 renderer，仅 fake 模型返回值复现：200000 字符提问得到 `awaiting_user / persisted=True / encoded_bytes=1606901 / storage_error=None`，结构化输出没有 inline history。作为本地集成探针，尚未升级为正式测试。

建议：对最终规范化快照检查容量，不能 fit 时显式拒绝保存；不能截断待执行工具参数后仍允许执行。体积大的业务输入应由外部工具契约提供短引用。inline 输出同样受平台限制，不能承诺它是无损恢复渠道。诊断中区分“编码及容量检查通过”“变量已输出”“平台写回已确认”；最后一种当前没有可观察凭据。

与之相关的代码观察：容量计算时同时保留旧 `history` 和裁剪后的 `recent_history`，直到编码前才同步二者，可能导致过度裁剪；应在同一容量边界修复中验证，避免足够容量时仍丢任务。该补充由子代理探针观察，主代理未独立复现。

## 2. 统一失败契约、终态与安全诊断

LibreChat：

- [terminal.ts:44](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/failures/terminal.ts:44) 将宿主持有的取消与 provider failure 分开。
- [terminal.ts:61](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/failures/terminal.ts:61) 统一安全错误元数据和 trace 关联；同一 observer 被实际入口使用。
- [lifecycle.ts:116](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/remote/lifecycle.ts:116) 集中结算，terminal 状态未确认时不会报告 provider drain。其 JobStore/CAS 实现依赖服务端持久化，不能直接复制到插件。

CC Agent 的真实缺口：

- [runtime.py:413](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/runtime.py:413) 未处理异常只记录异常并写 renderer error。
- [base.py:64](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/strategies/base.py:64) 外层也只输出 log；当前 Python 源码中找不到 `agent_failed`，与 AGENTS 的既有要求不符。
- 子代理注入安全的 `RunEnvironment.load_state` 故障：AG-UI 输出 `RUN_STARTED/RUN_ERROR`，Dify 原生输出 log/log/text，均无 `agent_failed` JSON。未修改任何源码。
- [mcp_tools.py:129](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/mcp_tools.py:129) 所有 MCP 调用异常变成相同 observation，类型与阶段丢失。
- [loop.py:634](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/loop.py:634) 与 runtime 的部分路径仍输出任意异常文本。已确认文本通路存在，未证明实际发生过凭证泄露；现有 MCP 脱敏应保留。

建议：先建立小而明确的内部失败契约，包含稳定 code、stage、run_id、tool_call_id（适用时）、安全 message、结果是否已知。由两个 renderer 与 strategy fallback 映射到各自协议，补齐 agent_failed。保留已有时延/token 统计，在其上补关联，而非另建 tracing 平台。工具失败仍必须生成与 tool_call 配对的 observation。

取消、等待用户、运行失败和业务结果未知需要可区分；这是运行语义，不要求新增一种界面协议。

## 3. 工具副作用：恢复连接不等于可以重放调用

LibreChat [MCPManager.ts:1955](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/mcp/MCPManager.ts:1955) 的 bearer 恢复路径只恢复连接，随后抛明确错误，不再次调用 `requestTool`；[errors.ts:351](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/mcp/errors.ts:351) 说明不能据错误断定远端没有执行。

CC Agent 已有 ModelRequests 的一次上下文溢出恢复，应继续将它与工具调用重试分开。不能把所有异常统一加 retry：导出或业务写入可能已在远端完成，只是响应丢失。当前 MCP 把异常压成通用失败信息，也不足以指导模型避免重复发起。

建议：区分初始化失败、确定未执行、远端显式拒绝、执行结果未知；未知时先查 job/receipt，外部工具支持幂等键时才按其协议重试。不能把 `tool_call_id` 或 MCP request id 自动视作服务端业务幂等键，也不能把服务端声明的工具 hints 当授权事实。

## 4. 并发边界对照（用户已撤回排队需求）

LibreChat start 会在执行前原子认领请求：[request.js:1137](/home/ygao/Desktop/work/librechat/LibreChat/api/server/controllers/agents/request.js:1137)；resume 以 generation/action 做单次认领：[resume.js:1542](/home/ygao/Desktop/work/librechat/LibreChat/api/server/controllers/agents/resume.js:1542)。队列与准入依赖其服务端 generation/queue store，而非浏览器中的 running 状态。

CC Agent [state_backend.py:76](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/state_backend.py:76) 的 `expected_revision` 只是本地编码的上一版数字，并没有与最新持久状态进行原子比较；两个请求拿到相同旧快照均可执行。前端 history ticket 的 stale-result 保护解决的是展示状态，不能阻止远端副作用。

用户最新决定维持前端回复未完成前不接受新普通消息，不新增队列。上述对照保留为边界事实，不进入本轮实施范围；前端禁发也不应被解释为插件已有跨页面或跨 API 调用的原子锁。本轮不扩大到跨入口准入平台。

## 5. 批准应绑定实际工具对象

LibreChat [execution.ts:83](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/execution.ts:83) 构造目标指纹，并在恢复执行前重新比较目标和能力。其 code workspace 模型不适用于本项目，但“批准对象未变”这一条件可借鉴。

CC Agent [interrupts.py:188](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/interrupts.py:188) 保存的 pending execution 主要是 name/arguments；恢复会重新经过 scheduler，已经能防止会话授权绕过政策。尚需考虑同名工具的服务目标、schema 或应用授权身份在两轮之间变化时，旧确认是否仍有效。

建议：待需要时增加无凭证的工具身份/契约版本信息；先定义什么变化需要重新确认，再决定摘要字段。不把 token/header 原文写状态，正常凭证轮换也不应自动等同于业务身份变化。这个候选尚无生产故障复现。

## 6. 停止与资源清理的保证必须准确

LibreChat [mcp/request.ts:60](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/mcp/request.ts:60) 持有 run 级 abort 与清理；终止新工作并处理迟到连接。

CC Agent 已在 [runtime.py:417](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/runtime.py:417) 的 finally 关闭当前运行 MCP。前端 [DifyAgUiAgent.ts:445](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/DifyAgUiAgent.ts:445) 发起 stop 后吞掉错误，并 abort 本地流；[difyTransport.ts:342](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/difyTransport.ts:342) 未检查 stop HTTP 响应。

这意味着当前路径无法确认后端已经停止，不等于证明 Dify 的 stop 无效。Dify SDK 是否暴露 stop/disconnect 信号，以及能否中断阻塞的模型或工具调用，本轮尚未验证。可先明确停止请求/停止确认/远端结果未知，并验证 deadline 与阶段检查的实际接入能力；不能把 generator.close 的 finally 清理等同于撤回已发生的业务操作。

补充执行可见性：当前 [tool_scheduler.py:38](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/tool_scheduler.py:38) 完成整批串行调用后才返回，Loop 随后才展示结果。可在保持串行策略的前提下逐项交付完成事件，并在工具之间检查取消和总时限。逐项发事件能够缩短进度展示延迟，但不等于已把逐项结果持久化到 Dify，也不能单独修复外部操作成功、最终状态尚未写回的故障窗口。

## 7. 当前导出能力的证据范围

- [CT MCP metadata:131](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/tests/fixtures/ct_mcp_tool_metadata.json:131) 包含三个 export/job 工具名称；夹具只有元数据，不能证明真实导出协议或线上已启用。
- [mcp_tools.py:68](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/mcp_tools.py:68) 注册普通模型工具；[mcp_tools.py:106](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/mcp_tools.py:106) 消费结构化结果和媒体。
- [base.py:106](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/strategies/base.py:106) 将直连 MCP bytes 转 Dify blob；Dify 注入工具继续原产物路径，不新增转发。
- 前端 [difyBlob.ts:70](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/difyBlob.ts:70) 支持组装 blob 附件和下载数据。

架构上可导出，实际取决于应用接入的工具、业务授权与可访问下载资源。未进行线上验证；不新增内部通用 Python/文件执行能力。

## 候选实施顺序（待用户确认完整设计）

1. 依已确认的“全量简洁工具 + 技能提供调用知识”方向，收敛技能入口、完整指令与恢复行为。
2. 将状态容量与 agent_failed 两项已复现缺口列为可靠性基础修复，不依赖具体 MCP 工具改造。
3. 内核保留未知结果/重试与授权检查边界；具体 MCP 工具和参数重构依用户指示留待后续。
4. 新增压缩、工具结果截断和 agent loop 的调查见 [runtime-budget-review.md](runtime-budget-review.md)；排队按最新决定不实施。

不建议为了这轮目标引入 Mongo checkpoint、Redis generation manager、后台调度、subagent 平台或替换 Vue/AG-UI。它们需要独立产品需求和运行所有权取舍，当前已确认目标不支持为其付出这些成本。
