# 工具目录与功能裁剪

Status: ready-for-human
Blocked by: 无

合并唯一工具目录，删除记忆与演示命令及其专属状态/提示/展示。

已实施。内部 Memory 工具和状态、两个演示命令已删除；Tasks 可调用，旧状态再次编码移除 memory。Dify 重复两半/JSON 语义去重保持原实现，并经运行级回归。

验证：后端全量 213 项、前端全量 181 项通过；TypeScript 与 7 个核心模块的增量 mypy 通过。构建和审查记录见 ../validation.md。
