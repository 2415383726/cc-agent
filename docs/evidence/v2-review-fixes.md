# Pi v2 审查修复与 Dify 联调

日期：2026-10-29。修复基线：`013673a`，分支：`feat/pi-agent-v2`。
这是对 `v2-implementation.md` 初次验证记录的后续补充；该文中的旧测试数量、包哈希和“尚无 Dify 环境”描述是当时的记录。

## 审查问题修复

| 问题 | 修复 |
| --- | --- |
| 策略把自身传给运行时，无法使用真实 SDK 会话 | 使用 `self.session`；增加真实策略入口回归 |
| MCP HTTP 客户端参数与锁定版本不符 | 按 MCP 1.26 接口传入每次运行独立的 `httpx.AsyncClient`，统一关闭连接 |
| 高压缩率状态保存成功却无法解码 | 编码同时限制压缩后大小和解压后 4 MiB 大小 |
| 存储裁剪后的压缩摘要脱离活跃分支 | 对包含摘要的完整候选链修复父子关系 |
| 最终正文混入 reasoning | 正文只提取 text block，reasoning 独立展示 |
| 非流式请求丢失用量 | 从已解析的最终消息记录 usage |
| 非流式回退绕过第二次请求预算 | 回退前重新检查预算和停止标志 |
| 更换同名工具提供方后仍能沿用旧审批 | pending、指纹与会话授权绑定实际工具身份摘要；恢复时重新核验 |
| MCP `isError` 被当作成功 | 工具结果、卡片状态与连续错误统计一致标记错误 |
| 模型流先缓冲到底才交给 Harness | 返回事件流后由同一请求上下文中的 asyncio producer 推进；逐块让出执行权 |
| 同步 SDK 导致停止监听不及时，后续工具仍可能启动 | 模型、回退和工具入口直接检查停止标志；保留协作式停止边界 |
| 纯文本历史遗漏助手回答 | 为每条历史回答生成配对的 start/end 事件，复用现有 reducer |
| 新请求断开后沿用上一轮成功终态 | 新流开始时清除上一轮终态与平台回答 |

最初新增的 11 个后端、2 个前端回归用例均在修复前失败。后续补充真实 SDK 注册和状态恢复边界测试。

## 联调发现并修复的问题

- 策略 YAML 的 `description` 层级不符合 SDK schema；改为顶层。
- SDK 注册依赖 `_assets`；补齐 `_assets/icon.svg`，并以真实 `PluginRegistration` 验证。
- 打包后的 `requirements.txt` 显式设置 `--no-index` 和 `--find-links ./wheels`。
- Dify 1.15 的 `/messages` 在本次高级聊天应用中返回空的 `agent_thoughts`，刷新后仅靠历史无法恢复问卷或审批。工作台从会话变量读取已保存的 Pi 状态，仅投影最新交互与终态；交互有效性仍由插件判断。
- Dify 1.15 的 PostgreSQL 会话变量名称过滤在本机返回 500。客户端使用不带该过滤条件的分页接口，再按名称选择 `agent_state`。

状态恢复有 190 KB 编码与 4 MiB 解压限制，检查会话归属，并丢弃会话切换后的过期响应。无法读取时提示刷新，不自动重新提交。它无法补回 Dify 未保留的历史工具过程。

## 回归结果

| 检查 | 结果 |
| --- | --- |
| Python 3.12，`unittest discover -s pi_dify/tests` | 88 项通过 |
| 工作台 `npm run test` | 35 项通过 |
| `npm run build` | 通过 |
| `npm run check:static` | 0 violations |
| 修改的 Python 文件 Black / Ruff | 通过 |
| `git diff --check` | 通过 |
| amd64 解包后直接安装 `requirements.txt` | 仅使用包内 wheels 成功 |
| amd64 解包后的真实 SDK 注册 | 成功，包含策略与资源 |
| amd64 离线运行时冒烟 | `offline ok`，`completed`，1 次模型请求 |
| arm64 包 | 构建成功，72 个锁定依赖离线解析成功；未执行 |

SDK 测试进程退出时仍出现既有 gevent/logging 清理警告；测试断言和退出码均通过。

## 真实 Dify 1.15 验证

