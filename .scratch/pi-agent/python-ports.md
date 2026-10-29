# 社区 Python Pi 候选调查

访问日期：2026-10-28。只读检查官方仓库、项目源码、GitHub API、PyPI 元数据；未安装候选包，未执行其测试，也未验证 Dify 集成。下文“有实现/有测试”表示源码存在；仓库保留的通过记录属于作者提供的证据，不等于本项目复测通过。版本与活动日期以本次 API 返回为准，可能晚于搜索摘要。

## 结论

存在原生 Python 移植，也存在仍需 Node/Pi CLI 的 Python 包装器。没有证据表明这些社区移植由 Pi 官方维护，不能把上游 Pi 的成熟度直接赋予同名 Python 包。官方主仓当前递归源码树没有 `.py` 文件，发布单元为 npm/TypeScript 包；这说明当前官方实现的形态，不证明整个网络绝无其他官方实验。[官方仓库](https://github.com/earendil-works/pi)、[源码树 API](https://api.github.com/repos/earendil-works/pi/git/trees/main?recursive=1)

对本项目的建议是：若首要目标是继承官方运行内核与后续修复，优先验证把官方 Pi 运行时随一个 `.difypkg` 交付的可行性；若最小运行环境优先，原生 Python 候选值得比较，但需接受独立维护、功能缺口和行为差异。选择移植不是只把 JavaScript 换成 Python 的无损选择。

Python 候选中，`pi-agent-core-lc` **配合** `pi-agent-harness-lc` 更接近需要复用的完整 harness；`pi-python-core` 有较明确的固定版本差分证据和轻量宿主注入接口，但不是完整 `AgentSession`。两者适合作为进一步验证对象，不建议现在认定其中之一已满足全功能 Dify 产品契约。旧 `pi-agent-core`、`pi-mono-coding` 不作为此次首选；Python RPC 包装器不能解决额外 JavaScript 运行时问题。

## 候选与实际维护情况

| 候选 | 实现形态 | 当前发布 / 活动事实 | 本项目判断 |
| --- | --- | --- | --- |
| [`pi-agent-core`](https://pypi.org/project/pi-agent-core/) / Huvinesh | 原生 Python 核心循环移植；PyPI 维护账户 `huvinesh99` | PyPI `0.1.1`，2026-02-15；GitHub 最后 push 2026-02-16 | 小核心，有 loop/工具/事件/steering；不是完整 coding-agent harness |
| [`pi-mono-coding`](https://pypi.org/project/pi-mono-coding/) / Hephaestus | 原生 Python monorepo 的 coding 工具包 | PyPI `0.1.1`，2026-02-24；仓库最后 push 同日；包元数据标 Alpha | 不能由“coding”包名推断会话、压缩、Skills 已完整移植 |
| [`pi-agent-core-lc`](https://pypi.org/project/pi-agent-core-lc/) + [`pi-agent-harness-lc`](https://pypi.org/project/pi-agent-harness-lc/) / zy1233 | 原生 Python；模型默认边界采用 LangChain adapter | 两包均 `0.6.0`，2026-10-25；仓库最近提交 2026-10-28 | 实际包含 harness/session/compaction/resources，可直接注入 Dify 流函数；仍有硬依赖和适配成本 |
| [`pi-python-core`](https://pypi.org/project/pi-python-core/) / daidong | 原生 Python，固定参照 Pi `v1.0.0` | PyPI `0.11.0`，2026-10-19；最新源码修复提交 2026-10-22 | 有核心、hooks、插件/Skills及差分证据；完整会话管理和压缩产品层仍需应用实现 |
| [`pi-agent-core-py`](https://github.com/wesleyzhangwq/pi-agent-core-py) / wesleyzhangwq | 原生 Python，源码包含完整 harness 等模块 | 源码版本 `0.80.10`；最后 push 2026-07-17；本次同名 PyPI JSON 返回 404，GitHub releases 为空 | 覆盖范围值得参考；发布和持续跟随上游的证据不足 |
| [`pi-agent-python-sdk`](https://pypi.org/project/pi-agent-python-sdk/) / cheenulabs | Python RPC 包装器，启动 `pi --mode rpc` 子进程 | PyPI `0.2.6`，2026-10-23；仓库 push 2026-10-27 | 复用的是实际 Pi，但仍需交付 Node/Pi；没有消除跨语言 Dify 回调问题 |

发布与依赖来源：[core JSON](https://pypi.org/pypi/pi-agent-core/json)、[coding JSON](https://pypi.org/pypi/pi-mono-coding/json)、[core-lc JSON](https://pypi.org/pypi/pi-agent-core-lc/json)、[harness-lc JSON](https://pypi.org/pypi/pi-agent-harness-lc/json)、[python-core JSON](https://pypi.org/pypi/pi-python-core/json)、[wrapper JSON](https://pypi.org/pypi/pi-agent-python-sdk/json)。活动来源：[Huvinesh API](https://api.github.com/repos/Huvinesh-Rajendran-12/pi-agent-core)、[Hephaestus API](https://api.github.com/repos/Hephaestus-Automation/pi-mono-py)、[zy1233 提交](https://api.github.com/repos/zy1233/pi-python/commits?per_page=2)、[daidong 提交](https://api.github.com/repos/daidong/pi-agent-core-python/commits?per_page=2)、[wesley API](https://api.github.com/repos/wesleyzhangwq/pi-agent-core-py)、[wrapper API](https://api.github.com/repos/cheenulabs/pi-agent-python-sdk)。`pushed_at` 不等于最后业务修复日期，也不证明生产成熟度；本调查不以 stars 排名。

## 更接近完整 harness：core-lc + harness-lc

源码中的 `AgentHarness` 显式接收 `session`、`model`、`stream_fn`、`tools`、`resources`、`compaction` 等参数，`env` 可选。普通模型请求调用注入的 `stream_fn`；默认压缩和分支摘要也使用这个函数。因此可以写 Dify adapter 直连当前 Python Session，不必调用 LangChain 模型实现。[构造和运行实现](https://github.com/zy1233/pi-python/blob/9cdd8fc55ea48a42b03684e9f628beb1cbaa920f/packages/pi-agent-harness/pi_agent_harness/agent_harness.py)

实际存在 `SessionStorage` 协议、内存/JSONL 会话树、资源快照、hooks、save-point、Skills 和模板。测试目录包含会话、压缩、生命周期、扩展状态以及 Pi v3 会话 fixtures。硬依赖仍包括 `langchain-core`、`pydantic`；harness 增加 `pathspec`、`pyyaml`，不是“完全不带 LangChain”。[harness 类型与存储协议](https://github.com/zy1233/pi-python/blob/9cdd8fc55ea48a42b03684e9f628beb1cbaa920f/packages/pi-agent-harness/pi_agent_harness/types.py)、[harness 测试](https://github.com/zy1233/pi-python/tree/9cdd8fc55ea48a42b03684e9f628beb1cbaa920f/packages/pi-agent-harness/tests)、[PyPI 依赖](https://pypi.org/pypi/pi-agent-harness-lc/json)

这是候选中范围较贴合的原生 Python 路线，但未核实完整上游 API 差分或全部上游回归测试通过，也未发现已经验证的 Dify 适配。README 的 Stable 是项目自己的分类；PyPI 元数据仍标 Beta。实际 Dify 暂停/下一轮恢复、状态容量、附件和 AG-UI 契约均 unknown，不能由已有 JSONL 存储和 hooks 自动推导。[项目声明](https://github.com/zy1233/pi-python)

## 更轻的核心：pi-python-core

`Provider` 协议的调用面是 `stream(request, cancel) -> AsyncIterator[ModelEvent]`；`FunctionProvider` 可包装用户函数。`ModelRequest` 包含消息、工具声明、模型和 options。因此 Dify 调用可直接实现此协议，无须使用库内 Anthropic/OpenAI 连接器，也无须 Node。基础依赖是 httpx、jsonschema、websockets，后者即使不使用内置模型传输仍是包硬依赖。[Provider 源码](https://github.com/daidong/pi-agent-core-python/blob/804c79b2a4215d0ba95bf23cb7e6b1dc2f7e45c9/src/pi_python/provider.py)、[PyPI 依赖](https://pypi.org/pypi/pi-python-core/json)

它并非只有早期 loop：已有工具 schema、流式事件、steering/follow-up、取消、运行预算、前后工具钩子、上下文变换；插件模块可组合 Skills、模板、工具和 hooks。插件代码需要 Python `setup(api)`，不能原样执行 Pi 的 TypeScript extensions；Markdown 技能有复用价值。受限 `read_skill` 只允许读取技能目录，和本项目现有边界接近。[插件文档](https://github.com/daidong/pi-agent-core-python/blob/804c79b2a4215d0ba95bf23cb7e6b1dc2f7e45c9/docs/PLUGINS.md)、[API](https://github.com/daidong/pi-agent-core-python/blob/804c79b2a4215d0ba95bf23cb7e6b1dc2f7e45c9/docs/API.md)

但它不是完整 Pi coding-agent 的可替换实现：保存/恢复示例只编码、解码消息，应用选择存储位置；`recovery.py` 提供 overflow/retry 判断等 helpers，示例里的 `Compactor` 和恢复循环由应用编写。示例还明确保留完整历史，压缩仅改变送模上下文。因此树状 session/正式压缩记录、自动生命周期、Dify 容量控制和待操作持久化仍需要自己维护。[保存恢复示例](https://github.com/daidong/pi-agent-core-python/blob/804c79b2a4215d0ba95bf23cb7e6b1dc2f7e45c9/examples/save_restore.py)、[压缩恢复示例](https://github.com/daidong/pi-agent-core-python/blob/804c79b2a4215d0ba95bf23cb7e6b1dc2f7e45c9/examples/recovery.py)

可审查的证据比单纯“忠实移植”声明具体：固定参照 `v1.0.0` / `a13d35a742c6ef8462812a28fbe1d8c8b7431c32`，有共享 JSON fixtures、保存的实际 upstream trace，以及 Python 测试将运行结果与 trace 比较。作者明确限制兼容声明，并列出输入校验、预算、取消/unknown、状态复制等有意差异；后续 Skills/template 差分另有记录。项目没有宣称所有 Pi API兼容，固定参照也没有随本地官方 `1.4.0` 自动升级。[accepted baseline](https://github.com/daidong/pi-agent-core-python/blob/804c79b2a4215d0ba95bf23cb7e6b1dc2f7e45c9/compat/baseline.json)、[差分测试](https://github.com/daidong/pi-agent-core-python/blob/804c79b2a4215d0ba95bf23cb7e6b1dc2f7e45c9/tests/test_conformance.py)、[覆盖及已知差异](https://github.com/daidong/pi-agent-core-python/blob/804c79b2a4215d0ba95bf23cb7e6b1dc2f7e45c9/compat/COVERAGE.md)

这适合“Python 内核 + 自己维护应用 harness”；对“直接继承官方成熟 harness，减少手搓会话与压缩”的目标，收益需要谨慎核算。项目创建于 2026-10-03，观察时间较短；未复测其 fixtures 或生产稳定性。[仓库 API](https://api.github.com/repos/daidong/pi-agent-core-python)

## 其余候选的具体边界

- **Huvinesh `pi-agent-core`**：源码树共 20 个文件，有 `agent.py`、`agent_loop.py`、`types.py`、proxy 和三份测试文件；提供自定义 `StreamFn`、工具执行、事件、队列。未见 SessionManager、compaction、Skills 或完整扩展运行器。这是可以接 Dify 的基础 loop，但拿它替换后仍要维护大量上层逻辑。[README](https://github.com/Huvinesh-Rajendran-12/pi-agent-core)、[源码树](https://api.github.com/repos/Huvinesh-Rajendran-12/pi-agent-core/git/trees/main?recursive=1)
- **Hephaestus `pi-mono-py` / `pi-mono-coding`**：`packages/pi_coding/pyproject.toml` 的包名和版本与 PyPI 相符，能建立归属关系。实际源码有 ai/agent/coding/tui 和测试；coding 包主要提供文件、shell、编辑等工具，未见专门 session/compaction/Skills 模块。默认本地工具也不能直接带入本项目的 Dify 边界。[包元数据](https://github.com/Hephaestus-Automation/pi-mono-py/blob/811daf98eeb119e7a3b5504240870aebd5f2980a/packages/pi_coding/pyproject.toml)、[源码树](https://api.github.com/repos/Hephaestus-Automation/pi-mono-py/git/trees/main?recursive=1)
- **同名项目不可混用**：`Rudreysh/pi-mono-py` 是另一个 Python 仓库，有更广的 coding-agent、harness/session/compaction 和测试源码；不等于上面的 PyPI `pi-mono-coding`。本轮未验证其发布与上游差分，不能将两者信息拼成一个“成熟 Python Pi”。[Rudreysh README](https://github.com/Rudreysh/pi-mono-py)、[其源码树](https://api.github.com/repos/Rudreysh/pi-mono-py/git/trees/main?recursive=1)
- **wesley `pi-agent-core-py`**：源码确有 AgentHarness、Session、内存/JSONL repository、compaction、Skills、模板、hooks 和对应测试，不是仅 loop。声明对齐 upstream `0.80.10` / `3da591ab74ab9ab407e72ed882600b2c851fae21`。模型由注入流函数或模型对象提供，无强制模型 SDK；依赖为 httpx/jsonschema/pathspec/PyYAML。轻量且边界清楚，但未发现正式发布和近期持续同步证据。必须先自行验证其兼容测试与 Dify 契约。[PARITY](https://github.com/wesleyzhangwq/pi-agent-core-py/blob/a2517400ec34da38b6e65ded602e0ebe63bbcb2b/PARITY.md)、[pyproject](https://github.com/wesleyzhangwq/pi-agent-core-py/blob/a2517400ec34da38b6e65ded602e0ebe63bbcb2b/pyproject.toml)、[测试](https://github.com/wesleyzhangwq/pi-agent-core-py/tree/a2517400ec34da38b6e65ded602e0ebe63bbcb2b/tests)、[releases API](https://api.github.com/repos/wesleyzhangwq/pi-agent-core-py/releases)
- **cheenulabs Python SDK**：README 明确要求已安装且配置好的 Pi CLI，每个 Client 启动 Pi 子进程，底层使用已有 JSONL RPC；Python 分发没有 runtime dependencies 不代表无需 JavaScript 运行时。会话、压缩等能力来自真实 Pi CLI。它可作为宿主通信参考，但并未提供 Dify 的模型/工具反向调用和跨进程持久确认。[README](https://github.com/cheenulabs/pi-agent-python-sdk)

## 对首版全功能与单包交付的影响

单个 Python 包只需加入插件依赖并不代表完整方案已成立。无论选哪条路线，仍须验收：Dify 当前会话模型流和用量、工具与产物去重、运行隔离和 headers、不执行内置本地 shell/stdio MCP、AG-UI/Dify 双输出、Tasks/Skills、跨轮授权后的策略重检、unknown 写操作及约 190KB `agent_state` 下的可靠恢复。

原生 Python 能消除 Node/子进程桥接和平台二进制交付，但无法消除这些产品适配工作。只采用小核心尤其可能把原来想删除的会话、压缩、恢复逻辑重新写一遍。相反，完整 harness 也不能直接把进程内等待当作跨调用持久暂停。

建议先以相同的全功能验收清单比较“官方 Pi 随包交付”和“Python core/harness-lc”两条路线；daidong 可作为较轻核心及差分方法的备选参考。后续实现可以内部逐项验证，首个对外交付仍按已确认的全部当前功能验收，不缩减为单轮聊天原型。本文记录选型证据，尚未选择依赖或批准实现。
