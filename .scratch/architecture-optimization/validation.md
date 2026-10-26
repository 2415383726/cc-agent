# 架构优化验证

基线：`0bbace1`。六项优化及确认的裁剪均已实施。

- 后端：`python -B -m unittest discover -s cc_agent/tests`，213 项通过。
- 前端：`npm run test`，40 个文件、181 项通过。
- `npx tsc --noEmit` 通过；补齐开发期 Node 类型，以及三个既有的类型缺口，无运行依赖升级。
- 增量 mypy：interrupts/model_requests/skill_catalog/tool_catalog/tool_adapter/state_backend/loop 共 7 个模块通过。
- `npm run build` 通过；保留原依赖的包体积和浏览器兼容提示。
- Dify 重复两半和语义 JSON 去重原样保留；运行级用例覆盖两策略的普通/恢复调用，模型历史仅保留一份 observation。
- MCP 本地 HTTP 测试覆盖两策略批准后的二进制输出和连接释放；未连接生产服务。

离线双架构依赖与最终审查结果在完成后补充。
