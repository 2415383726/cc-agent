# 插件离线打包（air-gapped）

适用范围：`cc_agent/`、`pi_dify/`、`pi_strategy/` 的 `.difypkg` 离线包。目标：**安装期与运行期都不访问任何外网**（物理隔离内网可直装）。构建产物与实测证据见 [evidence/offline-arm64-package-verification.md](evidence/offline-arm64-package-verification.md)；本文只记录方法与不变量。

## 安装机制（为什么必须这样打）

dify-plugin-daemon（0.1.x，`internal/core/plugin_manager/local_runtime/environment_python.go`）安装本地包的固定流程：

1. 解包到工作目录，`uv venv .venv --python 3.12`；
2. `uv pip install [-i $PIP_MIRROR_URL] -r requirements.txt`。

daemon **只读包内 `requirements.txt`**，不读 `pyproject.toml` / `uv.lock`。requirements 文件内的指令在命令行参数之后生效，所以文件里的 `--no-index` 即使在 daemon 配了镜像的环境下也成立——依赖只能来自包内 `wheels/`。

**真离线判定**：解开 `.difypkg`，`requirements.txt` 首两行必须是：

```
--no-index
--find-links ./wheels
```

其余行为锁文件的精确 `==` 版本。没有这两行的包（如 `cc_agent-0.0.4` 及更早的 dist 产物）在内网必然安装失败，禁止分发。

## 打包不变量

1. **requirements 重写**：各插件 `scripts/build_offline_package.py` 打包时把 `requirements.txt` 替换为 `--no-index` + `--find-links ./wheels` + `requirements.lock.txt` 全文。修改构建脚本时不得丢失这一步。
2. **wheels 单架构**：`scripts/download_offline_wheels.py` 用 `--only-binary=:all: --implementation cp --python-version 3.12 --abi cp312`，平台取 `manylinux_2_28_{x86_64,aarch64}` 与 `manylinux2014_{x86_64,aarch64}`。`--arch arm64` 出的包只含 `py3-none-any` 与 `*aarch64*` wheel。
3. **版本必须递增**：每次重新出包 bump `manifest.yaml` 的 `version` 并同步 `pyproject.toml`。`meta.version` 是 Dify 清单格式版本，保持模板值（pi 系为 `0.0.1`），不要当作插件版本递增。同一 `plugin_id` 重复安装会被 daemon 静默拒绝，Dify 只认 `plugin_unique_identifier`。
4. **tiktoken 运行期缓存**：`dify_plugin` 的 `recalc_llm_max_tokens` 路径会调 `tiktoken.encoding_for_model("gpt2")`，tiktoken 0.8.0 首次调用会从 `openaipublic.blob.core.windows.net` 下载分词器。每个插件：
   - `_assets/tiktoken_cache/` 内置两个文件，文件名 = 下载 URL 的 sha1：
     - `6d1cbeee0f20b3d9449abfede4726ed8212e3aee`（gpt2 vocab.bpe）
     - `6c7ea1a7e38e3a7f062df639a5b80947f075ffe6`（gpt2 encoder.json）
   - 内容 sha256 与 `tiktoken_ext/openai_public.py` 钉死的值一致（vocab `1ce16647…`、encoder `19613966…`）；升级 tiktoken 版本时须重新核对该哈希再刷新缓存。
   - `main.py` 开头 `os.environ.setdefault("TIKTOKEN_CACHE_DIR", <包根>/_assets/tiktoken_cache)`；tiktoken 在调用时才读该变量。
5. **元数据随包**：`VERSION_MANIFEST.json`（wheel 清单 + sha256）、`THIRD_PARTY_NOTICES.md`、`LICENSES/` 由构建脚本生成，导入方可核对。

## 构建与验证步骤

```bash
# 依赖变更时（需联网机器），双架构各拉一次：
python3 <plugin>/scripts/download_offline_wheels.py --arch amd64 --arch arm64

# 出包（每架构一条；dist/ 产物名含架构后缀）：
python3 <plugin>/scripts/build_offline_package.py --arch arm64
```

验证分三层，内网交付前全部要过：

1. **构建期解析**：cc_agent 构建脚本内置 `pip download --no-index`（目标平台）解析校验；pi 系用 `verify_offline_package.py`（amd64 可实跑 `--no-index` 安装 + 冒烟；arm64 用 `--resolve-only`）。
2. **断网安装**（真实 daemon 行为）：在跑 plugin-daemon 的容器里把 `pypi.org`、`files.pythonhosted.org`、`astral.sh` 指向 127.0.0.1，解包后执行 daemon 原命 `uv venv .venv --python 3.12 && VIRTUAL_ENV=... uv pip install -r requirements.txt`，随后用装好的 `.venv/bin/python` 跑冒烟脚本：
   - pi 系：`scripts/offline_smoke.py`（完整 Pi 回合，断言 `terminal_status == completed` 与状态前缀）；
   - cc_agent：`scripts/offline_smoke.py <包根>`（逐模块导入 + tiktoken gpt2 离线编码）。
3. **arm64 执行**（无 arm64 真机时）：binfmt `tonistiigi/binfmt --install arm64` + `python:3.12-slim`（linux/arm64）+ 与 daemon 同版本的 aarch64 uv，`docker run --network none` 执行第 2 步同套命令。

验收标准：断网容器内依赖装满（dist-info 数 = 锁文件行数）、冒烟脚本 `ok: true`、tiktoken `gpt2` 编码成功、daemon 日志出现 `Installed agent`。

## 内网部署

1. 传入 `.difypkg` 并核对 sha256（见 evidence 文档产物表）；
2. 控制台**先卸载旧版本**（同 `plugin_id` 直接装会静默失败）；
3. “本地文件”导入安装——无需配置任何 pip 源；
4. 应用 Agent 节点更新钉住的 `plugin_unique_identifier` 后重新发布。
