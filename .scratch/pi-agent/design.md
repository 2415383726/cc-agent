# Pi Agent for Dify：设计导航

当前实施依据为 [Agent 工作台规格 v2](spec.md)，状态 ready-for-agent；本导航不增加范围。v1 的全功能、固定 AG-UI 双入口及沿用旧前端要求已被修订。

当前设计是：Leyline Vue 聊天组件 → Dify 浏览器控制层 → Dify 应用/插件宿主 → Python Pi Harness/Core；Dify 提供当前模型、授权工具及唯一跨轮状态。静态聊天核心补 AskUser，不引入原社区 Node/Pi 后台。

- [前端方向与 Dify 接入依据](frontend-direction.md)
- [Vue / Nuxt 候选与 Leyline 复用边界](vue-web-options.md)
- [Python Pi 接入点与固定版本限制](python-runtime-ports.md)
- [Dify AskUser 的按轮方案](dify-askuser-options.md)
- [旧实现设计归档](design-v1.md)：仅追溯，不按其中旧 AG-UI、Tasks 或改写提问结果等要求实施。
- [当前实施票索引](ticket-plan.md)：18 张 v2 工单已发布为 ready-for-agent。
- [旧票索引](ticket-plan-v1.md)：17 张旧票仅作历史追溯，父规格为 v1。

已有少量代码骨架及依赖导入验证；静态抽取、插件运行链路、真实 Dify 传输与两架构离线交付均未通过完整验收。当前已发布规格和实施票，尚未启动功能实施。