实例：`http://localhost:18081`，通过官方远程开发调试入口加载当前插件。
验证应用：`Pi v2 修复验证`，ID `2b083f02-2ca8-437e-bd44-d44f40e41c8c`。
模型：本地已配置的 DeepSeek provider，`deepseek-flash`。
应用图连接 Pi → 会话变量赋值 → Answer，将 Pi 输出的 `agent_state` 写回同名会话变量。

本次 DeepSeek provider 将 reasoning 包在 `<think>` 中，因此验证应用显式启用 `thinking_tags: true`。
工作台验证直接运行产品的 `DifyController` 和 transport，访问真实发布应用的服务 API，没有 mock 网络或模型。

| 场景 | 实际观察 |
| --- | --- |
| 普通对话与跨轮状态 | 第一轮记住测试口令，第二轮准确返回；会话变量可读回 |
| AskUser | 产生问卷后暂停；下一轮结构化答案恢复运行并回答 |
| 刷新恢复问卷 | 新控制器从历史和变量恢复待答问卷；提交“苏州”后完成，再刷新无待答状态 |
| Streamable HTTP MCP | 真实 MCP 1.26 FastMCP 服务完成发现与调用 |
| 写工具审批 | 批准前合成写入记录为 0；刷新恢复审批；批准一次后记录恰好 1 条 |
| MCP 业务错误 | `fail_demo` 返回 `isError`；卡片为 error，连续错误统计为 1；模型报告错误且不重试 |
| 停止 | 对话 POST 1 次、停止 POST 1 次；断流后显示 `unknown / stopped_unconfirmed`，没有自动重发或宣称已停止 |

另外使用内置浏览器实际操作构建后的工作台页面，经临时 loopback 同源代理连接上述真实 Dify 应用。代理仅用于联调，真实应用密钥留在代理进程中，未填入网页或静态资源。页面成功展示模型生成的三题 AskUser（单选、多选、文本）；空表提交提示必填；填写后提交，问卷变为已回答，模型收到结构化答案并完成汇总，输入框恢复可用。

页面截图：

- `screenshots/dify-live-ask-user.jpg`：问卷上半部分及等待回答状态。
- `screenshots/dify-live-ask-user-bottom.jpg`：多选、文本输入、取消与提交按钮。
- `screenshots/dify-live-ask-user-completed.jpg`：提交后的真实模型回答与完成状态。

工作台中间区域独立滚动，因此使用两张原始页面截图覆盖完整问卷。此次浏览器操作验证了 AskUser 点击链路；审批与刷新恢复的真实网络验证仍以控制层场景为依据。

MCP 使用临时本机服务和合成数据，没有业务写入。验证结束关闭临时 MCP 与插件调试进程；验证应用保留供查看配置。没有修改 Dify 的签名校验设置，没有把凭据写入仓库。

## 离线产物

均位于 `pi_dify/dist/`，为生成文件，不纳入 Git。每包包含 72 个相应架构的 wheels。

| 架构 | 包 | 字节 | SHA-256 |
| --- | --- | ---: | --- |
| amd64 | `pi_dify-0.1.0-offline-linux-amd64.difypkg` | 26,464,734 | `e428d208d3ec0d06c7ebea7645d42fe047ad83c4caaac8df3a9c287bbb6d6949` |
| arm64 | `pi_dify-0.1.0-offline-linux-arm64.difypkg` | 25,482,464 | `7dcad286da8ef3b154d2bc15c6ada6177552c3fb54736f9ed547bb21e387e734` |

## 尚未验证的边界

- 本机 Dify 开启强制签名校验，拒绝安装未签名的本地产物。因此这次证明了离线依赖闭包、包内 SDK 注册与真实 Dify 远程调试运行，**没有证明正式插件安装流程的完全断网安装**。发布前需走目标环境认可的签名安装流程。
- 没有 arm64 执行环境，没有 Dify 1.7 实机验证，也没有完成所有业务验收场景。
- 真实外部工具验证使用 MCP；Dify 注入工具与附件仍以现有 fake/契约测试为依据。
- 已进入的同步模型请求不承诺硬中断；未确认的外部副作用仍需业务核实。真实 provider 的上下文溢出、完整模型兼容矩阵和生产网络断连未在本次验证。
