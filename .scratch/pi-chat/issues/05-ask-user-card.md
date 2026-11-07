# 05: AskUser 问卷卡

**What to build:** 卡片体系原语 + 完整问卷卡，视觉对齐 Harness 的 ui-user-questions：题目标题与描述、编号选项、选项描述、推荐徽章解析、单选/多选/自定义文本三型、必填校验与 min/max 选择约束、分页器（如 1/2）、跳过（保留其余草稿）、按 expires_at 倒计时、作答后只读回显。提交走既有协议：新 Dify 轮次的 `inputs.interaction` JSON（回放模式走回放控制器本地闭环）。问卷作答不是工具授权——语义与 06 严格分离。

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] questionnaire 回放可完整交互：作答、翻页、跳过、提交全程可用
- [ ] 必填缺失阻止提交并提示；multi 型 min/max 约束生效；text 型 placeholder/max_length 生效
- [ ] 提交中禁用交互；作答后卡片变只读回显
- [ ] 倒计时按 expires_at 呈现（无可倒计时不报错）
- [ ] 组件测试平移：必填校验、三型提交、提交中禁用、历史作答回显
