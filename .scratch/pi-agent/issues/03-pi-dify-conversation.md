# 03: Pi 驱动问答与跨轮续聊

**What to build:** 用户从工作台发起真实 Pi 问答，回答经当前 Dify 模型产生；销毁运行对象后，下一轮仍能继续同一会话。

**Blocked by:** [02 Dify 过程流穿透与工作台实时展示](02-dify-workbench-stream.md)

**Status:** ready-for-agent

**Version:** v2；用户已确认拆分并发布。按必要前置完成情况选择实施前沿；当前尚未实施。

**Parent:** [Agent 工作台规格 v2](../spec.md)

**Spec coverage:** US01、US02、US03、US05、US06、US15、US29、US39、US43、US44；V02、V03、V04、V13、V18。这是本票涉及的行为，不表示本票单独签收整个验收场景；最终平台证据由 17、18 补齐。

## Acceptance criteria

- [ ] 提供独立的新插件身份和一个工作台策略入口，固定 Python Pi core/harness 0.6.0 及已审查版本接入；实际调用 AgentHarness，不复制旧 AgentLoop。
- [ ] 普通模型请求只通过当前 Dify Session，响应接入 02 的显示契约；保留必要节点参数，并有明确应用配置/状态变量映射。
- [ ] 普通文本、实际推理及基础完整工具调用消息转换可用；无推理时显示运行状态，不虚构推理。复杂流参数兼容由 06 扩展。
- [ ] 完成最小有效状态编解码和公开 SessionStorage 导入导出，保留 entries/leaf/引用；使用独立版本前缀并拒绝损坏或未知状态，初步限制大小。
- [ ] 状态先于宿主终态输出，state_summary 对应实际快照，state_ref 不谎报平台已持久化；两轮状态读回可核对 revision/run ID。
- [ ] 重建运行对象后继续第二轮，既不叠加 Dify history，也不依赖本地文件或驻留进程；旧 CC Agent 状态不导入。
- [ ] 真实 SDK 上下文验证同步/asyncio 协调、流式交付和请求身份隔离；不可用任意线程搬运 Session 的纯 mock 证明可行。
- [ ] 固定最小回调适配接缝契约，保留上游配置工厂及顺序，不复制私有循环或全局 monkeypatch；基础异常输出安全 agent_failed，凭证不进入输出/状态。

## Implementation context

- 现有语义事件、能力配置和双输出代码只是未验收骨架，可按 v2 替换；AG-UI、结构化旧答案和两个策略不是交付门槛。
- 本票包含基础配对/有效状态与错误收尾；容量裁剪、完整预算、中断和全面停止分别由 07、10、12—15 扩展，不能据本票宣称首版完成。
- 当前只有少量骨架和依赖导入，前置票是否完成须检查实际验收记录。v2 是唯一范围依据，不恢复旧 AG-UI 双入口、Tasks、六命令或旧前端兼容要求。
- 每票包含自身完整行为及必要验证，优先从策略入口、真实 SDK 消息和浏览器观察；只给易变接入点补有限契约测试，不为每个内部 helper 建测试。

## Verification

从策略入口及工作台执行两轮可控会话，捕获实际模型请求与 SDK 消息，再销毁实例恢复；另用真实 SDK 证明上下文和两个会话不串用。

## References

- [Pi 0.6.0 接入点与停止契约](../python-runtime-ports.md)
- [官方/Python 事件映射与限制](../official-web-events.md)

## Comments

- 2026-10-29：按 /to-tickets 和 v2 规格起草；尚未批准发布或开始实施。

- 2026-10-29：用户明确同意新版拆分；按逐票文件发布为 ready-for-agent。发布不代表功能验收完成。
