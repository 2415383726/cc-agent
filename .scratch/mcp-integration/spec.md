# CC Agent 的运行时 MCP 工具接入

Status: ready-for-human

## 已确认的行为

生产 Dify 为 1.15.0，现有 AG-UI/CopilotKit 保留。两个 CC Agent 策略增加可选字符串参数 `mcp_servers_config`，启用 Dify 模板输入。参数接受 server map 或 `mcpServers` 包装；每项配置支持 `transport`（`sse` 或 `streamable_http`）、HTTP(S) `url`、字符串 `headers`、正数 `timeout` 和 `sse_read_timeout`。留空维持现有行为，省略 transport 默认 sse，超时默认 50 秒。

Dify 在调用策略前完成变量替换，例如 header 的 `X-User-Id` 引用 `{{#sys.user_id#}}`；插件只解析已经替换的 JSON。无需升级或修改 Dify，不在插件里新增模板语言。

本轮按配置连接各远程 MCP 服务，发现 tools（含分页），将完整 inputSchema 与现有内部/Dify 工具合并到 ToolCatalog。每个 MCP 工具有稳定的服务命名空间，远端调用保持原始工具名，工具不能互相覆盖。工具经过现有调度、预算、错误配对和两种输出策略。保留 isError、structuredContent、文字及图片/资源产物，不把二进制 base64 写入模型历史。

连接仅属于当前运行，正常完成、初始化失败、模型失败、用户中断和生成器提前关闭均释放；不同轮次/用户不复用客户端、header 或工具目录。配置 header/URL 中的凭证不进入模型提示、工具元信息、持久状态、日志或最终输出。错误信息经过脱敏，不能直接输出 SDK/HTTP 异常原文。

使用官方 MCP SDK 的远程客户端。配置不提供本地 stdio、进程执行或内部文件工具；resources/prompts 不自动包装为工具。本次用户授权扩展远程外部工具来源，保留 Dify 会话状态和原有工具能力。

## 测试与验收

用户明确确认三个测试边界：配置解析；ToolCatalog/ToolAdapter 的发现和调用；两种输出策略的完整运行与连接释放。使用 unittest、fake Dify 对象和 MCP/HTTP 边界替身；真实本地协议服务验证 SDK 的两种传输及 header，不依赖生产服务。

覆盖同名工具、嵌套 schema、分页、错误结果、超时/断连、输出保留、敏感信息不泄露、跨用户隔离以及提前退出清理。运行相关测试、增量类型检查，最后完整后端测试和双架构离线包校验。更新配置说明、域边界文档和离线依赖。

实现后按 code-review 技能分别审查 Standards/Spec。审查基准为开工 HEAD `5aa8543000452613c9f7cc2ff24edbfcaa7b9fb9`，修复有效问题并提交当前 main 分支；不提交与本次实现无关的 AG-UI 调查文件。

## 验证记录

实现版本 0.0.3。完整后端 unittest 205 项通过；新增模块和接入层的 mypy 检查通过；新增文件 Ruff 与 Black 检查通过。实际本地协议服务覆盖两种传输、多服务、三个用户并发 header 隔离、超时、文件产物及中断/提前退出清理，测试使用真实 Dify SDK 导入后的 gevent 环境。

离线依赖已分别验证 Linux amd64/arm64，并生成双架构 difypkg。尚未连接用户生产 MCP 或在生产 Dify 安装；Standards/Spec 审查将在实现提交后进行。
