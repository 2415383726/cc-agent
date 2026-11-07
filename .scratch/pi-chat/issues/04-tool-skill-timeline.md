# 04: 工具与技能时间线

**What to build:** 工具调用折叠卡与活动行，视觉对齐 Harness 的 ui-tool：可折叠组（运行中转态、参数 JSON 格式化、结果区、展开/收起）、加载技能行（glyph + 技能名，展开显示说明）、压缩行、注释行。投影记录类型对齐 Harness 的纯数据形状（ToolCallBlock/ToolResultNode/ToolArgs），内部工具（ask_user/activate_skill/read_skill_resource）不以工具卡出现，分别由问卷卡与技能行承载。

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] process 回放展示完整工具时间线：工具卡可展开参数与结果，运行中状态有转态指示
- [ ] 内部工具不出现在工具卡（现有投影隐藏规则测试保持全绿）
- [ ] 技能行显示技能名并可展开；压缩行与注释行正常呈现
- [ ] 工具失败仍有合成结果呈现（配对不变量）
- [ ] 组件测试覆盖折叠交互、状态徽标、内部工具隐藏
