# AG-UI、CopilotKit 与自有交互契约调查

日期：2026-10-26（Asia/Shanghai）。本地代码基准：`5aa8543000452613c9f7cc2ff24edbfcaa7b9fb9`。这是事实调查与待决问题，不是已接受的迁移决策；尚未修改运行代码。

当前状态：用户补充现有版本已在生产正常使用，决定暂时保留 AG-UI/CopilotKit，不进行此次迁移；工作重点转为 MCP 接入。下面的迁移方向与后续问题留作备查，不代表已安排实施。

## 初步判断

当前项目实际使用 AG-UI 的流式消息、推理、工具、Activity 和运行生命周期，也使用 CopilotKit 的消息累积、聊天组件、工具渲染及中断接口。“完全没用它的能力”不符合代码。

但是，共享状态、前端执行工具、标准后端输入等互操作能力没有在当前业务路径落地。业务结构化答案、权限语义、状态保存和中断恢复主要由项目自己实现。因此，是否继续使用它，应按现有收益与适配成本判断，不能仅按协议能力覆盖率判断。

“替换 AG-UI 事件格式”“替换 AG-UI 客户端运行时”“替换 CopilotKit 组件”是三个可分别选择的工程动作。当前最具体的界面与状态适配负担，集中在后两者。

## 本地实际链路

```text
AgentLoop / runtime
  -> ProtocolRenderer / AgUiStreamWriter
  -> Dify AgentStrategy log
  -> Dify /chat-messages SSE
  -> extractAgUiEvent
  -> AbstractAgent 的事件处理与消息状态
  -> CopilotKit + 自有 Vue 业务组件
```

