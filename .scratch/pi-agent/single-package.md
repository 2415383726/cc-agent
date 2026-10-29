# Pi Worker 的单 `.difypkg` 交付调查

调查日期：2026-10-28。范围：只安装一个插件包，不要求用户预装 Node/Bun，不增加常驻服务。用户已补充：**必须完全离线，runtime 和所有依赖随包；生产 arm64，测试 amd64**。本文是源码和官方文档调查；**没有安装、下载大二进制、编译或运行 Worker，也没有在 Dify 中验收**。尺寸表记录官方 HTTP HEAD、PyPI JSON 元数据与现有本地 wheels 的只读统计，不代表最终产物大小。

## 当前判断

单包交付与使用官方 TypeScript Pi 并不冲突。可以继续保留 Python Dify 插件入口，把受版本和校验和约束的 JavaScript 运行时及预构建 SDK Worker 一起交付。Python 宿主启动子进程，使用私有双向消息通道，让 Pi 请求本次 Dify session 的模型和工具调用。用户无需另装 Node/Bun，也无需部署独立服务。

最值得验证的两个候选是：

1. **官方 Node 最小 runtime 压缩资源 + 预构建 Worker bundle**。优点是与 Pi 的 Node 支持契约最接近；Node 无需作为系统依赖安装。初步部署可行性依据较直接。
2. **Bun 编译的自包含 SDK Worker**。Pi 已有 Bun 二进制构建，但自定义 Worker 的打包、动态资源、扩展和恢复流程尚未验证；不能直接把 CLI 编译成功外推为 SDK Worker 全功能验证成功，也不能假定尺寸更小。

结合完全离线和生产/测试架构要求，**当前优先候选为分别交付 arm64 与 amd64 `.difypkg`，每个包内含官方 Node 压缩 runtime、预构建 Pi SDK Worker 和该架构全部 Python wheels；每个环境只安装一个对应包**。Bun 作为对照候选，并非必须采用。这两个候选都要实际打包和在目标 Dify 环境验收，不能承诺最终包一定符合 50 MiB 或一定可安装。Node SEA 是额外候选，Python 嵌入 QuickJS 则不能直接运行完整 Pi SDK。

## 1. 已确认的 Pi 构建条件

本地 [coding-agent/package.json](/home/ygao/Desktop/work/cadre-system/cc_agent/pi/packages/coding-agent/package.json) 标识 `@earendil-works/pi-coding-agent` **1.4.0**、ESM、`engines.node >=22.19.0`；它导出 SDK 与 RPC entry。

