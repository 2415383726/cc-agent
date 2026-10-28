# 压缩、工具结果截断与 Agent Loop 调查

> 以下保留调查阶段的证据与当时状态；2026-10-28 后续实施已完成，最终行为、验证及审查见 spec.md、validation.md、review.md。

2026-10-27；沿用 CC Agent 基线 `951526723eb2f32eb90e52bc43e889c7762a5d16`。本轮只修改调查文档，使用内存 fake 做故障探针，没有连接生产模型、Dify 或业务 MCP。

用户确认：工具全量暴露、描述简洁、技能提供调用知识；Skill 优先由提示引导。回复未结束时不接受新普通消息，不新增排队。

## 判断

现有模块分工足够继续优化。应先修预算、摘要和工具批次的正确性，再考虑性能调参。已有工具配对清理、单条/批次结果预算、摘要失败 fallback、连续三次失败熔断、一次上下文溢出恢复、续写和最终合成等机制应保留。

## 第一批：五项确定性问题

### 1. 预算计算包含模型实际不接收的大元数据

- [ResultBudget.apply:10](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/result_budget.py:10) 截断 llm_observation，但不会处理 metadata.output。
- [ToolResult.to_history:50](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/messages.py:50) 将 output 等元数据保留进历史。
- [ContextBudget.prepare:63](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/context_budget.py:63) 递归估算整个消息，包括这些元数据。
- 实际 [to_dify_prompt_messages:357](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/model_adapter.py:357) 只发送相应消息的 content、tool calls、name、call id 等字段，不发送 metadata。

主代理 probe：20 万字符工具正文和 20 万字符 structured output，单条预算设为 1000。正文最终为 **992 字符**，metadata.output 仍有 **200000 字符**，history JSON 为 **201364 bytes**。窗口 32000 / 输入预算 22400 下，prepare 报 ContextOverflowError，估算 **73518 tokens**；用同一估算器对实际发送字段的视图估算仅 **2081 tokens**。两个数字均为本项目估算，不是 provider tokenizer 的实测 token。

这同时放大了后续摘要输入和状态编码负担。最小方向是明确模型消息视图、界面展示载荷和恢复所需元数据；预算与真正发给模型的字段保持一致，完整 UI output 不重复进入模型历史。不能粗暴删除待处理中断参数或权限恢复必需字段，也不能把本项目有限状态变成第二套原始结果存储。

### 2. 尾部工具结果较大时，旧历史明明可压缩却被直接拒绝

[find_split_point:194](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/context_budget.py:194) 先根据尾部 token 占比选切点；[_respect_tool_pairs:213](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/context_budget.py:213) 向后越过工具组。越到末尾后返回 0，导致不摘要任何旧历史。

真实 AgentLoop + fake 模型/工具 probe：20 条旧 user 消息（每条 250 字符），当前请求，一次 Search 返回 8000 字符。窗口 **8192**、输入预算 **5734**，首轮工具成功，第二轮请求估算 **6564 tokens**，直接 context_overflow，摘要器 **0 次**。只摘要旧前缀、保留当前请求和完整 assistant/tool 组，真实 prepare 估算为 **4634 tokens**，能够继续。

最小方向：工具组内的切点回退到组开始，保护当前请求及完整尾部组，允许摘要之前的前缀。不能为消除溢出把最近工具结果单独扔掉。现有测试只验证切分后没有孤立 tool，没有覆盖这一可行压缩被跳过的边界。

### 3. 摘要语义混用，用户已经撤销的决定被重新拼回来

[DifyHistorySummarizer](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/compression.py:27) 将 existing_summary 和待压缩消息一起交给模型；但 [_call_summarizer:299](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/context_budget.py:299) 又把旧摘要全文与模型新摘要合并。只要新摘要没有逐字包含旧摘要，就继续保留旧全文。

probe：旧决定为部署 A，摘要器返回当前决定部署 B。连续三轮后仍留 A 和三个版本的 B，而不是一份反映当前决定的摘要。此处验证的是合并逻辑；不依赖模型是否足够准确。

最小方向：约定摘要器成功返回的是一份完整更新后的摘要，替换旧摘要；fallback 遵守同一契约并明确其信息保真边界。摘要提示要求保留当前目标、有效约束、被撤销/替代决定、任务进度、必要工具结论和未决事项，避免堆叠历史版本。保留旧事实的用例，也要验证显式撤销和修改决定的场景。

### 4. 固定上下文已经放不下，仍花三次摘要调用并改写历史

[ModelRequests.prepare:121](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/model_requests.py:121) 最多强制压缩三次，最后才判断 static_context_too_large。

probe：工具 description 30000 字符，窗口 4096 / 输入预算 2867，固定内容估算 **12433 tokens**；仍调用摘要器 **3 次**，依次摘要 21、6、2 条消息，31 条历史最终剩 2 条后才拒绝。

最小方向：先算本次不可缩减内容的预算下限，已经无解就直接拒绝，不破坏历史也不消耗摘要调用。注意 [PromptBuilder:36](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/prompt_builder.py:36) 当前 static_context_tokens 也包含可压缩的旧摘要，不能直接拿该合计字段提前拒绝。工具仍全量暴露；本轮不靠隐藏工具绕过该问题。

### 5. Skill 和其他工具同批执行时，结果配对被插入消息打断

