# Pi Strategy — 首次 Dify 平台联调证据

Date: 2026-11-16/17。环境：本地 Dify（docker compose，控制台 127.0.0.1），工作区 `198506's Workspace`，模型 `langgenius/deepseek/deepseek-v4-flash`。

本次联调在真实 Dify 平台完成：插件安装、应用编排、多轮对话、问卷恢复、工具审批、自带 UI 渲染验收。这不是完整验收：真实远程 MCP 业务工具、arm64 执行与长期稳定性仍待验证。

## 部署

| 项 | 值 |
| --- | --- |
| 插件 | `pi_strategy/pi_strategy:0.1.0@9f63d6e8…`（amd64 离线包） |
| 安装方式 | 控制台 API `POST /plugin/upload/pkg` + `install/pkg` |
| 应用 | `pi-strategy-native-test`（advanced-chat，从 pi_dify 测试应用的 DSL 导入后改接线） |
| 接线 | Agent 节点策略 `pi_strategy_native`；`query=sys.query`、`agent_state=conversation.agent_state`（经变量赋值回写）、`conversation_id/user_id/app_id=sys.*`、Dify 工具 time ×2、远程 MCP ct 服务 |
| 注意 | 升级插件须先卸载（同 `plugin_id` 重复安装报 "already installed"）；应用节点钉住 `plugin_unique_identifier`，换版本后需更新草图并重新发布 |

## 验证结果

| 检查 | 结果 |
| --- | --- |
| `python -B -m unittest discover -s pi_strategy/tests` | **147 passed**（含引号包装回归） |
| 离线包构建（amd64） | 成功，26,482,913 bytes，sha256 `0ce50e95…` |
| `verify_offline_package.py --arch amd64` | `--no-index` 安装 0.3s；冒烟 answer="offline ok"、终态 completed、前缀 `pistrategy-state` |
| 文本回合（服务 API `/v1/chat-messages`） | 回答正常；Agent 节点输出含 `agent_state`（`pistrategy-state:v1:gzip-base64:`）、`answer`、`json`、`text` |
| 跨轮状态 | conversation_id 保持；revision 递增；第二轮精确复述第一轮问题（Pi entries 历史生效） |
| 日志形状 | `Run started` / `Run finished`（status+stats）/ `Final answer`（`pi_strategy.final_answer`），`data.raw` + `<details>` HTML，与 `CC Agent (Dify)` 一致 |
| ask_user 问卷 | 工具卡"等待回答" + 编号问卷文本；query 回复 `1. 蓝色\n2. …` 恢复成功，模型继续执行（本轮还走了 activate_skill + visualize，视觉片段内嵌工具卡） |
| 工具审批 | `approval_mode=configured` + `approval_tools=[current_time]`；"等待确认"卡 + 审批文本（同意/当前会话始终允许/拒绝）；回复"同意"后工具真实执行并汇报时间 |
| 自带 UI 渲染 | `<think>` 渲染为"已深度思考"折叠块；工具卡摘要徽章（等待确认 `>_ current_time`）正常；审批/问卷文本可读 |
| 浏览器预览（Chatflow 编辑器） | 上述渲染均在自带 UI 中截图确认 |

## 第二轮联调（2026-11-17）

| 检查 | 结果 |
| --- | --- |
| ct 远程 MCP 业务工具（人员检索） | `search_people` 单轮最多 13 次调用全部"已运行"；测试库无姓「张」人员（数据形态为「示例甲/乙/丙…」共 23 人），用「示例」关键词成功命中 23 人并列出前 3 名（姓名+单位表格）；多轮 MCP 调用、结果预算与配对正常 |
| 审批恢复补发工具卡（本轮优化） | 批准后回答流中出现"已运行"状态工具卡（含工具名与真实结果）；拒绝/工具失效场景渲染"未执行"卡；回归断言加入 `test_runtime.py` 的两条审批用例 |
| slash 技能激活 | `/skill:pi-strategy-help …` 触发 `Skill activated` 日志，模型按技能内容准确回答交互机制（内建技能 user-only 激活链路） |