- 后端把 AG-UI 事件放入 Dify log：[base.py](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/strategies/base.py:95)。没有标准 `RunAgentInput` HTTP 入口，输入来自 Dify 策略配置。
- 浏览器直接请求 Dify SSE：[difyTransport.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/difyTransport.ts:305)。AG-UI 本身也不限定传输，换协议不要求换为 WebSocket，见[官方架构说明](https://github.com/ag-ui-protocol/ag-ui/blob/main/docs/concepts/architecture.mdx)。
- 主路径解包后直接转发 AG-UI：[DifyAgUiAgent.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/DifyAgUiAgent.ts:476)。非 AG-UI fallback 才走 `normalizeDifyEvent -> createDifyRunEmitter`，不能把 fallback 的重编码误认为主路径每次都执行。
- 历史、会话管理、上传、停止直接调用 Dify API；换内层事件格式不会移除这些 API。

## 能力与归属

| 能力 | 当前归属与证据 |
| --- | --- |
| 流式正文、推理、工具、Activity、结束/错误 | AG-UI writer + AbstractAgent；[agui_stream.py](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/agui_stream.py:53)、[DifyAgUiAgent.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/DifyAgUiAgent.ts:534) |
| 业务卡片、表格、对比、时间线、图表 | 自有 Markdown fenced JSON 与 Vue 渲染；[structuredContent.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/structuredContent.ts:134) |
| 分析过程分组、折叠、耗时 | 自有 [runProcess.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/runProcess.ts:45) |
| 会话状态、技能、记忆、任务、授权 | Dify `agent_state` 与项目 runtime；不是 AG-UI UI state 同步 |
| UserPrompt / 权限恢复 | 自有 runtime 改写工具结果或执行挂起工具；[runtime.py](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/runtime.py:518) |
| 中断前端接口 | 后端 outcome 被桥接为 `CUSTOM/on_interrupt`，再接 CopilotKit `useInterrupt`；[DifyAgUiAgent.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/DifyAgUiAgent.ts:483) |
| A2UI | 有 renderer 注册及 demo/weekly-report 路径，不能说完全没有；主要业务回答仍用自有 fenced JSON |
| 共享状态与前端工具执行 | 未发现当前业务路径使用 `STATE_SNAPSHOT/STATE_DELTA/MESSAGES_SNAPSHOT`，也没有前端工具执行注册；`useRenderTool` 负责展示 |

版本注意：本地 Python `ag-ui-protocol==0.1.18` 的 `RunFinishedEvent` 不建模 `outcome`；项目在 dump 后自行添加该字段，见 [agui_stream.py](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/agui_stream.py:183)。不能用最新规范反推当前锁定 SDK 已完整实现标准中断。

## 已观察到的适配成本

1. Dify conversation 与 CopilotKit thread、provider clone 的同步：[CcDifyAssistant.vue](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/components/shell/CcDifyAssistant.vue:108)、[历史加载](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/components/shell/CcDifyAssistant.vue:301)。自建 UI 仍需处理新 draft 取得服务端 ID、异步切换与运行隔离，但可以自行决定状态归属。
2. 响应式对象转 plain、clone 与配置共享：[DifyAgUiAgent.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/DifyAgUiAgent.ts:39)、[clone](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/DifyAgUiAgent.ts:398)。
3. 滚动依赖 CopilotKit 内部 `data-testid` 和 MutationObserver：[DrawerExperience.vue](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/components/shell/DrawerExperience.vue:388)。
4. 工具 renderer 存在类型兼容与 `as any`：[DrawerExperience.vue](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/components/shell/DrawerExperience.vue:503)。
5. 保留 Dify 原生流 fallback 需要第二条归一化/重编码路径；是否继续支持该入口是独立产品决定。

不要误报：`lib/agentState.ts` 的自有 reducer 仅被测试引用，不是当前生产第二套 reducer。文件长度也不等于可删除代码量，adapter 同时承担 Dify、附件、停止、历史等必要职责。

## 参考项目

DSH 已结合本地既有调查确认为 DeepSeek Harness。`pi-web` 暂按 `xing-shuyin/pi-web-ui` 调查；名称尚未由用户确认，不能与 `badlogic/pi-mono/packages/web-ui` 混同。

| 项目 / 固定快照 | 传输与契约 | 对当前项目的含义 |
| --- | --- | --- |
| DSH `22ddee3792402c3e70ec5f86a63c3e3e895a2f60`，2026-10-23 | typed Remote RPC；普通调用 HTTP POST，流走 mux WebSocket；自有业务声明与生成代码 | 它自管 Web 交互契约；不必照搬其 RPC/插件/连接基础设施 |
| pi-web-ui `08ee62d0263d3407575896da9f6e07b343b84c5e`，2026-10-26 | JSON/WebSocket；自有版本化消息，前后端共用类型 | UI 面向自身契约，引擎差异在 adapter 收敛；自有协议仍需恢复与版本管理 |

DSH 的依据：[connection README](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/client/connection/README.md#L30-L34)、[API Gateway](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/docs/api-gateway.md#L126-L128)。它维护历史初始页、cursor、baseline、sequence 与补洞，见 [Web Client](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/docs/subsystems/web-client.md#L45-L85)。其 SDK stdio JSON-RPC 是另一层，不能与官方 Web 通道混称。

pi-web-ui 的依据：[架构与快照/增量](https://github.com/xing-shuyin/pi-web-ui/blob/08ee62d0263d3407575896da9f6e07b343b84c5e/docs/architecture-core.md#L5-L26)、[协议版本 37](https://github.com/xing-shuyin/pi-web-ui/blob/08ee62d0263d3407575896da9f6e07b343b84c5e/server/protocol-version.ts#L1-L11)、[共享类型](https://github.com/xing-shuyin/pi-web-ui/blob/08ee62d0263d3407575896da9f6e07b343b84c5e/web/src/types.ts#L1-L13)。DSH 引擎通过另一 adapter 接入相同 UI wire protocol，见[引擎文档](https://github.com/xing-shuyin/pi-web-ui/blob/08ee62d0263d3407575896da9f6e07b343b84c5e/docs/dsh-engine.md#L10-L13)。

另一种 pi-web 指代：pi-mono 的 `packages/web-ui` 是组件库；核对的[历史快照 README](https://github.com/badlogic/pi-mono/blob/12805f61bd563b282dc43f0722133a9a84a44f13/packages/web-ui/README.md#L18-L105) 将浏览器中的 Agent 对象传给 ChatPanel，通过内存事件连接。这不等于一个可直接替代 Dify 的远端协议，也不据此断言其当前版本形态。

## “Dify 多一层解包”的边界

传输层上成立：不论 AG-UI 还是自有事件，都可以放在 Dify 外壳里，让 frontend adapter 解包。主路径本来就是这样。

完整产品行为上不充分：历史保存/回放、conversation ID 恢复、工具标识与错误配对、附件/blob、中断后的新一轮调用、状态压缩、结束与断流，仍需明确归属。项目当前用 Dify answer/agent thoughts 修复最终回答历史，见 [difyHistoryMessages.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/copilotkit-dify/src/cc-assistant/lib/difyHistoryMessages.ts:113)；换字段名不能恢复未保存的过程。

## 候选方向（尚未决定）

| 方向 | 能解决什么 | 代价 / 限制 |
| --- | --- | --- |
| 保留现有栈，收缩不需要的兼容路径 | 最少迁移成本 | 继续接受组件与运行时的状态归属 |
| 自有 Vue 状态与展示，先保留 AG-UI 事件 | 可先验证摆脱 clone/thread/DOM 耦合的收益 | 自己承担消息累积、中断和运行状态；事件格式约束还在 |
| 自有 Vue 状态与展示 + 小型版本化事件 | 产品能力与 wire format 可以独立演进 | 前后端契约、兼容和 reducer 均需自管；不是只改解包 |
| 自有事件 + 继续使用 CopilotKit | 可以改后端内部格式 | 仍要转回 AG-UI 才能供当前客户端消费，未必有净收益 |

如果选择自建，沿用 Dify fetch/SSE 即可；可以复用已有 `ProtocolRenderer/AgentEvent` seam、业务 Vue 组件、附件处理和 transport。事件需要明确 run/message/tool/prompt 身份、开始/增量/完成/错误，以及待回答问题；是否需要 seq、重放和 snapshot，应由恢复要求决定，不能为了模仿参考项目预先全加。

不能直接将当前 Web 切到现有 Dify 输出策略：它不提供同样的 UserPrompt 和结构化答案提示，见 [profiles.py](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/profiles.py:20)、[internal_tools.py](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/core/internal_tools.py:451)。若迁移，应先拆开产品交互能力与序列化格式。现有 ADR-0001 明确保留两种输出策略；若改变该承诺，应在最终决定时记录新的取舍。

## 设计树与采访记录

第一轮已由用户明确：

1. 前端专用于 CC Agent + Dify，不以接入其他 AG-UI Agent 为目标。
2. 优先痛点是界面、会话与状态受 CopilotKit 限制。

由此得到的建议（尚未获用户选择）：优先移除 CopilotKit 的组件与客户端运行时依赖，让 Vue 自管展示状态；可以先保留 AG-UI 作为边界事件格式，单独验证这一步的收益，再决定是否改为自有事件。单换后端事件格式并继续保留当前 CopilotKit adapter，不能直接解决已选痛点。

当前 frontier：

3. 迁移边界：先自管 Vue 状态/UI、暂留 AG-UI 事件，还是同时改成自有版本化事件？建议前者，减少同轮改动的边界数量；如果连事件生命周期本身也造成明确限制，再选择后者。
4. 恢复要求：重新打开会话后只需最终回答与附件，还是要求完整工具/过程记录与待回答问题？建议至少恢复最终回答、附件和待回答问题；完整过程回放另按实际使用价值决定。当前代码只重建最终回答/上传附件，不能声称已有完整恢复。

后续依赖分支：确定业务能力保留范围、刷新恢复与运行中断的边界、旧历史与协议兼容、Dify 原生输出策略是否仍保留。现有 ADR 承诺和产品能力默认保留，除非用户选择改变。仍未确定最终迁移方案，不写成 accepted ADR，也不改 glossary 中既有“输出策略”的定义。

本次为静态代码与主源文档调查，未运行前后端或联调 Dify，未据此声称生产恢复能力已经验证。
