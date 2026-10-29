# Pi Agent v2：实施票索引

Status: ready-for-agent

日期：2026-10-29。依据 [Agent 工作台规格 v2](spec.md)（ready-for-agent；SHA-256：6e9a6087afe3619e5d29f571a50d30a63caeccd842f45aef7e99c1d4633a8e07）。用户已确认粒度与依赖，18 张独立实施票已发布为 ready-for-agent；本次不启动功能实施。

旧 [17 票索引](ticket-plan-v1.md)、[v1 工单归档](issues-v1/)及 [v1 规格](spec-v1.md)完整保留。以下编号全部属于 v2，不能与旧 US/A 覆盖混用；旧票不再作为当前实施入口。

## 逐票交付与必要阻塞

1. **[01 Vue 工作台聊天核心抽取与场景回放](issues/01-vue-workbench-extraction.md)**。Blocked by：无。交付：打开独立静态工作台即可查看可展开的消息、思考、工具与技能过程，并通过问卷表单发出答复动作；无需启动社区原后台。

2. **[02 Dify 过程流穿透与工作台实时展示](issues/02-dify-workbench-stream.md)**。Blocked by：01。交付：通过 Dify 应用发起一轮验证请求，工作台实时看到消息、工具和活动，并从历史重建同一结果，证明新事件载体可用。

3. **[03 Pi 驱动问答与跨轮续聊](issues/03-pi-dify-conversation.md)**。Blocked by：02。交付：用户从工作台发起真实 Pi 问答，回答经当前 Dify 模型产生；销毁运行对象后，下一轮仍能继续同一会话。

4. **[04 双架构离线单包与基本问答启动](issues/04-offline-bootstrap.md)**。Blocked by：03。交付：将已可运行的 Pi 问答封装成按 amd64/arm64 区分的完整离线包，在干净目标运行环境安装后完成基本续聊。

5. **[05 Dify 工具调用、通用工具卡与附件闭环](issues/05-dify-tools-artifacts.md)**。Blocked by：03。交付：用户提出需外部工具处理的问题，Pi 调用本轮 Dify 授权工具、消费结果并继续回答，工作台展示一次执行及真实附件。

6. **[06 模型流兼容与工具参数正确执行](issues/06-provider-streaming.md)**。Blocked by：05。交付：不同 Dify 模型输出文本、推理和交错工具参数流时，工作台保持正确内容，真实工具只收到完整且准确的参数。

7. **[07 状态容量、历史与会话恢复](issues/07-state-history-recovery.md)**。Blocked by：05。交付：用户刷新或切换对话后恢复正确历史和运行投影；状态损坏、过大或保存失败时明确失败，旧结果不会覆盖当前会话。

8. **[08 应用技能激活、资源读取与过程展示](issues/08-skills-lifecycle.md)**。Blocked by：07。交付：用户或模型选用当前有效应用技能，按需读取受限资料，工作台展示真实使用轨迹，下一轮按资格继续恢复。

9. **[09 远程 MCP 身份隔离与产物交付](issues/09-remote-mcp.md)**。Blocked by：05。交付：用户通过配置的远程 MCP 普通工具完成查询或生成产物，连接使用当前身份，结果和文件在工作台准确展示。

10. **[10 执行预算、工具防护与用量统计](issues/10-execution-budgets.md)**。Blocked by：05。交付：用户配置调用、时间和 token 限额后，助手在预算内工作，工作台呈现准确次数及用量，失控重复调用受限。

11. **[11 自动压缩与一次上下文溢出恢复](issues/11-context-compaction.md)**。Blocked by：07、10。交付：长会话经 Pi 自动压缩后继续工作，工作台显示真实压缩活动；上下文溢出只恢复一次且不重复执行工具。

12. **[12 AskUser 问卷暂停与跨轮答复](issues/12-ask-user-roundtrip.md)**。Blocked by：07、10。交付：助手提出多题问卷后确定性等待，用户刷新仍可作答，下一轮恢复同一任务；重复、过期或无效答案不会触发继续执行。

