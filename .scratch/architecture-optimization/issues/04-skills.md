# 技能生命周期

Status: ready-for-human
Blocked by: 无

集中选择、恢复、激活，删除旧 eager resource reader。

已实施。slash 与模型激活的注入和 active summary 一致；恢复应用当前 denylist/策略；资源路径检查与禁止动态 shell 回归通过。

验证：后端全量 213 项、前端全量 186 项通过；TypeScript 与 8 个核心模块的增量 mypy 通过。构建和审查记录见 ../validation.md。
