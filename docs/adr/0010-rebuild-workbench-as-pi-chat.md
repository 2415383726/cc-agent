# 重建工作台前端为 pi_chat，展示层改用 DeepSeek Harness

用户对 pi_workbench 的视觉与交互不满意（无侧栏、卡片风格简陋），2026-11-07 决定新建 `pi_chat/` 前端项目：展示层从 MIT 许可的 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 源码做减法移植（保留版权声明），数据层原样保留——`piagent.display.v1` 契约解析、投影归并、Dify 控制规则（票号/陈旧结果/断流不重发）、静态回放与 `check:static` 全部平移。`pi_workbench/` 在 pi_chat 通过契约测试与证据截图对齐后整体删除，不做长期双轨。

## Considered Options

- **原地改 pi_workbench**：壳（Vue 组件/样式）全部重写、芯（纯 TS 数据层）不变，与新建的实质工作量相同；放弃，因新目录可让旧工作台在过渡期充当回放与行为对照基线，收尾一次删除。
- **仅按截图仿制 DeepSeek 风格**：视觉还原差、交互细节（折叠行、分页问卷、跳过语义）靠猜；放弃，MIT 源码允许直接移植标记、样式与交互，不凭截图猜。

## Consequences

- 展示栈固定为 Vue 3（用户约束，2026-11-07：与 copilotkit-dify 同栈，不接受 React 分叉）。spike 实验证实 Harness 组件可脱离 Cordis 抽取（React 18 下 212 个文件零修改可构建渲染），但该结论只作**移植参考**使用：Vue 实现逐字复用其 ui-theme 令牌 CSS 与 CSS Modules、照抄投影记录纯 TS 类型与 DOM/类名结构、按 React 源码将交互忠实重写为 Vue SFC，不凭截图猜。数据层为框架无关纯 TS，原样平移。
- transport 新增 Dify 原生会话重命名/删除端点（侧栏历史列表需要），仍不触及 `pi_dify`、`copilotkit-dify`、`cc_agent`。
- AGENTS.md 的 pi_workbench 边界条款在删除后改写为 pi_chat 对应条款；「回放必须用同一契约与组件，不做第二个渲染器」的约束不变。
- 本决策修订 ADR-0007 对 Leyline 展示层的选择；ADR-0008 的静态前端分离（无公网资产、不运行 Node/Pi 后台）继续成立。
