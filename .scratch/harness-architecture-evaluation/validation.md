# Harness 改进实施与验证

日期：2026-10-28。基线：`ea8f45a`。用户授权：删除 allowlist / denylist；身份由已有节点控制；按架构建议实施。

## 实际交付

- 删除工具 allowlist / denylist、技能 denylist 的配置字段、解析、过滤和调度分支，删除对应功能测试。保留重复调用/连续错误保护、技能入口资格、资源路径检查和旧 v1 中断恢复；会话确认仍使用既有路径。未引入身份代理或改写 user ID。
- 工具流显式区分 delta 与 snapshot；delta 保留重复字符，snapshot 采用替换语义。归并 index 与首块/后到 id，支持交错调用；缺少足够身份的多调用片段明确拒绝。模式可通过 runtime_config 配置。
- 技能正文仅在模型当前上下文保留一份；历史保存简短激活记录。旧注入历史在模型视图中也被缩减。预算压力可释放已经消费的旧技能，新加载、尚未消费的技能受到保护；最新完整正文保留，仍可按定义完整性重载。当前任务视图聚焦未完成任务，增加上下文构成估算。
- 状态加载和编码复用同一本轮 backend；`previous_revision` 明确表示快照序号。先输出 `agent_state` 再发终态；兼容 persisted 字段，增加 delivery_status 和 platform_persisted。增加 run_status，区分本轮完成、等待用户、失败和预算耗尽，不把事件名当成业务成功。
- 运行预算默认最多 32 次模型调用、64 次实际工具调用、300 秒协作式耗时；累计 token 上限可选。摘要、重试、续写、最终请求、批准恢复共用同一预算。未执行工具产生配对结果；运行元信息包含实际用量和工具 outcome。
- 串行工具逐项发送开始及结果；模型仍在全批次预算和结果配对后继续。保留 Dify 产物原转发路径及直连 MCP blob 转发，批准恢复也走同一路径。
- 前端加载历史时同步读取 Dify `agent_state`，有界解码成恢复视图，恢复待处理中断；历史和恢复结果共用 request/ticket 检查。恢复读取设 10 秒总超时；失败仍保留历史并显示状态不可用。恢复卡片通过现有交互展示和命令继续执行。
- 停止请求检查 HTTP 状态；界面区分停止接收、停止请求失败及结果未知。断流缺少终态时标记 unknown；不自动重放工具。Dify task ID 和 plugin run ID 可在本轮界面状态中关联，工具与模型诊断带 run ID，默认不记录模型正文或附件原始 JSON。
- 增加业务技能完成证据、长作业、unknown 结果及幂等核实的验收指引；提示指导模型保存短 job/evidence 引用并核实业务结果，不引入通用 critic、后台队列或第二套存储。
- 移除未被运行源码使用的六项文档/数据处理直接依赖及无关传递依赖，同步 uv.lock、requirements、Linux 离线锁和 wheels。保留部署所用 SDK 及其依赖版本，并使 uv.lock 的 greenlet 与既有离线锁一致。离线 wheels 目录约从 123MiB 降至 31MiB；移除 32 个不再需要的 wheel，备份在 `/tmp/cc-agent-harness-unused-wheels/`。离线打包排除开发检查缓存；manifest 移除过时 Memory 描述。

## 验证结果

- 完整后端 unittest：**248 项通过**。使用缓存 Python 3.12 与既有依赖 runner，未修改仓库虚拟环境。日志：`/tmp/harness-final-backend.log`。
- 完整前端 Vitest：**41 个文件、194 项通过**，包括恢复卡片 SSR、同会话旧恢复结果、恢复失败保留历史和恢复后的精确 prompt 继续。日志：`/tmp/harness-final-frontend.log`。
- TypeScript：`npx tsc --noEmit` 通过；Vite 生产构建通过。日志：`/tmp/harness-final-build.log`。构建仍提示既有图表/Markdown 等大 chunk，未在本轮调整拆包策略。
- **19 个核心模块 mypy 通过**（`--follow-imports=silent --ignore-missing-imports`）。检查不等于全仓严格类型检查；未注解函数体遵循现有 mypy 默认设置。日志：`/tmp/harness-final-mypy.log`。
- 改动 Python 文件使用 Black `-C -l 100`；Ruff 的导入、未使用名称规则通过；`git -c core.whitespace=cr-at-eol diff --check` 通过。
- `uv lock --check --offline` 通过；离线构建验证 Linux amd64 / arm64 的锁定依赖解析，生成 `cc_agent/dist/cc_agent-0.0.4-offline-linux-amd64-arm64.difypkg`。日志：`/tmp/harness-final-offline.log`。
- 本地探针重跑：首块 id 与参数正确归并；重复数字 11 保留；工具结果在后一个工具执行前可见；技能正文只出现一次。两个 previous revision=7 的编码仍都得到 revision=8，这正是快照序号的既有能力范围，不宣称 CAS。

关键行为先通过失败回归确认，再修复；额外自查发现刚加载的同批技能不应作为旧技能释放，已补回归并修复。自查覆盖工具结果配对、完整 pending 保存、普通/恢复统一预算、两输出策略及附件路径；没有采用两个独立审查代理。

## 部署验证边界

未连接生产 Dify、真实 provider 或业务 MCP。delta/snapshot 的实际模式需按部署 provider 的脱敏样本核对；当前默认 delta 也接受一次性完整调用，累计快照型 provider 需配置 snapshot。默认预算可通过 runtime_config 调整。

插件无法确认后续 Dify 对话变量赋值完成，也不能保证停止请求终止远程业务副作用。真实平台写回、会话变量读取权限/兼容、取消传播、业务幂等与成功证据仍按 [业务验收指引](/home/ygao/Desktop/work/cadre-system/cc_agent/docs/harness-validation.md) 在部署环境核实。这里没有把这些外部能力写成已验证事实。
