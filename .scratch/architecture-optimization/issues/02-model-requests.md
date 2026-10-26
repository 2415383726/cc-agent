# 模型请求准备与恢复

Status: ready-for-human
Blocked by: 无

将预算、压缩、模型请求恢复收进深 module，保持既有输出与失败语义。

已实施。覆盖普通请求和续写的持续溢出：压缩后仅重试一次，最终为 context_overflow；系统提示与配对历史回归通过。

验证：后端全量 213 项、前端全量 181 项通过；TypeScript 与 7 个核心模块的增量 mypy 通过。构建和审查记录见 ../validation.md。
