# pi_chat

Pi Harness 显示层的 Vue 3 + Vite 重建（自 MIT 许可的 DeepSeek Harness 做减法移植展示层，数据层自 pi_workbench 平移）。连接真实 Dify（服务型 API）进行流式对话，凭据只保存在本页 `sessionStorage`。

## 开发

```bash
npm install
npm run dev      # 本地开发
npm run test     # vitest 单测（happy-dom）
npm run build    # 产物构建
```

## 手动冒烟清单（票 08）

> 准备：`npm run dev` 打开页面；准备一个真实 Dify「服务型 API」应用的地址与 API Key。
> **凭据只通过页面表单填写**（保存于 sessionStorage，关闭标签页即失效）；切勿把任何 Key 写进代码、测试或提交记录。
> Dify 应用节点需显式映射 `query`、`files`、`interaction`、`agent_state` 等输入（见 pi_dify 插件文档）。

### 1. 连接表单

| 步骤 | 预期 |
| --- | --- |
| 打开页面（未连接） | 连接表单常显 |
| 不填 API Key 直接点「连接」 | 表单内红字提示「请填写服务地址与 API Key」，不发请求 |
| 应用输入填入非法 JSON（如 `{bad`）后点「连接」 | 表单内红字显示 JSON 解析错误，不发请求 |
| 应用输入填入 `[1, 2]` 后点「连接」 | 提示「应用输入必须是 JSON 对象。」 |
| 填写服务地址 / API Key（+ 可选用户标识、inputs JSON）后点「连接」 | 表单收起，进入实时会话视图；侧栏出现历史会话列表 |
| 连接失败（如地址错误 / Key 无效） | 表单保持展开并显示「连接失败：…请检查后重试」；侧栏同步显示「会话列表加载失败 + 重试」按钮，点「重试」可再次拉取 |
| 连接成功后点头部「连接设置」 | 表单再次展开（已连接态带「收起」按钮），点「收起」关闭 |

### 2. 流式对话（消息流式 + 终态）

| 步骤 | 预期 |
| --- | --- |
| 在 composer 输入文本，按 Enter 或点发送按钮 | 输入即清空；乐观用户气泡立即出现（右侧、带附件 chips 如有） |
| 等待回复 | 助手文本流式出现；工具 / 思考 / 技能 / 压缩按时间线渲染 |
| 回合结束 | 出现可信终态行（如「已完成，用时 X 秒」）；最终文本合并不重复（无重复气泡） |
| 回合闭合后 | 过程行（思考/工具组）折叠进终态头（点击展开还原）；助手文本后出现「复制 + 时间」回合尾行 |
| 模型调用 `visualize` | 对话内出现沙箱交互卡（iframe 不透明源、零网络 CSP）：片段内联渲染，高度自适应（inline 800 / wide 1200 封顶）；片段缺失时降级为占位说明 |
| 侧栏点面板图标 | 侧栏折叠为 56px 导轨（开关静止为鲸尾标、悬停换出面板图标 + 新会话图标）；再点展开，轨道过渡缓动；会话列表滚动条跟随指针（指针离开约 2s 后隐藏） |
| 窗口宽度 ≤1024px（拖窄窗口） | 侧栏自动收拢为导轨；拉宽恢复后可再手动展开 |
| 会话 ≥2 回合时 | 右缘出现回合导航轨：刻度标注当前回合（随滚动跟随），悬停弹出该回合预览卡，点击跳转对应回合 |
| 回合 ≥3 且向上滚动 | 时间线底部浮现「回到底部」浮动钮（34px 圆钮、composer 卡上方）；点击平滑滚回底部，跟随吸底时自动隐藏；滚动中途的新内容保持贴底（动画进行中 retarget，不切断） |
| 早期回合的回合尾 / 更早的用户消息行 | copy + 时间 actions 默认隐藏，悬停该行（或键盘聚焦）渐显；最新回合尾恒显 |
| 运行中再次按 Enter / 点发送 | 不发送（发送按钮已让位给停止按钮）；按住 Enter 连发不重复提交；Ctrl/Cmd+Enter 与 Enter 均可发送 |
| 运行中看 composer 右缘 | 停止按钮为蓝底圆形 + 16px 圆角方块字形（悬停 title「停止」），停止请求中禁用 |
| 点「更早」按钮（历史较长会话） | 分页加载更早消息，去重无重复 |

### 3. 停止

| 步骤 | 预期 |
| --- | --- |
| 运行中点 composer 里的「停止」 | 按钮变为「停止中…」并禁用；顶部出现「已请求停止；只有服务端终态才能确认最终结果。」提示 |
| 服务端确认停止 | 终态行显示「已停止」，无未确认警告 |
| 断流未确认（停止后未见服务端终态） | 出现「未确认」终态与说明「已请求停止，但没有收到可信的服务端终态。」，另有备注「已请求停止；结果未确认，未重新发送请求。」——**界面绝不自动重发**，需要用户手动重新发送 |
| 停止结束后 | 停止按钮消失，发送按钮恢复 |

### 4. 附件上传

| 步骤 | 预期 |
| --- | --- |
| 点 composer 左下「+」 | 打开系统文件选择器（可多选；未连接时为禁用占位） |
| 选择文件 | 请求 `POST /files/upload`；上传中 composer 显示「上传中…」chip，期间禁止再次选择与发送 |
| 上传成功 | 待发送区出现附件 chip：**仅文件名 / 类型 / 大小**（如 `报告.pdf · application/pdf · 2.0 KB`），可点「×」移除 |
| 输入文字并发送 | 请求体 `files` 以 `transfer_method: "local_file"` + 上传 id 传入；发送后草稿与 chips 清空；消息区用户气泡展示同一份安全元数据 |
| 上传失败（如文件过大） | 侧栏底部出现「附件上传失败：…」兜底提示；chip 不加入，可继续发送文本 |
| 安全性核对 | 界面任何位置不出现文件内容、本地路径或可下载链接（附件只有元数据） |