13. **[13 工具审批、会话授权与策略重检](issues/13-tool-approval.md)**。Blocked by：12。交付：工具需要授权时展示独立审批，用户刷新后可批准或拒绝原操作；批准仍遵守当前策略和预算。

14. **[14 远程审批恢复与未知结果核实](issues/14-mcp-resume-unknown.md)**。Blocked by：09、13。交付：需审批的远程工具在下一轮使用当前身份恢复，产物只交付一次；写操作结果未知时明确要求核实，不盲目重放。

15. **[15 停止、断流与安全失败收尾](issues/15-stop-failure-security.md)**。Blocked by：06、14。交付：用户停止、网络断开或模型/工具失败时，工作台准确区分已结束、等待与未确认，资源释放且不泄露秘密。

16. **[16 Dify 兼容配置与静态工作台交付](issues/16-dify-compatibility-static-release.md)**。Blocked by：04、08、11、15。交付：部署者可按明确配置在声明支持的 Dify 版本中使用静态工作台和新插件，完整功能输入/输出映射可复现，旧应用继续可用。

17. **[17 amd64 完整离线与业务效率验收](issues/17-amd64-release-acceptance.md)**。Blocked by：16。交付：测试环境安装最终 amd64 单包与静态工作台，完成全部核心业务和恢复场景，形成可审阅的运行与效率证据。

18. **[18 arm64 生产目标离线与业务验收](issues/18-arm64-release-acceptance.md)**。Blocked by：16。交付：在生产目标或等价 arm64 环境独立安装最终单包并完成核心业务及恢复，取得该架构可交付的真实证据。

## 依赖的理由

- 01 先抽出可静态运行的聊天核心和问卷动作，02 才能在实际页面中证明 Dify 过程事件/历史穿透；03 复用已验证的控制层和显示契约，接入真实 Pi 模型与跨轮状态。前三票分别有可运行或可回放的完整结果，不另开纯组件层/编码层工单。
- 03 之后，04 尽早验证单包依赖与目标架构启动，05 验证真实工具/产物；两者互不阻塞。04 必须在最终交付前完成，不等全部功能完成再暴露离线风险。
- 05 之后，06 复杂模型流、07 状态/历史、09 远程 MCP、10 预算各有独立验收。08 只依赖可靠状态 07，不人为等待 AskUser 或压缩。
- 11 压缩依赖 07 的有效快照和 10 的共享预算；12 问卷依赖相同的可靠状态与停止/预算规则，两者互不阻塞，12 不依赖技能。
- 13 在 12 的 gate/等待/答复路径上实现独立工具审批；14 组合 09 的当前远程身份/产物和 13 的审批恢复，核实 unknown 副作用。
- 15 组合 06 的复杂流及 14 的远程/恢复/未知结果，验收停止和失败跨路径行为；前序票已经包含自己的异常清理，不能把基本正确性留到 15。
- 16 的直接前置只有 04、08、11、15；它们的传递依赖覆盖 01—15 的全部功能。交付实际 Dify 版本/配置和静态资产集成，不把每个祖先重复列为直接阻塞。
- 17 和 18 都只依赖 16，分别取得 amd64 和 arm64 的最终离线业务证据，互不阻塞；环境缺失不能用另一架构代签。

## 用户故事覆盖

45 条故事全部来自 v2；以下为主要功能票及必要交付票，不把最后两张验收票写成替代实现的“全覆盖”。

