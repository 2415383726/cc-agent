# core-lc/harness-lc 与官方 Pi：针对 Dify 的进一步核对

日期：2026-10-28。只读检查源码、PyPI 元数据和 GitHub API；没有安装、导入或执行候选包。为避免把 main 上的新功能算入发布版，本次主要核对 **0.6.0**。

## 判断

Python 路线已经具备可用的抽象边界，不能简单否定成“玩具 loop”；但它也没有把本项目最难的运行契约全部解决。使用它意味着采用一个独立演进的 Python harness，并继续拥有 Dify 的持久中断、预算和错误恢复实现；使用官方 Pi 则主要增加运行时打包和跨语言通信成本，仍需 Dify 持久中断和状态容量适配。

如果首要目的是直接继承官方成熟运行内核，倾向官方 Pi，前提是单 `.difypkg` 的自包含运行时和真实 Dify 环境验证通过。如果最小环境和 Python 内集成更重要，`core-lc + harness-lc` 是可信的验证候选；目前的证据不足以把它当成官方 Pi 的同等替代品。不能仅因它已有 session/compaction，就认为迁移后能删除原有全部恢复和预算逻辑。

## 发布版定位与上游继承证据

- GitHub `v0.6.0` 指向 `5f73e07964f14a7409f9d1b7f2b7188b06c1fc64`，PyPI 两包 0.6.0 均发布于 2026-10-25。本次将两个小型 wheel 下载到内存，用 PyPI 提供的 SHA256 核验后只读解压；核心 `agent_loop.py`/`types.py`、harness `agent_harness.py`/`session/session.py` 与该 tag **逐字相同**。这不是执行或安装包，也不是完整发布产物可复现性验证。[tags API](https://api.github.com/repos/zy1233/pi-python/tags?per_page=30)、[core 发布元数据](https://pypi.org/pypi/pi-agent-core-lc/0.6.0/json)、[harness 发布元数据](https://pypi.org/pypi/pi-agent-harness-lc/0.6.0/json)
- 发布设计说明的上游参照为 **“2026-07 main 分支”**。本次检查的设计、审计、源码树中，未找到能作为 0.6.0 整体兼容承诺的固定 upstream commit/tag，故精确基线记为 **unknown**，不能称其已跟随官方 1.4.0。[发布版 harness 设计](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/docs/specs/2026-07-03-phase3-agent-harness-design.md)
- 有源码模块对照、审计修复记录，以及事件顺序、并发工具、压缩、会话重放等实质测试。它们是项目自身测试；未找到发布时运行官方 Pi 与 Python 的统一差分运行器、保留的上游 trace 或完整上游测试映射。设计 §10 明确把 Pi v3 JSONL fixture 写为**手工按格式构造**，因此“读取 Pi 格式 fixture”不能扩大成已经互跑两套实际运行时验证。[设计与测试策略](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/docs/DESIGN.md)、[核心测试](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/tests/test_agent_loop.py)、[压缩测试](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/tests/test_harness_compaction.py)

## 真实 CI 与维护窗口

发布 SHA 的 CI run `40172668652` 已完成，Python **3.11、3.12、3.13** 三个 pytest job 均为 `success`；发布 run `40180264121` 的 `Pre-release tests` 也成功，工作流明确使用 Python 3.12。该命令默认排除 `real_llm`，因此证明的是这组离线/假模型等测试通过，不能扩大为真实模型或 Dify 验证。[CI jobs API](https://api.github.com/repos/zy1233/pi-python/actions/runs/40172668652/jobs?per_page=100)、[发布 jobs API](https://api.github.com/repos/zy1233/pi-python/actions/runs/40180264121/jobs?per_page=100)、[发布版 CI](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/.github/workflows/ci.yml)、[pytest 配置](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pyproject.toml)

这些 Python jobs 使用 `ubuntu-latest`，没有 Linux arm64 矩阵。本次未找到 Python 运行时在 Linux arm64 的实际测试证据。发布中的 macOS arm64 job 构建的是 **Rust TUI**，不能当作 Dify Linux arm64 已验证。纯 Python `py3-none-any` wheel 也不能替代全部依赖和宿主组合的验证。[发布工作流](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/.github/workflows/release.yml)

仓库创建于 2026-05-22；PyPI 从 2026-08-05 的 0.1.0 到 10-25 的 0.6.0，共六次发布，公开分发观察窗口约 12 周。PyPI 只有一个维护账户 `zhangy1233`，项目 author 为 `zy1233`；GitHub contributors 返回 `zy1233` 和 `cursoragent`，不能由此推断两个独立人类维护者。近期持续提交是积极证据，长期维护保障仍 unknown；不以 stars 评分。[仓库 API](https://api.github.com/repos/zy1233/pi-python)、[PyPI 维护者和历史](https://pypi.org/project/pi-agent-harness-lc/0.6.0/)、[贡献者 API](https://api.github.com/repos/zy1233/pi-python/contributors?per_page=100)

## Dify 难点：已有接口与仍需自己完成的工作

| 契约 | 0.6.0 实际行为 | 对迁移的影响 |
| --- | --- | --- |
| 模型和压缩使用 Dify Session | `AgentHarness` 注入 `stream_fn`；默认压缩也调用它 | 可以共用 Dify 模型 adapter，架构上不必引入第二套模型凭证或 LangChain Provider |
| 无本地执行环境 | `env=None` 为默认；测试直接以内存 Session、mock stream 构建并执行 harness，未传 env | 可不启用本地文件/shell工具；Skills资源与工具仍由宿主受控提供。不是必须安装 CLI、TUI 或启用 LocalExecutionEnv |
| 跨轮状态 | `SessionStorage` 是异步协议；`MemorySessionStorage(metadata, entries, leaf_id)` 可从外部数据构造；有 save-point 事件 | 可适配 `agent_state`，但它没有190KB限制、状态编码/裁剪、Dify写回结果契约 |
| 持久确认与用户提问 | tool hook 的 block 被转换成普通错误 tool result；进程内队列、`pending_session_writes` 只负责待写入消息/配置 | 未提供“保存操作参数→结束插件调用→重建后批准执行”协议；需自己实现。pending writes 不能等同于 pending interrupt |
| 一次 overflow 恢复 | 核心遇 `error/aborted` 立即结束；auto compact 在 turn_end 后执行，失败仅 warning 并跳过 | 未提供现有“识别溢出→压缩→重试一次→再失败结束”的合同；需要宿主恢复控制或扩展运行逻辑 |
| 完整请求预算 | `ContextBudget` 用上次 `usage.totalTokens` 或 `input+output`；自动压缩用最后成功 usage anchor 加后续消息估算 | 首次请求没有 usage；新system prompt、工具schema变化没有独立预估。不能替代完整请求预算和输出预留 |
| 执行和结果预算 | 已有 `max_turns` 与单工具 timeout；工具批次 `terminate` 只有所有结果均为 true 才停止后续模型轮次 | 未见本项目等价的跨普通/压缩/重试总预算、结果预算、重复调用防护或 unknown 写操作协调；终止一个结果也不等于阻止同批其他工具执行 |

上述模型、无 env 和持久化接口见[发布版 harness](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/agent_harness.py)、[无 env 的实际测试](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/tests/test_harness_agent.py)、[存储协议](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/types.py)、[内存存储构造](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/session/memory_storage.py)。

中断和运行行为见[核心循环](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py)。其 `_should_terminate_batch` 使用 `all(...)`；并行分支预先准备整批后创建 Tasks，不能依赖单个工具返回 terminate 来提供权限调度边界。

预算细节见[ContextBudget](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/types.py)和[压缩估算](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/packages/pi-agent-harness/pi_agent_harness/compaction/utils.py)。估算可以从旧 usage 间接涵盖旧请求的 system/schema，但**不包含对新请求这些部分的独立计数**。此外，harness 的 `_create_loop_config` 未接入 core 的 `before_llm_call`，只有消息 context hook；“核心留有 hook”不能直接推导 harness 已实现请求前压缩策略。

以上缺口是适配工作，不意味着一定需要 fork；应先设计公开 hook、注入 stream 和自定义工具是否能完整覆盖，再决定是否更改内核。官方 Pi 也没有现成 Dify 持久确认，但它自己的 AgentSession 层已包含更广的应用运行和恢复机制；采用社区包不能自动获得那些机制。

## LangChain 到底增加什么成本

它没有把执行循环交给 LangChain agents：实际 loop、工具调度、turn 和 Session 语义都在本项目源码中；自定义 Dify `stream_fn` 可以绕过 `langchain_stream`，因此并不必须经 LangChain 发模型请求。[发布版 loop](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/agent_loop.py)、[LangChain adapter](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/adapters/langchain_stream.py)

但 `langchain-core>=0.3.0` 是硬依赖，且不是只在类型检查时引用：顶层 `pi_agent_core.__init__` 导入 adapters，`langchain_convert` 和 tools adapter 实际导入 LangChain 消息/工具类型。即使使用 Dify adapter，正常安装和导入仍需这套包。harness 自身的21份 Python源码未直接导入 LangChain，核心需要它。[顶层导入](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/__init__.py)、[实际转换器导入](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pi_agent_core/adapters/langchain_convert.py)、[依赖声明](https://github.com/zy1233/pi-python/blob/5f73e07964f14a7409f9d1b7f2b7188b06c1fc64/pyproject.toml)

目前 `langchain-core` 最新元数据为 1.7.1，带 langsmith、langchain-protocol、jsonpatch、tenacity、uuid-utils、httpx、pydantic 等依赖。下限未设上界意味着未来重新解析可能带入另一版本；单包离线交付应锁定全树并检查目标架构 wheels。Dify SDK 0.7.4 也使用 pydantic/httpx/pyyaml 等。当前声明范围有交集，**本次没有证明存在必然冲突，也没有运行解析证明整个组合兼容**；成本是新增依赖及升级矩阵。[LangChain 元数据](https://pypi.org/pypi/langchain-core/json)、[Dify SDK 0.7.4 元数据](https://pypi.org/pypi/dify-plugin/0.7.4/json)、[当前项目锁文件](../../cc_agent/uv.lock)

另一个 Python 路线仍需实测的边界是：库基于 `asyncio`，Dify 当前 adapter 使用同步迭代的 `session.model.llm.invoke` 和同步工具调用，SDK 包含 gevent。直接在异步流函数中迭代同步响应可能阻塞取消和并行调度；如何接入事件循环、保持 Session 上下文、传输流片段以及退出后停止后台任务，需要正式运行环境验证。不能未经验证就把 Session 放入线程并假定线程安全。[当前模型 adapter](../../cc_agent/core/model_adapter.py)、[工具 adapter](../../cc_agent/core/tool_adapter.py)、[SDK 依赖](https://pypi.org/pypi/dify-plugin/0.7.4/json)

## 选型时应衡量的结果

Python 路线的确定收益是消除 Node交付和跨进程协议；它的代价是独立上游、额外依赖，以及我们继续承担部分 harness 语义。官方路线的确定收益是执行实际官方实现并直接接收上游修复；其单包运行时、平台与桥接可靠性目前仍须验证。

决定应基于相同业务验收下**能删除哪些旧运行代码、必须新增多少产品逻辑和运行交付工作**，不能只比较包大小或功能名称。首版全功能要求不变；内部验证需优先证明持久确认、一次 overflow 恢复、完整预算及真实 Dify 流式取消，而不是仅完成 Python mock聊天。
