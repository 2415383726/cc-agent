# 授权、中断及状态提交

Status: ready-for-human
Blocked by: 无

修复会话允许重复确认与状态摘要误报，集中中断续接，保留策略限制与附件。

已实施。旧 v1 待处理中断、持久会话授权、批准后策略拒绝及 MCP 文件恢复输出已覆盖；极限压缩的 state_summary 与实际保存快照一致。

验证：后端全量 213 项、前端全量 186 项通过；TypeScript 与 8 个核心模块的增量 mypy 通过。构建和审查记录见 ../validation.md。
