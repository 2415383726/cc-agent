# LibreChat 的长内容策略及 Q10 建议

更新：2026-10-28。参考本地 LibreChat `8ff185759e12eddd509dd84304a408276603c10f`，并直接核查本地 `node_modules/@librechat/agents` **4.0.5** 源码。只读代码调查，没有执行生产工具或修改运行代码。

用户要求在决定 Q10 前参考 LibreChat 的实际方案。以下候选尚未写成已接受 ADR。

## 1. 技能目录、正文和资料分别处理

- [skillCatalog.ts:5](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/tools/skillCatalog.ts:5)：目录默认使用上下文的 1%，每条 description 最高 250 字符；超限按“简介按比例缩短 → 仅名称 → 减少条目”降级。
- [skills.ts:95](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/skills.ts:95)：宿主默认目录限 100 技能，最多扫描 10 页；[skills.ts:797](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/skills.ts:797) 记录实际到达模型的简介缩短或遗漏。
- [skills.ts:908](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/skills.ts:908)、[handlers.ts:5288](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/handlers.ts:5288)：激活技能时，将正文作为带来源的 meta user message 注入；目录预算不等于正文也截成 250 字。正文仍受整体上下文管理约束。
- [tools.ts:499](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/tools.ts:499)：read_file 支持 start_line / max_lines；显式指定范围时默认 200 行、最多 500 行；不指定范围的 skill/sandbox 文本读取走全读路径。
- [handlers.ts:1093](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/handlers.ts:1093)：按连续行返回，带行号；页在 UTF-8 262144 bytes 限制处缩短时，尽量退到完整行，并根据实际交付行数提示下一 start_line。单行本身超限时明确指出不能按行继续。

边界：不能据此宣称任意大技能文件都可用 read_file 分页。未缓存的技能文件在读取存储前若超过 256KiB，会提示先激活技能，再通过已准备的代码环境读取（[handlers.ts:5033](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/handlers.ts:5033)）；缓存文本和 SKILL.md 的读取分支有所不同。技能文件 prime 到代码环境也受 codeEnvAvailable 条件约束（[handlers.ts:5321](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/handlers.ts:5321)）。

可借鉴：目录负责发现，正文负责工作方法，资料由有界且可续读的读取协议提供。CC 不需要为此引入沙箱；增强已有 SkillReadResource 即可，保留技能所属路径检查。

## 2. 工具结果先有入场上限，模型预览采用头尾保留

[truncation.ts:49](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/utils/truncation.ts:49) 默认单结果字符限额为：

```text
min(floor(contextWindowTokens × 0.3) × 4, 400000)
```

这是估算字符预算，不是 tokenizer 的精确换算。[truncation.ts:136](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/utils/truncation.ts:136) 超限后保留约 70% 头部、30% 尾部，尽量落在换行边界，明确附上截断说明；小预算退化为前缀读取。

[ToolNode.ts:4633](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/tools/ToolNode.ts:4633) 在构造 ToolMessage 前执行有界序列化；content 和 artifact 分开处理。默认常量名虽为 HARD_MAX，但 [ToolNode.ts:1268](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/tools/ToolNode.ts:1268) 允许显式 maxToolResultChars 覆盖默认计算，因此不能把 400000 描述成任何配置下都不可突破的全局强制上限。

可借鉴：根据可用模型预算确定结果视图，并把模型内容和展示产物分开。对 CC，应先修正 metadata 被误算入模型预算的问题，再考虑调限额；不能直接把默认 8000 放大到 400000，后者会冲击 Dify 状态容量。

## 3. 历史结果按上下文压力和是否已消费渐进缩减

[fading.ts:14](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/messages/fading.ts:14) 与 [prune.ts:1213](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/messages/prune.ts:1213)：

