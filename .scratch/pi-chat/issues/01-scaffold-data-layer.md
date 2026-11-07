# 01: 骨架与数据层平移

**What to build:** 新建 pi_chat 前端项目（Vue 3 + Vite + TypeScript + vitest + happy-dom）。从 pi_workbench 原样平移数据层：`piagent.display.v1` 契约解析、投影归并、历史提取与保存态恢复、控制器规则（票号陈旧结果丢弃、断流不重发、停止 best-effort）、Dify 传输端点。回放控制器与三个场景数据就位，最小 App 壳以朴素样式渲染 process 场景，页面明确标注回放模式。本票是后续所有视觉票的地基——只求通路，不求好看。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `npm run dev` 以回放模式渲染 process 场景（朴素样式可接受），回放标注可见且不发起任何网络请求
- [ ] 数据层测试套件平移后全绿：契约解析、投影、控制器、历史提取、保存态恢复
- [ ] `npm run test` 与 `npm run build` 通过
- [ ] 未引入 React、Cordis 或任何公网运行时依赖
- [ ] 三场景（process/questionnaire/approval）数据在回放清单中可选
