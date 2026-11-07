# 03: 消息时间线

**What to build:** 以 Vue SFC 重写 Harness 风格的消息时间线：用户消息右侧气泡（时间戳 + 复制按钮）、助手区流式全量 markdown（表格/代码块/列表，markdown-it `html:false` + highlight.js，打字指示）、思考折叠行（默认收起、灰阶、单行截断）、终态行（「已完成，用时 X 秒」+ 失败/停止/预算等状态徽标）。process 回放在此票完成后呈现 DeepSeek 视觉。

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] process 回放完整呈现用户/助手/思考/终态四类条目，视觉与 Harness 同族
- [ ] 思考行可折叠展开；用户气泡复制按钮可用
- [ ] 流式 delta 合并与最终文本不重复显示（投影测试护栏保持全绿）
- [ ] 终态行按状态区分文案与徽标（completed/failed/stopped 等）
- [ ] 组件挂载测试覆盖气泡渲染、折叠交互、终态区分
