# 02: dsh 主题基座与应用壳

**What to build:** 从 DeepSeek Harness vendor 展示基座：ui-theme 设计令牌 CSS（`--dsw-*`）与基础样式，随附 Montserrat 字体 OFL 许可文件与 MIT 版权声明；确立浅色主题。应用壳布局为三区：左侧栏轨道（本票仅占位）、聊天时间线列、底部 composer 区（可输入，发送暂为回放占位）。全站中文文案基线就位。CSS Modules 类名与 DOM 结构照抄 Harness 源码，不凭截图猜。

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] 应用视觉使用 dsh 设计令牌（字体/间距/圆角/色板），与 DeepSeek 截图同族
- [ ] MIT 版权声明与 Montserrat OFL 许可文件随 vendor 资产保留
- [ ] 三区布局成型：侧栏轨道占位、时间线滚动区、composer 区
- [ ] composer 可输入文本，样式与 Harness 输入区同族（发送逻辑留待后续票）
- [ ] 构建与既有测试保持全绿