[loop.py:371](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/loop.py:371) 写入第一个 tool result，随后 [386](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/loop.py:386) 立即插入 Skill 的 user 正文，之后才写剩余工具结果。[sanitize_history:64](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/history.py:64) 在 user 边界移除未配对调用及其后来结果。

真实 AgentLoop probe：同批 a=Skill、b=Business 都执行成功，前端也有两个结果；下一次模型请求及最终历史却只保留 a，b 被静默删去。

最小方向：先连续写完这批已执行工具的配对结果，再注入技能正文。不要改变用户选择的提示驱动 Skill 优先，也不新增技能工具门禁。

同一批次另有事件缺口：[loop.py:352](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/loop.py:352) 先发全批 call，scheduler 在首个中断后停止执行；probe 得到 `call a -> call b -> result a`，b 没有 result/end。应给未执行尾部明确的跳过/未执行收尾，或延迟可见 start；保留每个历史调用配对要求，避免界面工具卡永久显示运行中。此问题与发送新消息或排队无关。

## 第二批：明确收益与证据限制的候选

### 长技能参考资料不能分段补读

[SkillRuntime.read_resource:26](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/skill_runtime.py:26) 默认先取前 12000 字符，随后 ResultBudget 默认再截至约 8000 字符；[工具 schema:267](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/internal_tools.py:267) 只有 skill/path，没有 offset/limit。

主代理用真实路径检查、fake read_text 返回约 16000 字符参考资料：6000 字位置的必要规则在第一次读取中存在，经过 ResultBudget 后消失；14000 字位置的规则第一次读取就已丢失。重复同一个调用只能得到相同截断结果。当前 bundled 技能的文本文件没有超过 12000 bytes；这是长参考资料下的已复现能力限制，不能据此断言现有所有技能都受损。

建议仅为技能自身文本资源增加有上限的分段读取与 total/next 标记，仍遵守现有路径边界；普通业务工具结果继续按预算给出明确有损视图，不默认增加一次 LLM 摘要调用，不新增通用本地 I/O 或原始结果存储。

用户随后要求先参考 LibreChat 的实际策略；2026-10-28 已核对宿主及 SDK 的完整分层机制，补充见 [librechat-large-content-strategy.md](librechat-large-content-strategy.md)。Q10 不再仅作为“普通截断/技能分页”的二选一，应同时考虑连续回读、模型投影、新旧结果及摘要源。

### 混合语言 token 估算会受英文前缀影响

[estimate_context_tokens:239](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/context_budget.py:239) 对整段 flatten 文本用前 2000 字符判断中日韩比例，再统一除以 1.0 或 2.8。主代理 probe：5000 个中文字估算 **5004**；在前面加 3000 个英文字母后，反而估算 **2861**。

这是估算算法的不一致，不是实际 tokenizer token 测量。可按消息或文本片段分别估算，保留保守余量并用 provider usage 校准。不要仅调整 0.7 阈值来掩盖计算问题，也不假设所有模型使用同一种 tokenizer。

### 流式参数兼容存在确定边界缺陷，生产触发尚未核实

真实 DifyModelAdapter.invoke_stream + fake SDK chunks：同 id 的三块参数 `{"x":"ha`、`ha`、`"}` 被拼成 x=ha，应为 haha；id 首块存在、续块为空时也可能拆成两个 draft。代码在 [model_adapter.py:55](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/model_adapter.py:55) 和 [_merge_stream_part:546](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/model_adapter.py:546)。累计快照输入的现有兼容测试是通过的，不能直接删去去重逻辑。

本地 dify_plugin-0.7.4 wheel 中，内置 OpenAI-compatible provider 在上游聚合后才发完整 tool_calls，所以这一实际 provider 路径通常不会把上述原生参数碎片传入插件。应先核实用户实际模型 provider 的块格式，再在可信适配层确定累计/增量契约。没有验证生产 provider，也不宣称线上参数都被损坏。

### 首次尝试已经输出文字后的溢出恢复

真实 Loop probe：第一次模型先发 `discarded draft ` 后再抛 overflow，第二次成功答 final，流中可见 `discarded draft final`，最终 answer/history 却是 final。[ModelRequests.stream:70](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/model_requests.py:70) 没有尝试级可见输出回滚或消息替换。

通常上下文溢出在首 delta 前拒绝，此处是已复现的边缘路径，实际发生率未验证。后续明确 attempt 的显示语义，仍保留项目要求的一次压缩重试；不能为了简化显示直接删除该恢复能力。

## 验证

主代理运行现有定向测试 **66 项，通过**：RegistryAndBudgetTests、LoopTests、StreamToolCallAccumulatorTests、BudgetAndPromptEnhancementTests、GuardSchedulerAndToolEnhancementTests。使用 Python 3.12 和本地只读 uv 依赖缓存，没有安装依赖。

另有本报告列出的内存故障探针；没有添加正式测试文件、修复运行代码、运行全量后端/前端回归或连接生产服务。现有测试通过与这些遗漏边界中的失败可同时成立。

建议正式修复先将第一批五项探针转为公开行为回归，验证实际模型输入、工具调用/结果、最终历史和两种输出策略，而非为私有 helper 镜像写测试。默认限制、Dify 语义去重、产物单一路径、技能路径检查和恢复政策维持原有约束。
