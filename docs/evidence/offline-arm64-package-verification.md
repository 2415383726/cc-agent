# 真·离线 ARM64 插件包构建与验证证据

Date: 2026-11-18。目标:为物理隔离内网生产环境提供 `cc_agent` 与 `pi_strategy`
的 ARM64 离线包,保证**安装期与运行期都不访问任何外网**。

## 背景:之前"不真离线"的根因

dify-plugin-daemon(本地栈 0.1.2,与 Dify 1.5.0 compose 配套)安装本地
`.difypkg` 的固定流程(`internal/core/plugin_manager/local_runtime/environment_python.go`):

1. 在解包目录执行 `uv venv .venv --python 3.12`;
2. 执行 `uv pip install [-i $PIP_MIRROR_URL] -r requirements.txt`。

daemon **只读包内 `requirements.txt`**,不使用 pyproject.toml / uv.lock。
旧 cc_agent 构建脚本只打包了裸的 requirements.txt(无 `--no-index`),因此
`uv pip install` 直连 PyPI/镜像源——有网时装得上但不离线,物理隔离内网直接失败。
用户导入的 `cc_agent-0.0.4-offline-linux-amd64-arm64.difypkg(.zip)` 已解包确认。

次要运行期风险:`dify_plugin` 的 `recalc_llm_max_tokens` 路径调用
`tiktoken.encoding_for_model("gpt2")`,tiktoken 0.8.0 首次调用会从
`openaipublic.blob.core.windows.net` 下载 vocab/encoder。本次一并消除。

## 修复内容

| 修复 | 说明 |
| --- | --- |
| `cc_agent/scripts/build_offline_package.py` | 打包时把 requirements.txt 重写为 `--no-index` + `--find-links ./wheels` + 锁文件(与 pi_strategy 对齐),并生成 `VERSION_MANIFEST.json` / `THIRD_PARTY_NOTICES.md` / `LICENSES/` |
| `cc_agent/manifest.yaml`、`pyproject.toml` | 版本 0.0.4 → 0.0.5(0.0.4 的包已证实是坏的),meta.version 对齐 0.0.5 |
| `cc_agent/main.py`、`pi_strategy/main.py` | 进程启动即 `os.environ.setdefault("TIKTOKEN_CACHE_DIR", <pkg>/_assets/tiktoken_cache)`(tiktoken 在调用时才读该环境变量) |
| `cc_agent/_assets/tiktoken_cache/`、`pi_strategy/_assets/tiktoken_cache/` | gpt2 `vocab.bpe`(sha256 `1ce16647…`)+ `encoder.json`(sha256 `19613966…`),与 tiktoken 0.8.0 源码钉住的哈希一致;缓存文件名 = URL 的 sha1 |
| `README.md` / `pi_strategy/README.md` | 打包说明补充 --no-index 重写与 tiktoken 缓存 |

daemon 若在环境里配置了 `PIP_MIRROR_URL`,命令行为 `uv pip install -i <mirror> -r
requirements.txt`;requirements 文件内的指令在命令行之后解析,`--no-index` 仍然
生效——安装只可能来自包内 wheels。

## 产物(交付物)

| 文件 | bytes | sha256 |
| --- | --- | --- |
| `cc_agent/dist/cc_agent-0.0.5-offline-linux-arm64.difypkg` | 17,851,300 | `1a03dcca15506a7a16286422c2e4082bd169abf5f158b4e6cdaa4d4f21bcc29a` |
| `pi_strategy/dist/pi_strategy-0.1.0-offline-linux-arm64.difypkg` | 26,064,260 | `27106ae710235af134cdf32e24e812c4c5284eb7d874ee05977ba1999502039c` |

包内审计:requirements.txt 前两行为 `--no-index` / `--find-links ./wheels`;
wheels 全部为 `py3-none-any` 或 `*aarch64*`;两插件均含 tiktoken 缓存 2 文件;
VERSION_MANIFEST architecture=arm64(cc_agent 54 wheels / pi_strategy 72 wheels)。
dist/ 中旧的 `cc_agent-0.0.2/0.0.3/0.0.4` 包**不可用于离线安装**,勿再使用。

## 验证

**回归**:`pi_strategy/tests` 151 passed;`cc_agent/tests` 248 passed。
构建期:cc_agent 构建脚本内置的 `pip download --no-index`(arm64 平台)与
pi_strategy `verify_offline_package.py --arch arm64 --resolve-only` 均通过
(72 包 aarch64 解析成功)。

**验证 A —— daemon 容器断网安装(与本机 Dify 同一容器,uv 0.7.12 / Python 3.12.3)**:
容器内 `/etc/hosts` 把 `pypi.org`、`files.pythonhosted.org`、`astral.sh` 指向
127.0.0.1(curl 验证拉黑生效)。解包两个 amd64 测试包,执行 daemon 原命安装:

- cc_agent:53/53 依赖全部装上;43 个插件模块导入冒烟通过;tiktoken gpt2 离线编码通过。
- pi_strategy:72/72 依赖全部装上;`offline_smoke.py` 完整 Pi 回合
  `{"answer":"offline ok","terminal_status":"completed"}`;tiktoken 离线通过。

**验证 B —— 真 daemon 安装链路断网复测**:上传/安装接口
(`/plugin/<tenant>/management/install/upload/package` + `/install/identifiers`,
X-Api-Key 认证),以改名测试插件 `pi_strategy_ot`、`cc_agent_ot` 安装同一修复后
的包(不触碰已安装插件):

- 两个安装任务在 PyPI 拉黑下均 `success`,插件进程真实启动
  (`Installed agent: pi_strategy_ot` / `cc_agent_ot`),site-packages 分别 72/53 个。
- 事后卸载测试插件,daemon 存储恢复原状,`/etc/hosts` 已还原。

**验证 C —— ARM64 全真模拟**:binfmt qemu-aarch64 +
`python:3.12-slim`(linux/arm64)+ uv 0.7.12 aarch64 二进制,`--network none`
(完全无网络接口),执行同样的 daemon 命令:

- cc_agent:`aarch64` 架构确认;53/53 依赖安装;43 模块导入;tiktoken gpt2 离线通过。
- pi_strategy:72/72 依赖安装;完整 Pi 回合 `offline ok` / `completed`;tiktoken 离线通过。
- 验证后 binfmt 处理器已卸载,主机恢复原状。

## 生产部署步骤(物理隔离内网)

1. 传入两个 `.difypkg`(sha256 见上,导入前可校验);
2. Dify 控制台卸载旧插件(同 `plugin_id` 重复安装会静默失败,须先卸载;旧
   cc_agent 0.0.4 无离线能力,必须替换);
3. 通过"本地文件"方式分别导入新包安装——**无需配置任何 pip 源**;
4. 应用 Agent 节点钉住的 `plugin_unique_identifier` 更新为新版本,重新发布;
5. 常规两轮会话验收(状态恢复、审批、问卷)。

## 边界说明

- 本证据来自本地 Dify 1.5.0 + plugin-daemon 0.1.2 栈;≥1.7.0 的 daemon 保持同一
  `uv pip install -r requirements.txt` 安装路径,机制一致,但未在真实 arm64
  生产机上验收——安装后的常规业务回归仍需在生产侧做一轮。
- 插件运行期对网络的唯一预期访问是 Dify 自身模型/工具/MCP 通道(dotify daemon
  反向代理),不涉及任何 PyPI/公网依赖。
