# CC Agent 的运行时 MCP 工具接入

Status: ready-for-human

## 已确认的行为

生产 Dify 为 1.15.0，现有 AG-UI/CopilotKit 保留。两个 CC Agent 策略增加可选字符串参数 `mcp_servers_config`，启用 Dify 模板输入。参数接受 server map 或 `mcpServers` 包装；每项配置支持 `transport`（`sse` 或 `streamable_http`）、HTTP(S) `url`、字符串 `headers`、正数 `timeout` 和 `sse_read_timeout`。留空维持现有行为，省略 transport 默认 sse，超时默认 50 秒。

Dify 在调用策略前完成变量替换，例如 header 的 `X-User-Id` 引用 `{{#sys.user_id#}}`；插件只解析已经替换的 JSON。无需升级或修改 Dify，不在插件里新增模板语言。

本轮按配置连接各远程 MCP 服务，发现 tools（含分页），将完整 inputSchema 与现有内部/Dify 工具合并到 ToolCatalog。每个 MCP 工具有稳定的服务命名空间，远端调用保持原始工具名，工具不能互相覆盖。工具经过现有调度、预算、错误配对和两种输出策略。保留 isError、structuredContent、文字及图片/资源产物，不把二进制 base64 写入模型历史。

连接仅属于当前运行，正常完成、初始化失败、模型失败、用户中断和生成器提前关闭均释放；不同轮次/用户不复用客户端、header 或工具目录。配置 header/URL 中的凭证不进入模型提示、工具元信息、持久状态、日志或最终输出。错误信息经过脱敏，不能直接输出 SDK/HTTP 异常原文。

使用官方 MCP SDK 的远程客户端。配置不提供本地 stdio、进程执行或内部文件工具；resources/prompts 不自动包装为工具。本次用户授权扩展远程外部工具来源，保留 Dify 会话状态和原有工具能力。

用户补充：接入的是 MCP Apps 服务，仅需要普通工具。发现阶段过滤 `_meta.ui.resourceUri` 关联的 App 工具及 `_meta.ui.visibility` 不含 `model` 的工具；兼容旧 UI resource/template 元数据。visibility 缺省允许模型可见，显式格式错误不注册。普通工具即使同时对 app 可见也应保留；不能按工具名称前缀猜测类型。已对照本机只读参考 `ct-mcp-server/src/domains/mcp-app.ts` 与 `src/contracts/tool-meta.json`：默认 21 个工具中保留 12 个普通业务工具，过滤 5 个 App 入口和 4 个仅 App helper。过滤工具既不在模型目录中，也不能通过 ToolAdapter 派发。

## 测试与验收

用户明确确认三个测试边界：配置解析；ToolCatalog/ToolAdapter 的发现和调用；两种输出策略的完整运行与连接释放。使用 unittest、fake Dify 对象和 MCP/HTTP 边界替身；真实本地协议服务验证 SDK 的两种传输及 header，不依赖生产服务。

覆盖同名工具、嵌套 schema、分页、错误结果、超时/断连、输出保留、敏感信息不泄露、跨用户隔离以及提前退出清理。运行相关测试、增量类型检查，最后完整后端测试和双架构离线包校验。更新配置说明、域边界文档和离线依赖。

实现后按 code-review 技能分别审查 Standards/Spec。审查基准为开工 HEAD `5aa8543000452613c9f7cc2ff24edbfcaa7b9fb9`，修复有效问题并提交当前 main 分支；不提交与本次实现无关的 AG-UI 调查文件。

## 验证记录

实现版本 0.0.3。完整后端 unittest 209 项通过；新增模块和接入层的 mypy 检查通过；新增文件 Ruff 与 Black 检查通过。实际本地协议服务覆盖两种传输、多服务、三个用户并发 header 隔离、超时、文件产物及中断/提前退出清理，测试使用真实 Dify SDK 导入后的 gevent 环境。新增 CT 21→12 元数据快照、真实 SDK 过滤与拒绝调用、双策略提示过滤，以及首次连接的独立进程日志脱敏回归。业务身份头 `X-Employee-Id` 与已有 `X-User-Id` 同样不作为认证凭证替换，保留业务结果中的工号；API Key/token 继续脱敏。

离线依赖已分别验证 Linux amd64/arm64，并生成双架构 difypkg。尚未连接用户生产 MCP 或在生产 Dify 安装。

## 审查记录

Spec 独立审查发现 1 项 P2：递归脱敏会破坏碰巧包含 header 值的二进制 base64。已改为先解码产物、再脱敏文字和元数据；新增 image/resource blob 回归测试在修复前失败、修复后通过。审查者已复核解决，无未解决的 Spec 问题。

Standards 独立审查发现 1 项 P2：首次连接才创建的 httpcore 日志器没有安装脱敏过滤器。已在建立客户端前为锁定 HTTP 栈的所有实际日志器安装过滤器；独立子进程验证首次连接在 DEBUG 响应头中回显凭证时也不会泄露。审查者已复核解决，无未解决的 Standards 问题。

用户补充的 MCP Apps 过滤另经 Standards/Spec 两轴独立复核，均无新增问题。Spec 审查者独立运行 CT 快照、真实 SDK 过滤及双策略提示测试通过。最终总计：Standards 1 项 P2 已修复；Spec 1 项 P2 已修复。
