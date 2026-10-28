# Harness 改进实施

Status: implemented — repository validation passed

2026-10-28：用户授权按评估方案实施，并明确删除 allowlist / denylist；user ID 已由独立节点控制，沿用现有接入。

## 本轮交付

1. 删除工具和技能 allowlist / denylist 的配置、过滤和执行分支；保留入口资格、路径校验、重复调用/连续错误保护、旧中断恢复。
2. 明确流式工具参数 delta / snapshot 契约，修复调用身份归并及重复字符丢失；默认日志不包含消息正文。
3. 模型上下文中技能正文单份，保留技能版本/完整性与重载行为，增加分项预算。
4. 同一本轮状态 backend 负责加载和编码；状态变量输出先于终态；区分运行结果、状态交付与外部执行结果。
5. 前端检查停止响应，显式表示断流/停止后的未知结果；在既有 history ticket 下恢复会话待处理中断。
6. 串行工具及时输出执行进度；总预算覆盖模型、摘要、重试、恢复工具，预算拒绝仍配对工具结果。
7. 补业务技能验收指引、运行/工具关联诊断、过时声明清理及离线包验证。

测试沿用已有公开 Interface：DifyModelAdapter 的流输出、AgentLoop 的实际模型输入/工具结果、runtime 两输出策略、DifyStateBackend 状态读写、前端 transport / runStream / agent+coordinator。外部模型、工具、HTTP 使用 fake，不 mock 自有协作者。

生产 provider 样本、Dify 工作流实际赋值/取消传播、外部业务幂等及业务场景需要生产或服务端证据；本轮实现仓库内契约和可重复验收，不凭空声称线上已验证。

## 完成记录

仓库内实现、回归、类型/格式检查、前端构建和双架构离线包均已完成。实际改动、验证结果与部署边界见 [validation.md](validation.md)。原评估中身份代理及重新引入 allow/deny policy 的候选已按用户决定排除。
