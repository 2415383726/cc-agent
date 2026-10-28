# 双轴代码审查

基线：`951526723eb2f32eb90e52bc43e889c7762a5d16`。初次审查提交：`04f9f7b`。两个独立审查代理分别检查 Standards 与 Spec，忽略已由格式工具覆盖的项。

## Standards

No documented-standard breaches found.

The semantic diff preserves the documented runtime boundaries: Dify owns conversation state; the v1 codec and capacity checks remain; both protocol surfaces share runtime orchestration; overflow recovery remains within ModelRequests; tool calls receive paired results, including interrupted batch tails; skill resource path checks and cognitive-only internal tools remain intact; MCP connections retain run isolation; and artifact forwarding preserves the existing boundaries.

No substantive baseline smell findings. The cross-module changes follow the ownership boundaries documented in AGENTS.md and the ADRs. Tooling-enforced issues and documented baseline debt were excluded.

## Spec

初次审查发现两项 P2，均已先补红色回归，再修复：

1. **Fresh tool results are summarized before consumption after Skill injection.** Spec 的“修复尾部工具组切点”要求保护完整尾部组。长 internal Skill user message 可能使切点落到刚返回的工具组之后，导致第二次模型输入丢失全部新工具结果。修复：如果最近的 assistant 仍是工具调用，则把切点限制在该组之前，不能把 Skill 正文当成模型已消费结果的证据。长正文与小历史限额下的实际 AgentLoop 回归通过。
2. **Final result budgeting discards the caller’s resource-page limit.** Spec 要求“页大小与单条/批次预算协调”。原始 limit=128 的页面可能被调度器按 8000 重新渲染，最终超出请求限额。修复：TextResourcePage 保留原始响应限额，每次渲染都取它与后续预算的较小值；实际调度器的最终输出长度和游标回归通过。

Scope creep: None found. Deferred stream accumulation, frontend, queue, general file/shell storage, and MCP API redesign remain outside the implementation.

## 自查补充

超大非 pending 尾部消息不能迫使小 Tasks 提前丢失。新增真实 DifyStateBackend 回归后，把尾部历史归入摘要的步骤移到最终丢弃 Tasks 之前；pending 仍完整保留，装不下时显式失败。

初审共计：Standards 0 项；Spec 2 项，最严重为 P2，均已修复。修复后复核与最终验证见下方记录。


## 修复后复核

`6dcea32` 已由两个原审查代理复核：

- Standards：No new documented-standard breaches found. The changes preserve bounded resource paging, tool-call/result pairing, Tasks during state compaction, and exact pending-operation recovery. No substantive baseline smell findings.
- Spec：Both Spec findings are resolved. Earlier tool cycles remain eligible for summarization; requested page limits and cursors remain correct; small Tasks survive oversized nonpending history while oversized pending operations still fail explicitly. 审查代理另行运行 8 项相关公开回归，全部通过，未发现修复引入的回归。

最终：Standards 0 项；Spec 初审 2 项 P2，修复后剩余 0 项。完整后端 236 项通过，17 个核心模块增量类型检查、格式检查和双架构离线构建通过。扩展静态检查的既有债务及线上验收边界见 validation.md。
