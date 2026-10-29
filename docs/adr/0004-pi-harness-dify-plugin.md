# 基于 Pi 架构与开源 Harness 新建 Dify 插件

用户选择在 `pi-agent/` 新建 Dify Agent Strategy 插件，以专业开源社区的设计、实现和测试基础改善自行拼装的 Harness；现有 `cc_agent/` 提供 Dify 适配代码与行为验收基线，跨轮状态继续由 Dify `agent_state` 承载。用户明确不把摆脱长期维护或持续跟随官方 Pi 版本作为主要目标，重点是当前能力在受限 Dify 环境中稳定高效运行。

运行内核已在 [ADR-0005](0005-python-pi-harness.md) 确认为社区 Python core/harness；快照和暂停恢复契约继续设计及验证。本决策不宣称现成 Pi–Dify 连接器存在，也不替代 ADR-0001/0002 的状态和外部工具约束。

使用者只能安装一个 `.difypkg`，所有运行时和依赖必须随包提供并支持完全离线安装/运行；生产 arm64、测试 amd64。首版覆盖现有全部当前功能，新插件从新会话开始。纯 Python 内核直接适配 Dify，官方 Pi 保留为参考。交付约束不允许把额外预装 Node 或部署服务作为使用前提。

2026-10-29 补充：[ADR-0007](0007-agent-workbench-scope.md) 按用户最新指示修订“首版覆盖全部旧功能”：前端和协议可替换，Tasks 等旧能力可取舍；Dify 插件、内核选型、状态及离线交付约束保留。
