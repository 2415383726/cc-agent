# 以可观察的 Agent 工作台替代固定 AG-UI 前端兼容要求

用户在 2026-10-29 放宽新 Pi Agent 的首版范围：前端应展示工具、技能及 Agent 工作过程并支持 AskUser，可采用社区交互，不要求旧卡片、AG-UI/CopilotKit 或 Tasks 等全部旧能力。

用户要求按推荐设计发布新规格并表达 Vue 偏好后，补充源码调查选择 Leyline 的 Vue 聊天组件为首选、Pi Web 问卷为参考；替换 Dify 控制层并先验收静态抽取及事件穿透，不引入社区原有常驻 Pi/Node 后台，依据见[当前 v2 规格](../../.scratch/pi-agent/spec.md)与[Vue 调查](../../.scratch/pi-agent/vue-web-options.md)。

本决策修订 ADR-0004 的全量旧功能对齐和 ADR-0006 的固定双入口要求；执行/输出隔离、Dify 持有模型/工具授权及跨轮状态、Python Pi 内核和分架构离线单包继续成立，旧 CC Agent 不在此次裁剪范围内。
