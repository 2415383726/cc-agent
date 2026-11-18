# Pi Strategy 0.2.1 离线包验证（arm64 / amd64）

Date: 2026-11-18。源码：`release/pi-strategy-0.2.1`（含 `perf/session-io-wakeup`
的流式交接与请求准备优化）。目标：按 [packaging.md](../packaging.md) 出真离线包，
重点验证 ARM64 的安装与运行。

## 产物

| 文件 | bytes | sha256 |
| --- | --- | --- |
| `pi_strategy/dist/pi_strategy-0.2.1-offline-linux-arm64.difypkg` | 26,048,735 | `419fc0d5869eb53878374c30bb723c3dce363efa04241078e6a567f0ffb748ab` |
| `pi_strategy/dist/pi_strategy-0.2.1-offline-linux-amd64.difypkg` | 27,031,005 | `cb85587baab2e7312d628afdd5899b30c09c10d476357d9763715519f65a2ca5` |

包内审计（两包一致，仅架构 wheel 不同）：

- `requirements.txt` 首两行为 `--no-index` / `--find-links ./wheels`；
- wheels：52 个 `py3-none-any` + 20 个目标架构 wheel（arm64 为 `*aarch64*`，
  amd64 为 `*x86_64*`），共 72；
- `_assets/tiktoken_cache/` 含 gpt2 vocab/encoder 两个文件；
- 无 `__pycache__`；`interaction.py` 不存在；manifest `version: 0.2.1`，
  `arch` 只含目标架构。

## 验证

1. **构建期解析**：`verify_offline_package.py --arch arm64 --resolve-only` →
   `resolution_ok: true`，72 包全部解析。证据：
   `pi-strategy-0.2.1-arm64-resolution.json`。
2. **amd64 断网安装**：`--no-index` 安装 0.25s，冒烟
   `{"answer":"offline ok","terminal_status":"completed"}`，状态前缀
   `pistrategy-state`。证据：`pi-strategy-0.2.1-amd64.json`。
3. **arm64 真执行**（文档验证 C）：binfmt `qemu-aarch64` +
   `python:3.12-slim`（linux/arm64）+ uv 0.7.12 aarch64 二进制，
   `docker run --network none` 执行 daemon 同款安装命令：
   - `arch=aarch64`，`venv_machine=aarch64`，Python 3.12.16；
   - `uv pip install -r requirements.txt`：72/72 dist-info；
   - 冒烟：`{"answer":"offline ok","terminal_status":"completed"}`；
   - tiktoken gpt2 离线编码：`{"gpt2_tokens":3,"ok":true}`；
   - 完整输出见 `pi-strategy-0.2.1-arm64-exec.txt`；验证后 binfmt arm64
     处理器已卸载，宿主恢复原状。
4. **回归**：`pi_strategy/tests` 101 通过（连续 3 次），`ruff` 与
   `black --check` 全绿。

## 部署（Dify 控制台）

1. 把对应架构的 `.difypkg` 传入内网并核对 sha256；
2. 先卸载旧版本（同 `plugin_id` 重复安装会被 daemon 静默拒绝）；
3. 通过“本地文件”导入安装，无需配置任何 pip 源；
4. 应用 Agent 节点更新钉住的 `plugin_unique_identifier` 后重新发布；
5. 常规回归：文本流、工具卡、stop、多轮 state、MCP 工具与附件。

说明：`dist/` 中仍保留 0.2.0 包（供已开始的安装对照），本次交付请使用 0.2.1。
