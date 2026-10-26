# 前端运行流

Status: ready-for-human
Blocked by: 无

统一 native/fallback 生命周期、中断、附件与会话ID，删除影子 reducer。

已实施。native 透传、真实 fallback、Dify fallback 中断恢复、附件和终止行为已覆盖；影子 reducer 和反向转换删除。

验证：后端全量 213 项、前端全量 181 项通过；TypeScript 与 7 个核心模块的增量 mypy 通过。构建和审查记录见 ../validation.md。
