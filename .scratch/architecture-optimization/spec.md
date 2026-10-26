# CC Agent 架构优化与功能裁剪

Status: ready-for-human

## 已确认范围

用户同意架构报告中的六项优化全部实施，并确认删除两条演示命令和记忆功能，保留任务工具。基线 HEAD 为 `0bbace1`。保留 Dify 会话状态、AG-UI / Dify 两种输出策略、当前前端框架、MCP 每运行隔离与 App/hidden 工具过滤。

删除 MemoryList/MemorySearch/MemorySave/MemoryDelete 的工具 schema、执行、专属提示、状态写入与展示；旧 agent_state 中的 memory 字段忽略并在再次保存时消失，历史、任务、授权、技能和待处理中断仍可继续恢复。不迁移记忆到其他产品功能。删除 `/a2ui-demo` 与 `/weekly-report-card` 及专属演示实现和测试。删除确认无生产调用的旧 reducer、资源读取及会话恢复入口；保留真实 Dify fallback 和 SkillRuntime 的按需资源路径检查。

## 六项优化

1. 集中授权、确认、回答匹配和中断续接。会话允许只免确认，不能绕过 allowlist/denylist、重复调用与连续错误限制。兼容现存 v1 pending 元数据；批准后工具产物进入既有输出路径：Dify 工具保留重复两半及语义 JSON 去重，不增加第二条产物转发路径；直连 MCP 产物由插件输出。
2. 收拢模型请求准备、预算、压缩和恢复。保留静态超预算前置拒绝、系统提示、最终合成、续写与错误配对；上下文溢出按 AGENTS 规定压缩并重试一次，再失败则 context_overflow。
3. 合并 ToolCatalog/ToolRegistry，仅保留一个工具目录及 ToolSpec；删除拆包、双类型和重复查找，不为工具来源增加新框架。
4. 收拢前端完整运行流解释；native AG-UI 保真与实际 Dify fallback 共存，统一中断/终止状态，删除无生产调用的影子 reducer 和反向归一化。
5. 集中会话/thread 身份、history ticket、过期结果和 visible clone 等待；保留宿主 props 与 launchWithMessage，不自动恢复上次会话。
6. 技能选择、恢复和激活政策集中，slash 与模型 Skill 行为一致，denylist 和两策略技能面在恢复后仍生效。

## 已复现问题

- 会话授权后仍被第二套确认政策拦截；统一确认决策源。
- 极限压缩后 state_summary 报告裁剪前数量；摘要以实际保存快照为准。编码失败继续保留失败与 inline 回退语义。

## 验证面

沿用已接受架构报告中的行为测试面：运行入口跨轮授权/中断与保存状态；AgentLoop 模型预算、恢复、续写和最终合成；工具目录与技能恢复/激活；前端运行流与会话协调。测试通过公开 interface 观察结果，在 Dify/model/HTTP/SDK seam 使用 fake，不对私有 helper 追加测试。缺陷先红后绿，纯删除依靠相关回归。

每批运行相关测试和增量类型检查；最后后端 unittest、前端 Vitest、构建、离线双架构依赖校验。更新域词汇、裁剪决策、使用说明和包版本；按 Standards / Spec 两轴审查后提交当前分支。与本次无关的 AG-UI 调查文件保持未提交。