| 故事 | 主题 | 涉及票 |
| --- | --- | --- |
| US01 | 社区 Harness | [03](issues/03-pi-dify-conversation.md) |
| US02 | 新旧插件并存 | [03](issues/03-pi-dify-conversation.md)、[16](issues/16-dify-compatibility-static-release.md) |
| US03 | 当前 Dify 模型 | [03](issues/03-pi-dify-conversation.md) |
| US04 | 摘要/压缩/重试归 Dify | [11](issues/11-context-compaction.md) |
| US05 | Vue 工作过程 | [01](issues/01-vue-workbench-extraction.md)、[02](issues/02-dify-workbench-stream.md)、[03](issues/03-pi-dify-conversation.md) |
| US06 | 最终回答合并 | [02](issues/02-dify-workbench-stream.md)、[03](issues/03-pi-dify-conversation.md)、[06](issues/06-provider-streaming.md) |
| US07 | 真实思考 | [01](issues/01-vue-workbench-extraction.md)、[06](issues/06-provider-streaming.md) |
| US08 | 工具过程 | [05](issues/05-dify-tools-artifacts.md)、[06](issues/06-provider-streaming.md) |
| US09 | 通用工具展示 | [01](issues/01-vue-workbench-extraction.md)、[05](issues/05-dify-tools-artifacts.md) |
| US10 | 真实技能活动 | [08](issues/08-skills-lifecycle.md) |
| US11 | 活动与答案层次 | [01](issues/01-vue-workbench-extraction.md)、[08](issues/08-skills-lifecycle.md)、[11](issues/11-context-compaction.md) |
| US12 | 展开/折叠 | [01](issues/01-vue-workbench-extraction.md)、[05](issues/05-dify-tools-artifacts.md) |
| US13 | 附件/产物 | [05](issues/05-dify-tools-artifacts.md)、[09](issues/09-remote-mcp.md)、[16](issues/16-dify-compatibility-static-release.md) |
| US14 | 执行/产物去重 | [05](issues/05-dify-tools-artifacts.md)、[09](issues/09-remote-mcp.md) |
| US15 | 当前身份 | [03](issues/03-pi-dify-conversation.md)、[05](issues/05-dify-tools-artifacts.md)、[09](issues/09-remote-mcp.md) |
| US16 | MCP 生命周期 | [09](issues/09-remote-mcp.md)、[14](issues/14-mcp-resume-unknown.md)、[15](issues/15-stop-failure-security.md) |
| US17 | 外部能力边界 | [05](issues/05-dify-tools-artifacts.md)、[08](issues/08-skills-lifecycle.md)、[09](issues/09-remote-mcp.md)、[15](issues/15-stop-failure-security.md) |
| US18 | 配置筛选技能 | [08](issues/08-skills-lifecycle.md) |
| US19 | 用户/模型激活 | [08](issues/08-skills-lifecycle.md) |
| US20 | 资源范围/分页 | [08](issues/08-skills-lifecycle.md) |
| US21 | 技能跨轮资格 | [08](issues/08-skills-lifecycle.md) |
| US22 | 多题型问卷 | [01](issues/01-vue-workbench-extraction.md)、[12](issues/12-ask-user-roundtrip.md) |
| US23 | 确定性等待 | [12](issues/12-ask-user-roundtrip.md) |
| US24 | 刷新待答 | [07](issues/07-state-history-recovery.md)、[12](issues/12-ask-user-roundtrip.md) |
| US25 | 答复续作与历史 | [12](issues/12-ask-user-roundtrip.md) |
| US26 | 错误/重复/过期答复 | [12](issues/12-ask-user-roundtrip.md) |
| US27 | 问卷与审批区分 | [13](issues/13-tool-approval.md) |
| US28 | 批准后策略重检 | [13](issues/13-tool-approval.md)、[14](issues/14-mcp-resume-unknown.md) |
| US29 | 会话恢复 | [03](issues/03-pi-dify-conversation.md)、[07](issues/07-state-history-recovery.md)、[08](issues/08-skills-lifecycle.md)、[12](issues/12-ask-user-roundtrip.md)、[13](issues/13-tool-approval.md) |
| US30 | 状态失败 | [07](issues/07-state-history-recovery.md) |
| US31 | 会话/历史隔离 | [07](issues/07-state-history-recovery.md) |
| US32 | 断流不重发 | [07](issues/07-state-history-recovery.md)、[15](issues/15-stop-failure-security.md) |
| US33 | 执行限额 | [10](issues/10-execution-budgets.md) |
| US34 | 运行统计 | [10](issues/10-execution-budgets.md)、[11](issues/11-context-compaction.md)、[17](issues/17-amd64-release-acceptance.md)、[18](issues/18-arm64-release-acceptance.md) |
| US35 | 自动压缩 | [11](issues/11-context-compaction.md) |
| US36 | 一次溢出恢复 | [11](issues/11-context-compaction.md) |
| US37 | 准确终态 | [02](issues/02-dify-workbench-stream.md)、[07](issues/07-state-history-recovery.md)、[12](issues/12-ask-user-roundtrip.md)、[15](issues/15-stop-failure-security.md) |
| US38 | 未知结果核实 | [14](issues/14-mcp-resume-unknown.md)、[15](issues/15-stop-failure-security.md) |
| US39 | 安全错误 | [03](issues/03-pi-dify-conversation.md)、[15](issues/15-stop-failure-security.md) |
| US40 | amd64 离线 | [04](issues/04-offline-bootstrap.md)、[17](issues/17-amd64-release-acceptance.md) |
| US41 | arm64 验证 | [04](issues/04-offline-bootstrap.md)、[18](issues/18-arm64-release-acceptance.md) |
| US42 | 静态托管 | [01](issues/01-vue-workbench-extraction.md)、[16](issues/16-dify-compatibility-static-release.md) |
| US43 | 来源许可 | [01](issues/01-vue-workbench-extraction.md)、[03](issues/03-pi-dify-conversation.md)、[04](issues/04-offline-bootstrap.md)、[16](issues/16-dify-compatibility-static-release.md) |
| US44 | 主要验收接口 | [02](issues/02-dify-workbench-stream.md)、[03](issues/03-pi-dify-conversation.md)、[16](issues/16-dify-compatibility-static-release.md)、[17](issues/17-amd64-release-acceptance.md)、[18](issues/18-arm64-release-acceptance.md) |
| US45 | 核心范围聚焦 | [01](issues/01-vue-workbench-extraction.md)、[16](issues/16-dify-compatibility-static-release.md) |