### 5. 问卷（AskUser）

| 步骤 | 预期 |
| --- | --- |
| 触发需要澄清的请求（agent 调用 ask_user） | 问卷卡出现：编号选项 / 描述 / 分页（如 1/2）/ 跳过；时间线暂停等待作答 |
| 必填题不选直接「下一题 / 提交」 | 行内校验提示，不放行 |
| 逐题作答并提交 | 卡片转只读回显「已回答」+ 答案；对话在下一轮继续 |
| 点「取消」 | 卡片回显「已取消」，agent 收到取消 |
| 刷新 / 切走再切回会话 | 未答问卷经 `agent_state` 恢复，可继续作答（不自动代答、不自动重发） |

### 6. 审批授权

| 步骤 | 预期 |
| --- | --- |
| 触发工具授权（agent 请求审批） | 审批卡出现：工具名 / 参数可见、once / session 范围选择（默认 once）、阻断提示醒目 |
| 批准 | 卡片回显「已批准（范围）」；工具执行并在时间线继续 |
| 批准后 | 轮次结束出现终态行，最终文本合并不重复 |
| 拒绝 | 卡片回显「已拒绝 / 未执行」非执行态；agent 收到拒绝原因 |
| 刷新 / 切走再切回会话 | 待审批经 `agent_state` 恢复，仍可决定（不自动批准） |

### 7. 会话切换 / 删除 / 重命名

| 步骤 | 预期 |
| --- | --- |
| 侧栏点某个历史会话 | 时间线切换为该会话历史（含恢复的待交互占位与终态）；当前会话高亮 |
| 双击会话名（或行内铅笔图标）重命名，Enter 提交 | 列表即时更新；失败时侧栏底部出现「重命名失败：…」 |
| 行内垃圾桶图标 →「删除该会话？」→「删除」 | 条目移除；删除当前会话回到新会话空态（陈旧流结果被丢弃） |
| 点「新会话」 | 回到空会话，可立即发起全新对话 |
| 切换 / 删除过程中有回复正在流式返回 | 旧会话的迟到事件不串入新视图（陈旧票号丢弃规则） |

## 测试边界说明

- 停止 / 断流规则（`stopped_unconfirmed` 合成终态、绝不自动重发、停止 best-effort）由 fake transport 控制器测试与真实传输链路的组件测试双重覆盖（`tests/controller.test.ts`、`tests/composer.test.ts`、`tests/app.test.ts`）；上表冒烟用于对真实后端的最终确认。
- 附件只走 Dify `local_file` 传输与安全元数据展示；不存在文件内容访问路径。

## 删除门执行清单（票 09 阶段 2 · 交接文档）

> 本清单是删除门的唯一执行依据：阶段 1 已完成 check:static 移植（`scripts/check-static.mjs` + `npm run check:static`）、whale 品牌资产清理（构建零告警）与证据重制（`docs/evidence/`）。**✅ 阶段 2 已于 2026-11-07 执行**：live 冒烟通过（连接/流式/问卷闭环/重命名/删除/停止，证据 `docs/evidence/10-live-*.png`）后删除了 `pi_workbench/` 并改写 AGENTS.md 条款。

1. **前置确认（全部满足才继续）**
   - `cd pi_chat && npm run test` 三条 seam（投影 / 控制器 / 组件）全部通过；
   - `cd pi_chat && npm run build && npm run check:static` 零告警、零违例，产出 `dist/static-report.json`；
   - 用户按上方「手动冒烟清单（票 08）」完成 live 冒烟：流式对话、停止、附件上传、问卷、审批、历史切换 / 重命名 / 删除全部通过；
   - 证据落位核对：`docs/evidence/` 中 live 截图可对照。

2. **删除旧项目**：`git rm -r pi_workbench/`（含其 docs/evidence 与 scripts/check-static.mjs——机制已平移至 `pi_chat/scripts/`）。

3. **改写 AGENTS.md** 的 pi_workbench 条款为 pi_chat 条款：
   - `pi_workbench/` 项目条目改为 `pi_chat/`（静态 Vue 3 显示层，消费 `piagent.display.v1`）；
   - 「Runtime boundaries」中 `pi_workbench/src/dify/controller.ts` → `pi_chat/src/dify/controller.ts`、`src/projection/transcript.ts` → `pi_chat/src/projection/transcript.ts`；
   - **保留单一渲染器不变量**：「Replay must use the same contract and components, not a second renderer.」（历史恢复与实时必须用同一契约与组件，不做第二个渲染器）；
   - 「Tests」一节中 `pi_workbench/tests/` 条目改为 `pi_chat/tests/`（contract / projection / controller / components / history / staticScan）；开发命令改为 `npm run test`、`npm run build`、`npm run check:static`（在 `pi_chat/` 下）。

4. **同步根 README.md**：`pi_workbench/` 项目简介、构建命令（`cd pi_workbench && …`）与文档链接全部指向 `pi_chat/`；确认仓库内无其他 pi_workbench 残留引用（`grep -rn "pi_workbench" --exclude-dir=node_modules --exclude-dir=.git .`）。

5. **重跑全部收尾门**：`cd pi_chat && npm run test && npm run build && npm run check:static`；根目录各插件测试命令不受影响；提交并在票 09 勾选验收项。
