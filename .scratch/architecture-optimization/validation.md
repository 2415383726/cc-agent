# 架构优化验证

基线：`0bbace1`。六项优化及确认的裁剪均已实施。

- 后端：`python -B -m unittest discover -s cc_agent/tests`，213 项通过。
- 前端：`npm run test`，40 个文件、186 项通过。
- `npx tsc --noEmit` 通过；补齐开发期 Node 类型，以及三个既有的类型缺口，无运行依赖升级。
- 增量 mypy：interrupts/model_requests/skill_catalog/tool_catalog/tool_adapter/state_backend/loop/compression 共 8 个模块通过。
- `npm run build` 通过；保留原依赖的包体积和浏览器兼容提示。
- Dify 重复两半和语义 JSON 去重原样保留；运行级用例覆盖两策略的普通/恢复调用，模型历史仅保留一份 observation。
- MCP 本地 HTTP 测试覆盖两策略批准后的二进制输出和连接释放；未连接生产服务。

- 离线包：`cc_agent/dist/cc_agent-0.0.4-offline-linux-amd64-arm64.difypkg`，版本 0.0.4。amd64/arm64 离线依赖解析均通过；归档 CRC 校验通过，61 个 Python 文件与当前代码逐字节一致，manifest 规范化后相同；已删除模块不在包内。
- SHA256：`75669bf3efb2b91794814e68e3b90e9ca6778c46b6272340b7b41bfdf4077461`。
- 对照基线 AST 核验，Dify normalization 和三个去重函数全部未改；只合并目录类型及删除双重查找。
- 审查：Standards 两项、Spec 一项均已修复，复审无剩余发现，详见 [review.md](review.md)。

实现提交：`b6308da`；审查修复：`4432655`。两项前端问题先以真实 agent/SDK 边界复现（4 项失败），再修复并跑全量测试。原生事件之前的 metadata/blob 延后到协议开始时发送；已开始的 fallback 段在切换原生 run 前结束。历史 ticket 在状态提交及回调前验证。
