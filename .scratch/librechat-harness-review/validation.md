# 执行内核改进验证

2026-10-28，基线 `951526723eb2f32eb90e52bc43e889c7762a5d16`，按用户 `/implement` 授权在当前 `main` 分支实施。

## 行为覆盖

- 模型预算与实际消息投影一致，展示 payload 不重复写入工具历史。
- 当前用户问题保留，最新工具组完整配对；同一请求较早的工具循环仍可摘要。
- 新摘要替换旧摘要；摘要读取仍保留的缩减前内容；只截短时不覆盖摘要源。
- 混合语言估算不因加入英文而减少，摘要头尾裁剪后再次满足 token 限制。
- 固定上下文无法装入时不调用主模型或摘要模型，也不破坏历史。
- Skill 同批结果先配对再注入正文；中断尾部不执行，仍得到 skipped 结果与结束事件。
- Skill 资料经单条和批次预算后，页游标精确对应实际交付内容；逐页重组与原文件一致。
- 技能入口资格生效；已更新、旧格式或不完整持久记录允许重新加载。
- 状态容量最终校验，保留完整 pending 参数；保存失败不会输出正常完成或无效状态。
- 两种输出策略的未处理异常返回安全 agent_failed，外部工具异常不回显运行凭证。

## 执行结果

- 完整 Python unittest：234 项通过。新增回归位于 `cc_agent/tests/test_harness_reliability.py`，旧契约测试同步调整保存参数与旧技能记录的预期。
- 17 个改动核心模块的增量 mypy 检查通过（`--follow-imports=silent --ignore-missing-imports`）。扩展到 model_adapter / strategy 时仍有基线已有的 23 项类型问题；已用基线源码副本复核。本轮未扩大到这些既有类型整改。
- Black 使用仓库约定 `-C -l 100`；Ruff 对改动文件执行导入整理、未使用名称检查，行宽与 Black 对齐为 100。完整规则仍报告既有通用 catch、SDK fallback 等规则问题；本轮安全边界明确只记录异常类别，不用 traceback 满足日志规则。
- `git -c core.whitespace=cr-at-eol diff --check` 通过；仓库现有文件使用 CRLF。
- 离线构建验证 Linux amd64 / arm64 的锁定 wheel 解析并成功产出 `cc_agent/dist/cc_agent-0.0.4-offline-linux-amd64-arm64.difypkg`。

本机复用了 uv 缓存中的 Python 3.12 与依赖，通过临时 runner 注入依赖路径；未修改依赖声明、锁文件或仓库虚拟环境。runner 将 PYTHONPATH 传入子进程，保留日志机制，以覆盖 MCP 首次连接和并发凭证隔离测试。

未连接生产 Dify / MCP 服务，真实 provider 的流式工具参数样本、导出业务验收仍待后续。前端及外部 MCP 接口不在本轮改动范围。

双轴审查结果及处理见 review.md。
