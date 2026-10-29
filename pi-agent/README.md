# Pi Agent for Dify

Pi Agent 是以 Pi 架构及开源 Harness 实现为基础新建的 Dify Agent Strategy 插件。目标是在 Dify 的约束下稳定运行模型、技能、工具、压缩与会话恢复，并提供能观察工作过程和回答问题的 Agent 工作台。用户已允许整体替换前端及协议，已按新范围发布工作台规格 v2；已有初步代码骨架及本地依赖导入验证，尚无通过完整验收的可交付插件包。

## 已确定的产品约束

- Python 宿主持有本次 Dify 插件会话，通过官方 SDK 调用应用配置的模型和工具。
- 使用者只安装一个 `.difypkg`，安装及运行完全离线；所有运行时和依赖随包提供，无需额外预装 Node 或部署运行服务。
- 生产环境为 Linux arm64，测试环境为 Linux amd64；按目标架构构建交付物，分别验收。
- 首版重点是 Agent 工作过程展示、工具/技能协作、AskUser 及可靠的 Dify 接入；Tasks 等旧产品能力可按价值省略，不以完整旧功能对齐为门槛。
- 新插件从新会话开始，旧会话继续由原 CC Agent 处理。
- 新前端以 Leyline 的 Vue 3 聊天核心为首选复用基线，替换 Dify 控制层并补 AskUser；不要求 AG-UI/CopilotKit 或旧卡片。输出不渗入执行内核，静态抽取与传输穿透是首道实施验收门。
- 跨轮会话状态仍由 Dify 的 `agent_state` 承载；进程内对象和本地文件不作为另一套持久化来源。
- `cc_agent/` 提供需求、可迁移的 Dify 适配实现和行为验收基线；`pi/` 是只读参考源码。

## 已选执行内核

用户已选择 `pi-agent-core-lc` + `pi-agent-harness-lc`，直接在 Python 中适配 Dify 模型、工具、状态和输出。已调查的 `0.6.0` 作为初始依赖基线，后续锁定完整依赖树并进行实际验收；当前不宣称已验证通过。选型重视开源实现的设计、测试基础与 Dify 适配，不以持续跟随官方 Pi 更新为主要目标。

官方 Pi 源码保留作设计与行为参考。采用的 Python 库在完整请求预算、溢出恢复、跨轮确认及同步 SDK/asyncio 协调上仍需适配与验证。

## 设计入口

- [最新工作台方向与社区复用建议](../.scratch/pi-agent/frontend-direction.md)
- [官方事件核查](../.scratch/pi-agent/official-web-events.md)
- [Vue / Nuxt 客户端与 Leyline 接入研究](../.scratch/pi-agent/vue-web-options.md)
- [社区 Web 客户端比较](../.scratch/pi-agent/community-web-comparison.md)
- [Dify AskUser 路线比较](../.scratch/pi-agent/dify-askuser-options.md)
- [当前工作台规格 v2（ready-for-agent）](../.scratch/pi-agent/spec.md)
- [当前 18 张实施票与依赖](../.scratch/pi-agent/ticket-plan.md)
- [原始访谈与决策历史](../.scratch/pi-agent/interview.md)
- [设计导航与旧实现设计归档](../.scratch/pi-agent/design.md)
- [采用 Pi Harness 新建 Dify 插件的决策](../docs/adr/0004-pi-harness-dify-plugin.md)
- [采用社区 Python Harness 的选型决策](../docs/adr/0005-python-pi-harness.md)
- [项目术语](../CONTEXT.md)

当前 v2 规格及 18 张实施票已发布为 ready-for-agent；v1 规格和旧 17 张票已归档，不能直接按旧 AG-UI/Tasks 门槛实施。现存双输出代码仅为前期未接入骨架，需按第 03 票审查和替换。社区源码调查及工单发布不代表抽取构建、真实 Dify 接入或两架构离线运行已经验证通过。
