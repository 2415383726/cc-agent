# 架构优化审查

基线：`0bbace1`；首轮审查：`b6308da`；修复后复审：`4432655`。采用独立 Standards / Spec 两轴审查，报告保持分开。

## Standards

1. **P2，文档契约：原生开始字段丢失。** `runStream.ts` 在 fallback 元数据先到时合成开始事件，随后丢弃原生 `RUN_STARTED`，导致真实 runId/threadId/扩展字段消失，违反 README 的“保留原生事件字段”。现已延后被动前缀，保留原生事件；若已有实际 fallback 文本，则先结束该段，再开始原生 run，符合 SDK 的顺序运行约束。不同身份与扩展字段、blob 前缀和真实 SDK 运行已覆盖。
2. **P3，判断性代码气味：Duplicated Code。** `_compression_activity` 在 model_requests/loop/runtime 三处构造相同 payload，后续协议变更易遗漏。现已合并到 `compression.compression_activity`，三处调用共享实现。

复审：两项均已解决，未发现剩余问题；审查代理未额外重跑测试。

## Spec

1. **P2，过期历史仍可覆盖当前内容。** 规格要求“集中会话/thread 身份、history ticket、过期结果和 visible clone 等待”。原实现仅在 `selectConversation()` 返回后核验 ticket；此时真实 agent 已提交 messages/state 和回调。A→B→A、先完成新请求再完成旧请求，旧内容仍覆盖新内容；后台旧回调也会提前标记历史已加载。现将 ticket 校验传入公共加载边界，在提交前检查，同时以请求序号及配置身份防止无效结果提交。

复审：使用真实 agent/coordinator 的延迟 HTTP fake 重跑 A→B→A 复现，旧响应不会覆盖新内容，过期结果返回 null。定向 3 个前端测试文件、45 项通过；未发现其他明确规格偏差或范围扩张。

总计：Standards 2 项全部解决；Spec 1 项全部解决。两轴均无剩余发现。