## 验收场景覆盖

| 场景 | 主题 | 涉及票 |
| --- | --- | --- |
| V01 | Vue 核心抽取 | [01](issues/01-vue-workbench-extraction.md)、[12](issues/12-ask-user-roundtrip.md) |
| V02 | Pi–Dify 会话 | [03](issues/03-pi-dify-conversation.md) |
| V03 | SDK 异步协调 | [03](issues/03-pi-dify-conversation.md)、[15](issues/15-stop-failure-security.md) |
| V04 | 事件穿透 | [02](issues/02-dify-workbench-stream.md)、[03](issues/03-pi-dify-conversation.md)、[07](issues/07-state-history-recovery.md)、[16](issues/16-dify-compatibility-static-release.md) |
| V05 | 模型流 | [06](issues/06-provider-streaming.md) |
| V06 | Dify 工具/产物 | [05](issues/05-dify-tools-artifacts.md) |
| V07 | MCP | [09](issues/09-remote-mcp.md)、[14](issues/14-mcp-resume-unknown.md)、[15](issues/15-stop-failure-security.md) |
| V08 | 技能 | [08](issues/08-skills-lifecycle.md) |
| V09 | 过程重建 | [01](issues/01-vue-workbench-extraction.md)、[02](issues/02-dify-workbench-stream.md)、[05](issues/05-dify-tools-artifacts.md)、[06](issues/06-provider-streaming.md)、[08](issues/08-skills-lifecycle.md)、[11](issues/11-context-compaction.md) |
| V10 | 问卷暂停 | [12](issues/12-ask-user-roundtrip.md) |
| V11 | 跨轮答复 | [12](issues/12-ask-user-roundtrip.md) |
| V12 | 审批策略 | [13](issues/13-tool-approval.md)、[14](issues/14-mcp-resume-unknown.md) |
| V13 | 状态/历史 | [03](issues/03-pi-dify-conversation.md)、[07](issues/07-state-history-recovery.md)、[08](issues/08-skills-lifecycle.md)、[11](issues/11-context-compaction.md)、[12](issues/12-ask-user-roundtrip.md)、[13](issues/13-tool-approval.md) |
| V14 | 保存失败 | [07](issues/07-state-history-recovery.md)、[15](issues/15-stop-failure-security.md) |
| V15 | 预算统计 | [10](issues/10-execution-budgets.md)、[11](issues/11-context-compaction.md)、[13](issues/13-tool-approval.md)、[14](issues/14-mcp-resume-unknown.md) |
| V16 | 压缩溢出 | [11](issues/11-context-compaction.md) |
| V17 | 停止/unknown | [14](issues/14-mcp-resume-unknown.md)、[15](issues/15-stop-failure-security.md) |
| V18 | 安全边界 | [01](issues/01-vue-workbench-extraction.md)、[03](issues/03-pi-dify-conversation.md)、[05](issues/05-dify-tools-artifacts.md)、[08](issues/08-skills-lifecycle.md)、[09](issues/09-remote-mcp.md)、[15](issues/15-stop-failure-security.md)、[16](issues/16-dify-compatibility-static-release.md) |
| V19 | 版本配置 | [16](issues/16-dify-compatibility-static-release.md) |
| V20 | amd64 离线 | [04](issues/04-offline-bootstrap.md)、[17](issues/17-amd64-release-acceptance.md) |
| V21 | arm64 离线 | [04](issues/04-offline-bootstrap.md)、[18](issues/18-arm64-release-acceptance.md) |
| V22 | 业务效率 | [17](issues/17-amd64-release-acceptance.md)、[18](issues/18-arm64-release-acceptance.md) |

