# 02: Dify 过程流穿透与工作台实时展示

**What to build:** 通过 Dify 应用发起一轮验证请求，工作台实时看到消息、工具和活动，并从历史重建同一结果，证明新事件载体可用。

**Blocked by:** [01 Vue 工作台聊天核心抽取与场景回放](01-vue-workbench-extraction.md)

**Status:** ready-for-agent

**Version:** v2；用户已确认拆分并发布。按必要前置完成情况选择实施前沿；当前尚未实施。

**Parent:** [Agent 工作台规格 v2](../spec.md)

**Spec coverage:** US05、US06、US37、US44；V04、V09。这是本票涉及的行为，不表示本票单独签收整个验收场景；最终平台证据由 17、18 补齐。

## Acceptance criteria

- [ ] 以最小验证入口从真实插件 SDK 发出受控过程事件、最终文本与状态/终态，实际经过目标 Dify 应用 SSE 到 Vue 工作台；验证入口不成为第二套产品执行内核。
- [ ] 固定有限显示契约的 schema 版本、run ID、顺序、消息/内容块/tool-call ID 和宿主终态语义；只投影允许字段，不直接转储 provider/headers/完整状态。
- [ ] Dify 控制层接管请求、新对话定位、流解包与基础历史，明确应用/节点字段映射；不得假定任意 inputs 自动到达 AgentStrategy。
- [ ] 确认实际 Agent 日志外壳以及 SDK LOG 的 JSON data 穿透，记录目标版本、配置、脱敏输入/输出样本和可复现步骤。
- [ ] 增量与最终消息覆盖、工具 end/result 合并、重复事件和 Dify 最终文本合并均正确；未知工具/坏事件/未知版本有安全处理。
- [ ] 限制中间更新、事件数量/大小和日志体积；选定日志 ID/更新方式后，用真实历史读回证明可重建，不逐 token 保存全量快照。
- [ ] 验证状态交付先于可信宿主终态；仅 Pi message end 或流连接关闭不能变为已保存/正常完成，断流不自动重新 POST。
- [ ] 提供 SDK→应用 SSE→浏览器完整验证及可离线重放的脱敏样本；真实平台未通过时明确未完成，不能以 fake 代签。

## Implementation context

- 本票先以可控事件证明 Dify 载体与 Vue 控制层，03 再接入实际 Harness；无需等待工具、技能或完整离线包。
- Dify 原生最终文本仍服务平台回答/历史；不引入 AG-UI、RPC 兼容层或新的流网关。后续票复用本票显示契约。
- 当前只有少量骨架和依赖导入，前置票是否完成须检查实际验收记录。v2 是唯一范围依据，不恢复旧 AG-UI 双入口、Tasks、六命令或旧前端兼容要求。
- 每票包含自身完整行为及必要验证，优先从策略入口、真实 SDK 消息和浏览器观察；只给易变接入点补有限契约测试，不为每个内部 helper 建测试。

## Verification

发送一次受控应用请求并刷新历史，比对 SDK、SSE、页面与历史投影；回放重复/坏事件和断流，确保不产生第二次请求。

## References

- [官方/Python 事件映射与限制](../official-web-events.md)
- [工作台方向与 Dify 接入](../frontend-direction.md)
- [Dify 问卷与按轮交互选择](../dify-askuser-options.md)

## Comments

- 2026-10-29：按 /to-tickets 和 v2 规格起草；尚未批准发布或开始实施。

- 2026-10-29：用户明确同意新版拆分；按逐票文件发布为 ready-for-agent。发布不代表功能验收完成。
