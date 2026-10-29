# Python Pi 0.6.0：持久中断与总预算的真实接入点

核查日期：2026-10-28；基线为已发布 `v0.6.0` / `5f73e07964f14a7409f9d1b7f2b7188b06c1fc64`。只读源码，不安装或执行。本文区分公开能力、宿主责任和可能需要的有限补丁；并未验证 Dify 集成。

## 核心判断

模型/工具包装、快照导入导出、宿主 pending 数据与总预算计数，都有公开接口可以实现。**干净地在整批工具配对完成后停止、且不再调用模型，是当前 AgentHarness 公开面最明确的缺口**。core 已有 `should_stop_after_turn`，harness 没有暴露或传递；不必首先改写 core loop，但应给 harness 增加一条可测试的透传接口。

仅靠 `tool_call` 返回 `block` 或某一个工具返回 `terminate=True`，不能表达完整持久暂停。另一种无补丁绕法是让下一次 stream_fn 拒绝模型请求并产生失败消息，再由宿主识别；其历史和结束语义不是正常暂停，不能假定已经等价。

## 1. 工具 hook 的字段与实际作用

公开注册面是 `harness.on("tool_call", handler)` / `harness.on("tool_result", handler)`；扩展的 `ExtensionAPI.on()` 也注册到同一组 hooks。直接注册 `beforeToolCall` 这个名字不会自动映射为 core 钩子。[harness 注册 L885](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L885)、[扩展注册 L122](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/extensions/api.py#L122)

| 入口 | 消费的返回值 | 中断相关限制 |
| --- | --- | --- |
| `tool_call` | 首个 `block=True` 获胜，最终只留下 `block/reason` | 即使 handler 返回 `terminate`，`check_tool_call` 会丢弃；其 core `BeforeToolCallResult` 本身也只有 block/reason。block 最终是普通错误工具结果 |
| `tool_result` | `content`、`details`、`is_error`/`isError`、`terminate` | **terminate 确实透传**，没有被 harness 丢弃；core 独立合并四个字段。普通 hook 多个 handler 使用最后一个非 None 返回，不是逐字段累积 |
| `tool_execution_end` 等生命周期 hook | handler 可观察事件；返回值在该调用点不作为 stop 控制 | 不等价于公开 stop predicate |

证据：[before 分发与字段裁剪 L924–983](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L924)、[after 映射 L1237–1272](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L1237)、[core 字段 L159–168](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/types.py#L159)、[core 结果合并 L588–627](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py#L588)。

还有一个细节：before block、参数错误、未知工具等 `immediate` 结果不会经过 `_finalize_executed_tool_call`，因此不触发该函数里的 after-tool hook。不能指望在 `tool_result` handler 中给这些结果统一补 `terminate`。[串行分支 L680–700](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py#L680)

## 2. 停止整批及强制串行

- **公开串行面存在。** `AgentTool.execution_mode="sequential"`；扩展的 `ToolDefinition.execution_mode` 也公开，harness 转换工具时保留该字段。core 只要发现本批任何一个工具标 sequential，就整批走串行。`Agent` 和 `AgentLoopConfig` 另有全局 `tool_execution="sequential"`，但 `AgentHarness` 构造器没有这个全局参数。可为宿主注册的每个工具设置属性，不必为串行先改依赖。[工具定义 L40–55](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/extensions/types.py#L40)、[harness 转换 L207–225](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L207)、[批次选择 L430–451](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py#L430)
- **串行不代表遇到 terminate 就停止当前批次。** 串行循环仅在 signal aborted 时 break，`terminate` 在整批结束后才汇总，而且条件是所有已完成结果均为 true。并行模式还会提前准备整批、创建并发 Tasks。因此一个工具变为 pending，不会自动阻止后面的真实副作用。[串行 L659–707](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py#L659)、[汇总 L426](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py#L426)、[并行启动 L759](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py#L759)
- **可落地的宿主 seam**：串行执行每个 tool 前检查同一 pending/budget 状态；一旦需用户输入，保存确定的原始调用参数；后续调用通过 gate/工具 wrapper 只产生可识别的未执行结果，保证 tool-call 配对。然后用新增的 stop predicate 在批次结束停止。未执行结果的状态、获准执行后的替换投影和用户输出仍需明确设计，不能把“blocked”当作“已经失败执行”。
- `should_stop_after_turn` 是 core 的公开配置，但调用发生在**整批执行完成后**，不能单独保护同批工具。harness 既没有公开参数，也没在 `_create_loop_config` 传它。`context` hook 只返回消息列表，发生在模型请求前；不能靠它改变已经执行完的批次。[core predicate L284–311](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py#L284)、[harness 配置构建 L1222–1312](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L1222)

不要在当前被 await 的 hook 里直接 `await harness.abort()` 作为正常暂停实现：`abort()` 设置 signal 后还等待 `wait_for_idle()`，当前 run 又要等 hook 返回才能结束，存在自等待风险。这是源码推导，未动态复现。[abort L1543–1565](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L1543)

## 3. 快照、ContextEdit 与恢复后的工具结果

`SessionStorage` 是公开协议，可自定义后端；`Session` 公开读取 metadata/entries/branch/leaf，追加 message/custom entry/compaction，以及 `move_to()`。`MemorySessionStorage` 公开构造器和 `from_entries(metadata, entries, leaf_id)`，足以实现外部快照导入，再交给 `Session` 和新 harness。**恢复本身不需要改 `_storage` 或其他私有字段。**[协议 L607](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/types.py#L607)、[Session 公开面 L167](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/session/session.py#L167)、[构造器 L44](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/session/memory_storage.py#L44)、[from_entries L135](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/session/memory_storage.py#L135)

`from_entries` 的 `leaf_id=None` 在 entries 非空时会自动选末条所指的 leaf。若快照明确处于 root/null leaf，应使用公开构造器保留该值，不能误用 importer 的默认推断。导入数据的树引用、leaf、压缩引用和配对完整性仍由宿主验证。

未见公开 `ContextEdit` 类型、已有 entry 更新/删除方法或 `replace_tool_result()`。存储是追加模型，同 id 再追加会报 duplicate。`append_custom_entry("pending", data)` 可以保留宿主元数据，但 `build_session_context` 不会把它自动解释成结果替换或上下文编辑。[重复 id L91](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/session/memory_storage.py#L91)、[上下文回放 L100–164](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/session/session.py#L100)

无需因此立即修改 Session：宿主可以在**导入之前**构造新的有效 entries 投影，再用公开构造器恢复；或保留原事件，在公开 `context` hook 里做确定的送模投影。前者属于宿主快照协议，后者不改变 Session 权威记录。若坚持依赖库原生解释追加式 ContextEdit，才需要扩展其 entry 类型和 `build_session_context`，范围比添加一条 stop predicate 更大。不能直接追加同 call id 的第二条 tool result 并假定模型会理解为替换。

## 4. 请求准备与总预算

core 的 `AgentLoopConfig` 公开 `prepare_next_turn`、`should_stop_after_turn`、`before_llm_call`、`after_llm_call`。但 harness 0.6.0：

- 内部自建 `prepare_next_turn`，刷新 Session/context/model；没有宿主 prepare 回调透传。
- 把公开 `context` event 接为 core `transform_context`，其返回仅为 messages，是每次送模投影。
- 没有传 `before_llm_call`、`after_llm_call`、`should_stop_after_turn`，尽管 core 支持。

证据：[core 配置 L239–308](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/types.py#L239)、[harness 内部接线 L1222–1312](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L1222)。

**预算记账可走公开注入面**：普通调用、默认压缩与分支摘要最终都用宿主注入的 `stream_fn`；宿主工具 wrapper 也完全可控。可让它们共享本次运行 budget，统一计算请求数、用量、时间、工具次数和结果大小，不依赖库自带 `max_turns` 作为总预算。该对象跨 overflow 重试仍保持同一实例；跨 Dify 轮次如何续计另属产品策略。[普通流包装 L1171](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L1171)、[压缩调用 L1640](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L1640)

若需在模型请求前持久压缩/替换完整 `AgentContext`，可以给 harness 增加显式 `before_llm_call` 透传。注意 core 注释里的“durably replaces context”只表示本次 core loop 的 context；harness 下一轮的内部 prepare 又从 Session 构建上下文，故持久摘要仍须写入 Session，不能只返回一个替换对象并当成已保存。[core hook L290](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/types.py#L290)、[harness prepare L1274](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L1274)

## 有限依赖补丁的边界建议

**最小版本可先用一个很薄的 Adapter 子类，不必复制 loop 或修改依赖源码**：覆写 `_create_loop_config(get_turn_state, set_turn_state)`，先调用 `super()` 获得现有 `AgentLoopConfig`，只给返回对象补 `should_stop_after_turn`，必要时补 `before_llm_call`。该对象是普通 dataclass，这两个字段已存在且 core 已消费；保留 super 构建的 `prepare_next_turn`、工具 hooks 和持久化顺序。与各工具公开 `execution_mode="sequential"`、`tool_call` gate 配合，后续未执行工具仍由 core 产生配对结果，再在批次末正常停止。[配置 dataclass L238](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/types.py#L238)、[factory 返回 L1292](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py#L1292)

这是一条**私有扩展接缝**，不是上游承诺的公开 API。须固定 0.6.0 及产物 hash，并针对 factory 签名、super返回类型、内部prepare顺序、pending后无模型请求、所有工具结果配对和预算上限建立契约测试。升级时先运行这些测试。若后续上游接受公开 callback 参数，再移除 override；不采用全局 monkeypatch，也不复制整段私有方法。这里只证明源码结构允许这种小范围接入，尚未动态验证。

若首版坚持保留任意工具并行、同时要求遇到一次 pending 立即阻断同批尚未发出的调用，则当前公开串行字段加 stop predicate 不够，需要额外的批次调度设计或 core 补丁。该问题必须在设计里明确；不能把它藏在“桥接 adapter”这个名字下面。现阶段尚未实施或证明以上接入组合通过。
