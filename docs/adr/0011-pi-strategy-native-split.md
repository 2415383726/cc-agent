# 拆分 pi_strategy：Pi 内核的 Dify 原生输出插件

cc_agent 曾以单插件双策略承载两种[输出策略](../../CONTEXT.md)：原生（`CC Agent (Dify)`，发 Dify 原生消息）与协议适配（`CC Agent (AG-UI)`）；协议适配已由 pi_dify（[ADR-0008](0008-pi-agent-v2-implementation.md)、[ADR-0009](0009-keep-dify-host.md)）接管。2026-11-16 用户决定为原生输出同样建立独立项目 `pi_strategy`：以复制 pi_dify 为底修改，而不是合并进 pi_dify、也不是从 cc_agent 搬迁自制 loop 代码；两个 Pi 插件之间彻底不共享代码库，接受重复作为独立演进的代价（将来漂移严重再议抽公共包，届时另立 ADR）。

pi_strategy 保留 pi_dify 的全部硬边界（唯一 Dify 模型边界 `stream.py`、唯一跨轮权威 `state.py`、唯一 harness 0.6.0 适配子类 `harness.py`、一次性 overflow 压缩重试、离线打包链），仅把 `piagent.display.v1` 契约层替换为 Dify 原生消息渲染：UX 对齐 `CC Agent (Dify)` 的既定语义（reasoning 包 `<think>` 标签、工具结果渲染 HTML 工具卡、活动/日志/变量/JSON 分发），Dify 自带界面是唯一消费端，不建新前端，pi_chat 继续只服务 pi_dify。"原生"的定义就是对齐 cc_agent 原生模式——两个引擎在同一个 Dify 应用里可互换而不被用户察觉。

配套决策：状态采用新前缀 `pistrategy-state:v1:gzip-base64:` 并拒绝 `piagent-state`/`ccagent-state`——同构不等于同义，工具面一旦分叉，跨插件续跑会从功能变成坑；旧 cc_agent 原生会话不做迁移（自制 loop 的 history 结构与 Pi entries 不可转换）。交互删除 `interaction` 结构化参数，pending 审批以文本呈现、恢复入口改为下一条 query 文本（对齐 cc_agent 原生的 `permission_decision` 关键词表），pi_dify 的 pending 校验、consumed 防重放、过期与指纹机制全部保留，只换恢复入口（**该审批方案已被下方 2026-11-18 修订整体取代**）。2026-11-18 追加决策：不做 `ask_user` 问卷工具，pending 交互只剩审批；也不带 `visualize` 卡片工具（pi_dify 有），内部工具只保留 `activate_skill`/`read_skill_resource`。首版也不带 Tasks。cc_agent 自此冻结归档：停止开发，保留作参考，两个新项目跑稳后可删。

2026-11-18 再次修订（用户决定）：**pi_strategy 取消审批，工具直接执行**。理由：内置 Dify UI 没有交互卡片，文本审批只能靠关键词回复，误判/漏判成本高于收益；审批的防重放、过期、指纹与 session grant 机制随之整体移除（`interaction.py` 删除，state 不再保存 pending/grants/consumed，config 不再接受 approval 键）。工具仍受预算、重复调用与停止信号约束，未知执行结果仍要求先核验再重试。同轮评审另新增 `session_io.py`：Dify SDK 的同步 stdio 调用改由真实 OS 线程承载，阻塞调用可被停止信号放弃并按 unknown 结果收口，避免整轮挂死。