`build:binary` 使用 `bun build --compile`，并显式传入图片处理、Codemode 的 Worker entry。官方 [build-binaries.sh](/home/ygao/Desktop/work/cadre-system/cc_agent/pi/scripts/build-binaries.sh) 包含 Linux x64/arm64 等架构，并复制 WASM、文档和终端 native helpers。这证实上游采用过 Bun 交付方式；同时说明完整 CLI 包含额外资源，不能直接视作最小 Dify Worker。[官方构建脚本](https://github.com/earendil-works/pi/blob/main/scripts/build-binaries.sh)

[build-coding-agent-bundle.mjs](/home/ygao/Desktop/work/cadre-system/cc_agent/pi/scripts/build-coding-agent-bundle.mjs) 用 esbuild 构建 Node bundle，对动态 OAuth/Bedrock、图片 Worker 等另外生成入口，保留部分 external 依赖。**“有 bundle”不等于任意 SDK 用法都只有一个零依赖 JS 文件。** 我们应只保留 Dify 需要的入口，并对所选功能逐一检查动态 import、native/WASM、资源路径和扩展加载。

版本注意：以上本地源码是调查对象，网络 main 是可变参考。生产构建需要固定上游 commit/package 版本和锁文件，本文没有确认本地快照对应的 Git 历史，也没有建议把示例 Node 22.19.0 作为最终生产版本。

## 2. Dify 1.15.0 的包限制不是统一的 50 MiB

| 层级与版本 | 源码行为 | 对单包交付的影响 |
| --- | --- | --- |
| Dify API 1.15.0 `PluginConfig` | `PLUGIN_MAX_PACKAGE_SIZE` 默认 **15,728,640 bytes / 15 MiB** | 不能假设所有部署都是 50 MiB |
| Dify 1.15.0 官方 Compose | 对 API/worker 设置 `PLUGIN_MAX_PACKAGE_SIZE=${PLUGIN_MAX_PACKAGE_SIZE:-52428800}`；daemon 也获得对应 `MAX_PLUGIN_PACKAGE_SIZE` | 此部署模板默认 50 MiB，可被环境覆盖；不是云端或定制部署承诺 |
| Dify API 插件上传接口 | `_read_upload_content(file, dify_config.PLUGIN_MAX_PACKAGE_SIZE)` | 上传文件本身有大小检查 |
| daemon 0.6.3 上传 controller | 比较 `difyPkgFileHeader.Size` 与 `app.MaxPluginPackageSize` | daemon 也独立检查上传文件大小 |
| daemon 0.6.3 CLI packager | `Pack(maxSize)` 累加每个文件内容长度，CLI `--max-size` 默认 50 MiB | 官方打包器检查外层包内各 entry 的未压缩总大小 |
| daemon 0.6.3 `UploadPluginPkg` → ZIP decoder | 明确调用 `NewZipPluginDecoderWithSizeLimit(pluginFile, config.MaxPluginPackageSize)`，累加 `UncompressedSize64` | 常规插件包上传同时检查外层 entry 未压缩总量；其他安装入口仍需分别核对 |

来源：[API 配置 1.15.0](https://github.com/langgenius/dify/blob/1.15.0/api/configs/feature/__init__.py)、[API 上传实现 1.15.0](https://github.com/langgenius/dify/blob/1.15.0/api/controllers/console/workspace/plugin.py)、[Compose 1.15.0](https://github.com/langgenius/dify/blob/1.15.0/docker/docker-compose.yaml)、[daemon 上传 controller 0.6.3](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.3/internal/server/controllers/plugins.go)、[daemon CLI 0.6.3](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.3/cmd/commandline/plugin.go)、[packager 0.6.3](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.3/pkg/plugin_packager/packager/packager.go)、[ZIP decoder 0.6.3](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.3/pkg/plugin_packager/decoder/zip.go)。1.15.0 Compose 指定 daemon 镜像为 `0.6.3-local`，因此此处使用 daemon `0.6.3` tag 对照，未将 main 行为当成旧版行为。

`PLUGIN_MAX_BUNDLE_SIZE` 是多个插件的 bundle 概念，不会自动增大单 `.difypkg` 的限制；`PLUGIN_MAX_FILE_SIZE` 在 API 1.15.0 注释为插件生成文件上限，也不是上传插件包限制。反向代理、部署平台、Marketplace 的额外要求仍需查询实际目标，本文不推定云端政策。

常规上传与 decoder 的连接已核对 [plugin_decoder.go 0.6.3](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.3/internal/service/plugin_decoder.go)：`UploadPluginPkg` 实际调用了上述未压缩大小 helper，因此这个入口的限制不是仅检查上传文件大小。

## 3. 官方 Node runtime + bundle

建议验证的具体包装是：

```text
pi-agent.difypkg
  main.py / Python Dify adapter
  worker/worker.mjs + 确需的静态资源
  runtime/node-linux-<arch>.tar.xz
  wheels/（若要求离线安装 Python 依赖）
  LICENSE / notices / checksums
```

构建端下载并校验官方 Node 发行资源，制作只保留 `node` 和必要 license/notices 的固定压缩包；预先 bundle Worker，运行端不执行 npm install。Python 启动时用标准库 `lzma`/`tarfile` 解包、校验、设可执行权限，再启动指定 Node 与固定 Worker。应采用限制成员路径和数量/总大小的解包实现、私有版本目录、并发锁和原子替换。runtime 是实现依赖，**不会暴露成 Agent 的任意 shell 或本地文件工具**。

外层 ZIP entry 是 `.tar.xz` 时，源码中的 entry 长度计算看到的是此压缩资源的字节数，不会自动递归计算其内部运行时大小。将运行资源作为压缩资源交付是可行候选；部署方仍需接受并审计真实解包后体积、可执行文件、磁盘与启动成本。不能以压缩尺寸替代实际资源预算。

仅以可追溯的 **Node 22.19.0 官方全量 `.tar.xz`** 为尺寸参照，2026-10-28 HEAD 得到：

| 官方资源 | HTTP Content-Length |
| --- | ---: |
| [Linux x64 archive](https://nodejs.org/dist/v22.19.0/node-v22.19.0-linux-x64.tar.xz) | 30,479,988 bytes（约 29.07 MiB） |
| [Linux arm64 archive](https://nodejs.org/dist/v22.19.0/node-v22.19.0-linux-arm64.tar.xz) | 29,167,588 bytes（约 27.82 MiB） |

这是原始发行 archive 的尺寸，不是“只保留 Node 后”的尺寸，也没有包含 Worker 或 Python wheels。两者合计 59,647,576 bytes，已高于 50 MiB，因此**不能直接推定双架构合包能装下**。按用户生产 arm64、测试 amd64 的条件，当前建议提供按架构构建的包，每个环境只安装一个符合其架构的包。如果最终必须同一个文件兼容两种架构，需要另做完整体积预算。

主线程于同日只读统计现有 `cc_agent/wheels/`，按现有 builder 架构筛选规则得到 amd64 55 个 wheels 共 **17.49 MiB**，arm64 54 个 wheels 共 **16.40 MiB**；现有 0.0.4 双架构包约为 ZIP 文件 **30.45 MiB**、外层 entry 未压缩总量 **31.61 MiB**。将当前分架构 wheels 与上述全量 Node archive 相加，量级约为 amd64 **46.56 MiB**、arm64 **44.22 MiB**，**尚未计入 Worker、资源与 Python 源码**。这是预算参照，并非新包测量；后续只保留 Node 必要发行文件与核实 Python 最小依赖可能降低体积，但完全离线条件下不能以运行时下载补齐依赖，也不能在未构建前承诺 fit。

Node 22.19.0 官方 Linux x64/arm64 的平台条件是 kernel >=4.18、glibc >=2.28；官方构建说明还有对应 libstdc++ 要求。[Node 22.19.0 BUILDING.md](https://github.com/nodejs/node/blob/v22.19.0/BUILDING.md) Dify daemon 0.6.3 local Dockerfile 以 Ubuntu 24.04 为运行基础，并安装 Python 3.12，理论上符合此 libc 基线；此为源码推断，仍需在实际镜像、CPU/架构和挂载参数下执行验证。[daemon local Dockerfile](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.3/docker/local.dockerfile)

## 4. Bun standalone Worker

Bun 的 `build --compile` 会把 JS/TS 和运行时合在一个可执行文件中，部署端无需安装 Bun。支持 glibc/musl Linux x64/arm64 等 target；涉及 Worker 时需显式提供入口，涉及资源时需正确嵌入。[官方 executable 文档](https://bun.com/docs/bundler/executables)

它的优势是可执行入口与 Worker 代码一起交付，构建端使用 Bun 即可，和 Pi 现有二进制构建方向一致。但 `--minify` 主要压缩应用代码，**并没有证据保证编译后的运行时很小**。Bun 当前文档新增 `--trim`/AOT 尺寸优化，但明确为 experimental；文档中的示例数字属于示例服务器，不能外推 Pi 的动态加载、扩展和 session 功能。[官方 smaller executables](https://bun.com/docs/compiler/size)

当前 Bun 安装源码说明 glibc >=2.17，x64 要求 SSE4.2；target 与兼容性须按最终固定 Bun 版本检查，而不是照抄历史 baseline 名称。[Bun installation 源码](https://github.com/oven-sh/bun/blob/main/docs/installation.mdx) 为控制范围，首个验证应走普通稳定 `build --compile`，实验性裁剪只作为后续对照。编译结果也可作为压缩资源交付并由 Python 解包，但同样要测量压缩、解包、RSS、启动时长及产物完整性。

## 5. Node SEA

Node SEA 是官方的单可执行文件分发机制，部署端可没有预装 Node。但它仍把 Node runtime 带进产物，并不会因变成一个文件而自动降低体积。

版本区别很重要：Node **22.19.0** 的 SEA 文档标记 Active development，只支持单一嵌入 CommonJS script，注入脚本的 `require()` 默认只能加载内建模块，需要 bundle/处理外部资源；生成 blob 与注入目标需要同一 Node 版本。[Node 22.19.0 SEA](https://nodejs.org/download/release/v22.19.0/docs/api/single-executable-applications.html) 当前 **26.x** 文档已提供更丰富的 ESM/VFS/CLI build 能力，不能据此认定 22.x 也具备同样能力。[当前 Node SEA 文档](https://nodejs.org/api/single-executable-applications.html)

与官方 Node runtime + bundle 相比，SEA 增加了一条构建/注入/资源加载路径；目前没有验证其能带来足够收益，不宜仅为“单文件”而优先采用。

## 6. Python 嵌入 QuickJS

QuickJS 是 JavaScript 引擎，不是完整 Node 环境。即使 Python 包能求值 JS、执行 Promise job，也不会自动提供 Pi 使用的 `node:fs`、路径、Node streams、Worker、crypto 与 npm package loader。

本地完整 SDK 会话代码直接导入了这些环境能力，例如 [agent-session.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/pi/packages/coding-agent/src/core/agent-session.ts)、[session-manager.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/pi/packages/coding-agent/src/core/session-manager.ts) 和 [resource-loader.ts](/home/ygao/Desktop/work/cadre-system/cc_agent/pi/packages/coding-agent/src/core/resource-loader.ts)。只抽取兼容 JS 的 agent-core 子集可能另有研究空间，但要获得完整 AgentSession/资源与扩展能力，需要大量 shim/重写，偏离“尽量复用上游完整运行机制”的目标。

原始 Python `quickjs` wrapper 项目目前已归档，自述缺乏维护；这不代表所有 QuickJS Python bindings 均停止维护，但足以说明不能把 `pip install quickjs` 当成零成本运行官方 Pi 的解决办法。[QuickJS 官方引擎文档](https://bellard.org/quickjs/quickjs.html)、[PetterS/quickjs](https://github.com/PetterS/quickjs)

## 7. `nodejs-wheel-binaries` 与现有 offline wheels

社区 [njzjz/nodejs-wheel](https://github.com/njzjz/nodejs-wheel) 提供非 Node 官方发行的 Node wheels；调查时仓库未归档，最近 push 为 2026-10-26。`nodejs-wheel` 只增添 CLI 入口包装，并依赖 `nodejs-wheel-binaries`；只做 Python 宿主启动可只使用 binaries。它提供 Python API/`python -m nodejs_wheel`，可与现有 offline wheels 流程结合。[PyPI binaries 元数据](https://pypi.org/pypi/nodejs-wheel-binaries/json)、[PyPI wrapper 元数据](https://pypi.org/pypi/nodejs-wheel/json)

但 wheels 方案**不等于小包**。只读取 JSON 的结果如下：

| 版本与 wheel | 标签所示 libc 基线 | PyPI 文件大小 |
| --- | --- | ---: |
| 24.19.0 Linux x64 | manylinux_2_28 | 61,123,607 bytes |
| 24.19.0 Linux arm64 | manylinux_2_28 | 60,588,256 bytes |
| 22.19.0 Linux x64 | manylinux_2_17 / manylinux2014 | 58,368,815 bytes |
| 22.19.0 Linux arm64 | manylinux_2_17 / manylinux2014 | 57,841,528 bytes |

来源：[24.19.0 JSON](https://pypi.org/pypi/nodejs-wheel-binaries/24.19.0/json)、[22.19.0 JSON](https://pypi.org/pypi/nodejs-wheel-binaries/22.19.0/json)。这里依据具体文件名标注平台条件，**不把旧 README 的 glibc 2.17 泛化到新版本**；社区构建的较低 libc 基线也不能套到 Node 官方二进制。

上述单架构 wheels 本身就超过 50 MiB；若必须将它装进插件，默认 50 MiB 预算下已不合适，即使它适配现有 pip/offline wheels 工具链。它属于可研究的运维便利路线，不宜未经验证成为唯一方案。若采用，至少固定版本、wheel 文件、平台标签与 SHA256，审查其构建与维护来源，并纳入真实环境安装/可执行权限检查；不能把 PyPI 包当作 Node 官方发行。现有 [offline package builder](/home/ygao/Desktop/work/cadre-system/cc_agent/cc_agent/scripts/build_offline_package.py) 已支持按架构筛选 wheels，可以复用思路，但本文未修改或运行它。

## 8. 安装、执行与生命周期的具体验证项

daemon 0.6.3 `ExtractTo` 将文件一律以 **0644** 写盘；不能依赖本地 ZIP 可执行位在安装后仍生效。直接附带的 Node/Bun 二进制需要 Python bootstrap 明确设定权限；wheel 则依赖安装器展开后的权限处理，也要实测。[ZIP decoder 源码](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.3/pkg/plugin_packager/decoder/zip.go)

daemon local runner 只为 manifest 的 Python 语言构建入口命令，执行 `python -m <entrypoint>`。Node Worker 应由该 Python 入口管理，不能简单把 manifest 改成 JavaScript。[subprocess.go](https://github.com/langgenius/dify-plugin-daemon/blob/0.6.3/internal/core/local_runtime/subprocess.go) 源码提供了原生进程运行的环境基础，但不构成云端、serverless、企业安全策略允许任意附带二进制的承诺。

验证清单：

- 实际目标 Dify/daemon 版本、部署类型、API 与 daemon 和反向代理限制；包内未压缩总量、上传压缩量、runtime 真正解包大小、Python wheels 全量与 RSS。
- Linux amd64/arm64 的实际执行、libc/libstdc++、CPU 与 `noexec` 挂载；单架构分别交付还是一个双架构文件。
- 无 Node/npm/Bun 全局安装、无外网的干净 daemon 中安装并启动；stderr/stdout 与插件官方协议分离。
- 每次运行的双向调用 ID、取消、超时、子进程退出、宿主结束清理、同一实例并发、异常与日志中不泄漏 session secret。
- 用 Dify 实际模型流、Dify 工具与附件完成闭环；确认后结束当前调用并在下一次从 `agent_state` 恢复；完整功能矩阵保持一致。
- Pi SDK 所需动态模块、WASM/二级 Worker/扩展资源确实在包里；不得依赖运行时联网补依赖。

只有这些验证通过，才可以将“单包内含运行时”从可行候选升级为确定交付方案。任何路线都不因跨语言桥接成功而自动满足状态、中断和完整功能契约。