本轮改动：`observer.py` 新增 `display_status_for` 与 `approval_tool_card`；`runtime.py` 的 `_apply_approval` 三个分支（批准执行、拒绝、工具失效）补发原生工具卡。测试 147 通过；离线包 sha256 `bea9ceeb…`，安装为 `pi_strategy/pi_strategy:0.1.0@1ea33535…` 并重新发布验证。

## 第三轮联调（2026-11-17）：stop 与状态压缩

| 检查 | 结果 |
| --- | --- |
| 平台 stop（服务 API `stop` 端点） | 修复前：插件走 BaseException 崩溃路径——回答 "The Pi agent run failed." 且无状态输出（取消点在 MCP 连接建立处，`CancelledError` 绕过 `except Exception`）。修复后：流干净结束，workflow `stopped` / "Stopped by user."；停止轮整轮作废（含该轮 query），会话变量保持上一轮成功状态，续聊正常。语义可接受：未完成的输出本无可保存结果 |
| 状态压缩压测（`state_max_encoded_bytes=9000`，6 轮 500 字输出） | 修复前：turn3 触发一次 compaction 后，turn4/5 全部 `state_save_failed`（shrink 预算下限 64KB 淹没 4KB 目标，完全不动作）。修复后：6 轮全部 `persisted=True`，encoded 稳定收敛于 3216 bytes，压缩摘要保留 |
| shrink 修复细节 | `_shrink_entry_bodies` 预算下限 64KB → `max(1024, target)`；clip 档位渐进 2000/800/300/120；squash 不再覆盖 toolResult `details`（保 `execution_outcome=unknown` 标记）。回归测试 ×3（小预算保存、逐轮保存、unknown 标记保留） |
| visualize 内嵌片段 UI 渲染 | 自带 UI 截图确认：visualize 工具卡展开后，验证过的 HTML 片段直接渲染为可见卡片（"联调成功"蓝色圆角卡）——Q11 决策（片段注入工具卡）的最终视觉证据 |
| 测试 | **151 passed**；安装 `pi_strategy/pi_strategy:0.1.0@64f7e272…`（sha256 `b19d8ea1…`） |

本轮改动：`runtime.py` `execute_async` 捕获 `asyncio.CancelledError`（`asyncio.shield` 包 finalize），状态以 `stopped` 保存；`state.py` `_shrink_entry_bodies` 渐进压缩。

## 联调中发现并修复的问题

**Dify 1.5 多行 query 引号包装工件**：`{{#sys.query#}}` 模板替换会把多行值包进一对字面 `"`（pi_dify 的 `config.py` 早已为 JSON 交互参数记录过同一工件；`interaction` 参数已移除，但 `query` 仍走模板替换）。单行 query 不受影响；多行问卷回复的首行 `"1. 蓝色` 因此匹配不上编号，导致恢复被拒。

修复：`interaction.py` 的两个解析入口增加 `_unwrap_quoted`，剥掉一对外层字面引号（消费端最小改动，模型可见文本不变），并加了回归测试 `test_quote_wrapped_multiline_reply_is_unwrapped`。诊断手段：临时把收到的 query repr 注入可见错误消息后重跑定位（补丁只存在于已被卸载的旧包副本中，现行安装包不含调试代码）。

**插件升级流程**：同 `plugin_id` 重复安装报 "already installed"（安装任务静默失败），必须先 `uninstall`（需 `plugin_installation_id`，取自 list 记录的 `installation_id` 字段）再安装；应用 Agent 节点钉住 `plugin_unique_identifier`，换版本后须更新草图并重新发布，否则继续跑旧包。

**停止语义**：Dify 平台 stop 会终止工作流（Agent 节点不再完成、变量赋值不执行），因此被停止轮次整轮作废、会话变量保持上一轮成功状态；插件侧的 `CancelledError` 处理保证不产生误导性失败文本且内部终态为 `stopped`。这不是缺陷，是平台停止的固有语义。

## 已知差异 / 待验证

- arm64 未验证；生产 arm64 需 `--resolve-only` 证据或真机验收。
- 并发 stop（多会话同时停止）、provider 异常矩阵未在平台端压测。
- ct MCP 仅实测了 `search_people` 契约工具；其余业务工具未逐个执行。
