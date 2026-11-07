# pi_chat：工作台前端重建规格

标签：`ready-for-agent`
决策依据：[ADR-0010](../../docs/adr/0010-rebuild-workbench-as-pi-chat.md)（重建为 pi_chat，展示层取材 DeepSeek Harness；展示栈固定 Vue 3）

## Problem Statement

现有 pi_workbench 前端不好看、不像一个现代聊天产品：没有侧栏（历史是一个下拉框）、消息区卡片风格简陋、思考/技能/工具调用的展示缺乏层次，AskUser 问卷卡交互粗糙。用户喜欢 DeepSeek Harness 的聊天 UI——左侧会话历史列表、思考/加载技能/运行命令的可折叠渲染、工具调用卡、编号选项问卷卡——并希望以它为蓝本重建前端。

## Solution

新建 `pi_chat/`（Vue 3 + Vite + TypeScript），从 MIT 许可的 DeepSeek Harness 源码做减法移植**展示层**（设计令牌 CSS、CSS Modules、DOM/类名结构、交互语义），**数据层**从 pi_workbench 原样平移（`piagent.display.v1` 契约解析、投影归并、Dify 控制规则、静态回放）。旧 pi_workbench 在 pi_chat 通过测试与证据对齐后整体删除，不做长期双轨。

## User Stories

1. 作为聊天用户，我要左侧会话历史列表（新会话按钮、当前会话高亮、相对时间戳），以便快速切换对话。
2. 作为聊天用户，我要删除和重命名会话，以便整理历史。
3. 作为聊天用户，我要侧栏只保留新会话与历史列表（无品牌区、插件、自动化任务、工作区、搜索），以便界面干净专注。
4. 作为聊天用户，我要助手消息以 DeepSeek 风格渲染全量 markdown（表格、代码块、列表），以便舒适阅读。
5. 作为聊天用户，我要我发出的消息显示为右侧气泡并带时间与复制按钮，以便核对与复用。
6. 作为聊天用户，我要「思考」呈现为可折叠的灰阶行，以便默认收起、需要时展开查看推理。
7. 作为聊天用户，我要「加载技能」行显示技能名与图标，以便知道 agent 启用了什么技能。
8. 作为聊天用户，我要工具调用折叠卡（运行中状态、参数与结果可展开），以便审查 agent 的实际动作而不被打断。
9. 作为聊天用户，我要流式输出与打字指示，以便知道 agent 正在工作。
10. 作为聊天用户，我要「已完成，用时 X 秒」状态行与终态徽标（含失败/停止/预算等状态），以便一眼看清运行结局。
11. 作为聊天用户，我要 AskUser 问卷卡：编号选项、选项描述、推荐徽章、单选/多选/自定义输入、分页（如 1/2）、跳过，以便高效作答。
12. 作为聊天用户，我要问卷必填校验、min/max 选择约束与作答后只读回显，以便按要求作答并留有记录。
13. 作为聊天用户，我要工具授权审批卡（参数可见、once/session 范围选择、批准/拒绝、拒绝后的非执行态），以便安全放行工具执行。
14. 作为聊天用户，我要回到历史会话时自动恢复未答问卷与待审批，以便继续处理被中断的交互。
15. 作为聊天用户，我要停止按钮且断流时得到「未确认停止」的明确提示而非静默失败，以便信任界面显示的结果。
16. 作为聊天用户，我要附件上传与安全的附件元数据展示，以便发送文件（不暴露文件内容访问）。
17. 作为聊天用户，我要全中文界面文案，以便与使用习惯一致。
18. 作为开发者，我要数据层（契约解析、投影、控制规则）原样平移并被测试护栏覆盖，以便重建不引入行为回归。
19. 作为开发者，我要投影记录对齐 Harness 的纯数据形状，以便组件移植有稳定契约。
20. 作为开发者，我要回放模式用同一契约、投影与组件渲染三个场景（流程/问卷/审批），以便离线验证 UI 并服务证据截图。
21. 作为开发者，我要 `check:static` 保证构建物无公网资产，以便维持静态前端分离约束（ADR-0008）。
22. 作为维护者，我要 MIT 版权声明与 Montserrat 字体 OFL 许可随 vendor 资产保留，以便合规。
23. 作为维护者，我要 pi_workbench 在对齐验收后删除并同步改写 AGENTS.md 边界条款，以便仓库不做长期双轨。

## Implementation Decisions