- 根据最新有实质文本的 AI 消息区分已消费结果和新结果，新结果优先保留。
- 压力达到 80% 时，可对已消费结果启用更短视图。其上限约为新结果限额的 10%，有 300 字符下限，并且不会超过新结果限额。
- 未启用摘要时，85% / 90% / 99% 压力增加缩减档位；启用摘要时关闭这些额外压力档位，但仍保留整批工具交互能装入预算的限额及已消费结果 masking。
- 同时考虑本轮工具批次宽度、指令和 schema 开销；缩减档位只加深，避免历史文本随着每次估算变化反复改写，影响 prompt cache。
- [prune.ts:1259](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/messages/prune.ts:1259) 从 canonicalMessages 生成当前模型投影，而不是在上次已截断的字符串上继续截断。

可借鉴：先保护当前请求和最新完整工具组，旧结果承担更多压缩；上下文预算和 Dify 状态编码预算各自负责自己的限制。百分比和字符默认值需要针对 CC 的模型窗口及 190KB 状态边界验证，不直接照搬。

## 4. 摘要尽量读取进一步缩减前的内容

[prune.ts:3054](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/messages/prune.ts:3054) 在启用摘要时保存 masking 前的工具内容，供后续摘要恢复使用；[summarization/node.ts:202](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/summarization/node.ts:202) 有恢复这些内容的路径。

这里的 original 指进入 ToolMessage 后、进一步 fading/masking 之前的内容。入场限额已经丢掉的远端内容不会被摘要器自动恢复，保留映射自身也有限额。因此不能描述成“摘要永远读取完整远端原文”。

可借鉴：避免先把内容截到只剩头尾，再要求摘要器概括已经丢失的中间信息。CC 可在当前运行里保留有界的摘要源，但不能承诺跨轮仍能恢复未保存原文。

## 5. 原始结果引用是可选、有界的运行内机制

- [run.ts:2769](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/run.ts:2769)、[run.ts:3124](/home/ygao/Desktop/work/librechat/LibreChat/packages/api/src/agents/run.ts:3124)：当本轮任一 agent 具备代码环境能力时启用 toolOutputReferences。
- [toolOutputReferences.ts:4](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/tools/toolOutputReferences.ts:4)：工具输出按 run 和批次保存为引用，模型可以将 `{{tool0turn0}}` 放在后续工具字符串参数中；真正执行前替换为所保留的结果，便于在 bash/jq 中提取子集，而不要求模型复制整份 JSON。
- [toolOutputReferences.ts:205](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/tools/toolOutputReferences.ts:205)：当前默认单项 400000 字符、合计 800000 字符；5000000 是合计硬上限，不是当前默认值。宿主部分注释仍称默认 5MB，应以构造代码和计算函数为准。
- [toolOutputReferences.ts:268](/home/ygao/Desktop/work/librechat/LibreChat/node_modules/@librechat/agents/src/tools/toolOutputReferences.ts:268)：单项超限按前缀裁剪，合计超限淘汰旧项。该机制是有界、按运行隔离的引用注册表，不是自动把任意结果永久写成可 read_file 的文件，也不保证任意超长结果完整保存。

适配 CC：当前内部不提供通用 bash/文件执行。业务结果的可恢复复取适合由现有外部工具或后续 MCP 的 cursor、job_id、result_id 等协议承担。若以后确实需要运行内结果引用，应作为单独需求明确容量、生命周期、失效和授权；不把原始结果塞入 agent_state，也不为了复制引用语法重建工作区。

## 收敛后的 Q10 候选

1. 技能目录、正文和参考资料分层加载；SkillReadResource 支持连续有界分页，明确范围、是否截断及下一位置。
2. 页大小与最终 ResultBudget 协调，不能返回一页后再按头尾剪掉中间，却给出跨过缺失内容的下一页游标。
3. 普通工具结果保留有界模型视图和清晰截断标志；新结果优先，旧结果按上下文压力渐进缩减。
4. 摘要优先使用本轮仍保留的、进一步有损缩减前内容；成功摘要替换旧摘要，保留当前决定。
5. 原文复取走具备权威数据的外部服务；具体 MCP 接口留到用户后续工具优化。当前不新增内部脚本、通用文件工具或会话存储后端。

这比仅选择“头尾截断还是分页”更完整，也保持用户已确认的 skill first、全量简洁工具和 Dify 状态所有权。2026-10-28 用户确认后，已按 spec.md 顶部范围实施，最终行为见 README，验证记录见 validation.md。