17、18 还负责各自目标环境下 V01—V19 的整体验证；表中 V20/V21 的 04 只覆盖基本离线启动，不能代替最终全功能验收。V22 未预设性能提升阈值，按同条件交付业务完成情况及真实调用/时延记录。

## 实施与发布规则

- 每张票均有明确交付、勾选验收、必要上下文、验证方式及来源。只有前置票的实际验收完成才进入可实施前沿；当前仅 01 无阻塞。此处不安排代理或自动开始实施。
- 需要的局部整理随切片进行：01 抽聊天容器和资源依赖，03 审查/替换旧双输出骨架；没有证据支持另开全仓重构票。
- 02、03 与后续集成使用真正 SDK/Dify 输入映射和可复现证据；fake、源码调查、已有骨架或上游测试不能代签平台成功。
- 04、17、18 需要对应架构环境，02、16—18 需要目标 Dify 和受控模型/工具。缺少环境时明确未验证，不把对外依赖下载或新增常驻后台作为绕法。
- 新旧插件和前端保持独立，不在拆票时增加 Tasks、双协议、旧状态迁移或全部 RPC 兼容。
- 旧 17 票已完整归档并修正历史导航；当前标准 issues 目录只有这 18 张 v2 工单，逐票标为 ready-for-agent。父规格未修改或关闭。
- 拆分确认只核对新版粒度/依赖，未增加产品范围；新旧两版规格保持原样。已发布不等于已实施或已完成验收。

## 拆分确认

用户于 2026-10-29 明确回复“我同意”，确认这份 18 票拆分；并要求先完成发布，再提交推送 Git。此前 v1 的确认不用于代替本次确认。

## Comments

- 2026-10-29：用户要求根据新规格重新 /to-tickets；已起草 18 张逐票审阅稿及全部 US/V 覆盖，尚未发布新票或开始实施。

- 2026-10-29：用户确认后正式发布 18 张 v2 工单；旧 17 张原文迁至 issues-v1 并校验内容未变，父规格保持不变，尚未实施。
