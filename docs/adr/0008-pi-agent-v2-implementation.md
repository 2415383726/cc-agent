# Pi Agent v2 的实施边界：独立插件、有限显示契约与持久交互

2026-10-29 开始按 v2 规格实现新的 Pi Agent Dify 插件与静态工作台。新插件位于 `pi_dify/`，复用固定 0.6.0 的 `pi-agent-core-lc` / `pi-agent-harness-lc`；新工作台位于 `pi_workbench/`，从 Leyline 固定提交抽取聊天展示层。旧 `cc_agent/` 与 `copilotkit-dify/` 不改协议、不迁移旧快照，继续独立服务旧会话。

## 决策

- **独立身份与包。** 插件名 `pi_dify`，新策略入口，新状态前缀 `piagent-state:v1:gzip-base64:`。不读取 `ccagent-state`，不共享旧运行时、Tasks 或双输出入口。
- **Dify 是唯一宿主。** 模型、授权工具、附件元数据、技能配置、MCP 配置与 `agent_state` 都来自当前节点；Pi 只负责执行循环、会话投影和压缩。模型请求统一走当前 Dify `session.model.llm`，包括摘要、压缩、重试和溢出恢复。
- **有限显示契约。** 使用 `piagent.display.v1` 的少量事件：消息/推理开始、增量、结束，工具开始/更新/结束，技能、压缩、问题、审批与 `run.state`/`run.done`。事件经 Dify LOG JSON 承载；最终文本仍由 Dify 原生 text 输出，工作台按内容合并，不重复显示。不宣称官方 Pi RPC 或全部事件兼容。
- **两个交互类型。** AskUser 问卷与工具审批使用不同 pending、不同 UI 和不同校验。提问工具返回完整可持久化问卷；同批尾部工具只产生未执行结果，批次末通过最小 harness 子类的 `should_stop_after_turn` 停止，下一次 Dify 请求携带结构化 `interaction`。审批批准后在当前运行重新检查工具、可见性、策略和预算，构造导入前唯一有效工具结果，再以 custom message 恢复；不保持进程 Promise，不自动重放原批次尾部。
- **最小依赖接缝。** `pi_agent/harness.py` 只补 0.6.0 未透传的 `should_stop_after_turn` 和 resume turn；不复制 core loop、不全局 monkeypatch、不改依赖源码。接缝由契约测试和审批/预算流程覆盖。
- **预算与恢复。** 一个 `RunLedger` 统计本轮所有实际模型请求和工具执行；摘要、重试、压缩与恢复共用。普通、续写、最终请求共享一次溢出恢复额度：Pi 压缩后重试一次，再次溢出以 `context_overflow` 结束，不重放已完成工具。固定内容超限直接拒绝，不做无意义摘要。
- **静态前端分离。** `pi_workbench/` 生成无公网资产的静态构建物，不运行 Agent、Node 服务或社区后台。Leyline 只复用展示层；保留 Apache-2.0、固定提交和修改说明。部署位置与 `.difypkg` 分离，插件不自称托管前端。
- **离线包分架构。** `pi_dify/scripts` 生成 amd64/arm64 各自一个包含锁定 wheels、版本清单、许可证与校验和的 `.difypkg`。本地 amd64 已验证断网安装和基本问答；arm64 仅验证 wheels 解析，真实 arm64 执行与 Dify 安装仍需在目标环境验收。

## 后果

所有 18 张 v2 票都有实现代码与本地契约/回放证据，但真实 Dify 1.7.0/1.15.0、真实 provider 流、真实远程 MCP、Dify 停止/历史穿透及 arm64 执行未在本环境验证。不得把本地 fake、静态截图、wheel 解析或源码存在当作平台验收。未约定任何跨崩溃恰好一次、原子并发锁或强制撤销同步 SDK 的承诺。证据与逐票差距见 [v2 实施证据](../evidence/v2-implementation.md)。

相关文档：[v2 规格](../../.scratch/pi-agent/spec.md)、[ADR-0005](0005-python-pi-harness.md)、[ADR-0006](0006-semantic-run-events.md)、[ADR-0007](0007-agent-workbench-scope.md)。
