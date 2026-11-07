# 09: 证据、check:static 与删除门

**What to build:** 验收与收尾门。重制证据：三场景回放截图 + live 截图落位证据目录；移植 `check:static`（哈希全产物、扫描外链/外网资产/追踪器，违例即失败）并出静态报告；四条 seam 测试全绿 + live 冒烟通过后执行删除门——删除 pi_workbench 目录，改写 AGENTS.md 的 pi_workbench 边界条款为 pi_chat 条款（保留「回放必须用同一契约与组件，不做第二个渲染器」表述），同步 README。

**Blocked by:** 08.

**Status:** ready-for-agent

- [x] 回放三场景 + live 截图落位证据目录，可对照旧证据
- [x] `check:static` 移植并通过，产出静态报告
- [x] 投影/控制器/组件/回放四条 seam 测试全绿
- [x] pi_workbench 目录已删除，仓库无双轨残留引用
- [x] AGENTS.md 与 README 更新为 pi_chat 条款，回放不变量表述保留