- **项目与栈**：新目录 `pi_chat/`，Vue 3 + Vite + TypeScript + vitest + happy-dom；展示栈固定 Vue 3 是用户约束（ADR-0010），不接受 React 分叉。
- **Vendor 边界（做减法）**：逐字复用 Harness 的 ui-theme 令牌 CSS（随附 Montserrat OFL 文件）与各组件 CSS Modules（类名零改动）；逐字拷入框架无关 pure TS（投影记录类型、问卷草稿/倒计时状态机、参数部分解析等，去掉其 waterfall 传输，通道换成 Dify controller）；React 组件源码只作 DOM/类名/交互蓝图，全部重写为 Vue SFC。
- **取材黑名单**：不引入 React、Cordis 装配层、dsh host/RPC；ui-conversation/ui-workspace 只抄所需片段，不整包；不引入 Lexical/shiki 等重依赖，markdown 仍用 markdown-it（`html:false` 安全策略）+ highlight.js。
- **侧栏**：新会话按钮 + 会话列表（高亮、相对时间）+ 删除/重命名；删除/重命名调用 Dify 原生 conversations API，在 transport 新增端点，**不修改 pi_dify**。
- **卡片体系**：一套卡片覆盖全部待交互——AskUser（single/multi/text、必填、min/max、分页、跳过、倒计时、作答后只读回显）与审批（工具授权语义、scope 选择、拒绝非执行态）；审批阻断优先实现。
- **控制规则不变**（从 pi_workbench 平移）：票号 epoch 丢弃陈旧结果；断流合成 unknown/`stopped_unconfirmed` 终态且绝不重发；停止为 best-effort；历史分页加载；从 `agent_state` 恢复待交互；Dify 原生最终文本按内容合并不重复显示。
- **交互提交协议不变**：问卷作答/跳过/审批决定作为新 Dify 轮次的 `inputs.interaction` JSON 提交。
- **Composer**：附件上传保留（local_file 传输方式）；@ 文件/工作区引用、模型选择器、模式切换不做。
- **界面**：zh-CN 文案；浅色主题（对齐用户截图）。
- **回放与证据**：三场景静态回放走同一投影与组件；`check:static` 机制照搬；证据截图在 `docs/evidence/` 重制。

## Testing Decisions

- 只测外显行为：给定 DisplayEvent 流或用户操作，断言视图输出与对 transport 的调用；不测组件内部实现细节。
- **零新接缝**，沿用四条既有 seam：
  1. 投影 seam：DisplayEvent[] → TranscriptView（先例：projection 测试套件，近乎原样平移）；
  2. Controller seam：假 transport 上的发送/停止/陈旧结果/断流不重发（先例：controller 测试套件）；
  3. 组件 seam：@vue/test-utils + happy-dom 挂载断言问卷校验、审批 scope、折叠交互（先例：components 测试套件）；
  4. 回放 seam：场景回放无需后端渲染完整 UI（先例：app 测试 + check:static）。
- 历史与 saved-state 恢复测试同样平移（嵌套事件提取、去重、外来会话状态拒绝、超大载荷拒绝）。
- 证据验收：重制 replay 三场景与 live ask-user 截图至 `docs/evidence/`。

## Out of Scope

- `pi_dify`、`copilotkit-dify`、`cc_agent` 的任何修改；AG-UI 协议面。
- tok/s 与缓存命中统计、模型选择器、「标准模式」切换、@ 引用、品牌区、插件/自动化任务/工作区管理、侧栏搜索、会话置顶/分组。
- 暗色主题（先做浅色）；移动端适配。
- Harness 中超出 `piagent.display.v1` 的事件类型（终端直播卡、plan-review 计划卡等）。
- Dify 会话 API 之外的会话管理能力（如归档、标签）。

## Further Notes

- spike 产物：clone 与可运行抽取实验在 `/tmp/dsh-spike/`（212 文件零修改 React 构建渲染成功），其接缝清单（约 31 个包 specifier 的 alias/桩方案、类型保真度注意事项）是实现时的直接参考。
- 许可：DeepSeek Harness 整仓 MIT（保留版权声明）；Montserrat 字体 OFL；simple-icons CC0-1.0。
- **pi_workbench 删除门**：四条 seam 测试全绿 + 证据截图重制 + `check:static` 通过 + live 冒烟（流式/问卷/审批/历史切换/重命名删除）全部通过后，删除旧项目并改写 AGENTS.md 的对应边界条款。
