# ZCode Gen UI：对 Pi + Dify + 静态 Vue 的设计参考

研究固定于 `zai-org/ZCode@3c5b227649371507ddc4eb46ac5133afe6db1cab`（GitHub main 查询所得）。仅选取源码阅读，未拉全仓，未修改产品代码。以下为源码事实与本项目适配判断，不等于已验证浏览器移植。

## 结论

值得参考，尤其是 **Skill 生成规范、纯 HTML 内容边界、宿主提供统一样式与受限桥、可视化状态与 Agent 轮次分离**。不需要为此引入 ZCode、React、Electron 或第二套 Agent runtime。ZCode 的现成宿主是桌面实现；本项目需要按 Dify 的传输、附件、历史与静态站点边界另行设计。

## 内容怎样显示

- 消息里的引用只包含 `path/title/mode`，不是把整页 HTML 塞进 Markdown。支持 `::visualize{path="..."}` 等形式；完成前不执行，代码块内排除，保留源偏移。来源：[UI 契约](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/ui/src/gen-ui/CONTRACT.md#L1-L17)、[消息组件](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/ui/src/gen-ui/components/GenUiMessageResponse.tsx#L1-L76)。
- 宿主按授权目录读取 HTML **片段**；拒绝 html/head/body/doctype 文档壳、越界路径、符号链接，并检查文件身份和大小。它不是 HTML sanitizer，允许作者 JS，隔离责任在运行宿主。[文件读取](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/services/src/gen-ui/adapters/files.ts#L1-L77)。
- 宿主提供完整文档壳：样式与状态/bridge 在前，作者片段居中，统一 inner kit 在后；calendar 按内容注入。不要把作者片段直接插入主 Vue DOM。[文档组装](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/services/src/gen-ui/adapters/service.ts#L40-L68)、[资源注入](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/src/main/pluginSandbox/protocol.ts#L195-L255)。
- 内联和展开保留同一个页面实例，避免重建丢失滑块/展开状态；高度上限 10,000px，自动测量防止视口反馈无限增高。[页面契约](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/ui/src/gen-ui/CONTRACT.md#L7-L11)、[测量实现](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/src/renderer/src/plugin-sandbox/genUi.ts#L29-L109)。

## 交互与状态的边界

- 桥基于 MCP Apps `App` / `AppBridge` 和 postMessage；作者侧 `window.zcode` 仅暴露 `widgetState`、`setWidgetState`、`sendFollowUpMessage`、`openExternal`。不暴露工具调用能力。[作者侧桥](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/src/renderer/src/plugin-sandbox/genUi.ts#L143-L193)。
- follow-up 先确认页面仍可见且 ready，绑定是当前可写会话，禁止重复并发发送；没有原生用户手势就弹宿主确认。异步等待后再次检查会话绑定，避免切换会话后误发。[宿主执行边界](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/ui/src/gen-ui/adapters/page.ts#L83-L109)。这是我们 controller 的 stale-result 规则可以借鉴的设计，不必照搬 MCP 协议。
- state 更新只是保存，不启动 Agent。状态分 `modelContent` 与 `privateContent`；后者不进入模型上下文，**不是秘密保险箱/加密保证**。单块 16KiB，最多 100 条，进入模型的总状态最多 64KiB，并以 `untrusted_gen_ui_state` 标记。[状态契约与上下文组装](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/shared/src/gen-ui/contract.ts#L4-L8)、[状态 schema](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/shared/src/gen-ui/contract.ts#L78-L99)、[上下文](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/shared/src/gen-ui/contract.ts#L212-L244)。
- Tweak 提供 slider/color/toggle/select 等受限控件、最多12个、参数范围与重复id校验。它适合可视化的本地参数调节，不能当成业务审批或替代 AskUser。[参数 schema](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/shared/src/gen-ui/contract.ts#L114-L204)。

## 隔离与离线：哪些不能直接假设

- 桌面隔离有多层：独立 Electron partition、shell/plugin 两种 origin、自定义 `zcode-sandbox:` 协议、禁 Node integration、启 contextIsolation/sandbox、禁 popups/navigation/download，另有 CSP 和权限闸门。这不是“加一个 iframe 属性”即可等价获得。[guest 策略](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/src/main/pluginSandbox/guestPolicy.ts#L17-L60)、[session](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/src/main/pluginSandbox/session.ts#L13-L39)、[frame 创建与来源检查](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/src/renderer/src/plugin-sandbox/main.ts#L18-L77)。静态 Web 实现必须另选浏览器隔离边界，不能原样复制其 allow-same-origin 配置后宣称同等安全。
- Gen UI 默认 `connectDomains:[]`、`frameDomains:[]`，但允许指定 CDN/字体 origin 加载静态资源；CSP 的 script/img/style 等会包含这些域。因此“无 fetch 权限”不等于所有资源都零联网，也不能宣称完全无外部通道。[注册](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/services/src/gen-ui/adapters/service.ts#L63-L68)、[域清单](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/shared/src/gen-ui/contract.ts#L21-L29)、[CSP](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/src/main/pluginSandbox/csp.ts#L39-L77)。
- 它将**精确 URL** 的 D3 7.9.0、Lucide 1.17.0、Floating UI Core1.7.3/DOM1.7.4 重定向到本地 vendor；清单有 SHA-256 和许可证，构建时校验。未知 URL 不自动下载缓存，也不保证可离线。[清单](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/apps/zcode-cli/packages/visualize-plugin/skills/visualize/assets/vendor/manifest.json#L1-L72)、[重定向](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/src/main/pluginSandbox/genUiVendor.ts#L45-L56)、[打包校验](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/desktop/scripts/gen-ui-runtime-assets.mjs#L14-L49)。我们适合直接使用本地路径并关闭远程源，而不是复制 Electron request interception。

## 对本项目的取舍判断

| 参考对象 | 价值与适配边界 |
|---|---|
| Skill、样式、HTML widgets、vanilla JS 参数控件 | 最值得学习；内容层独立于 Vue/React。可固定版本参考并保留归属，暂不复制产品实现。 |
| Markdown 引用、完成门控、错误兜底、保留实例 | 借设计；文档身份应基于 Dify 可访问的 artifact/content，而非桌面绝对文件路径。 |
| 受限 bridge、当前会话复查、状态分离 | 借边界；接我们的 controller、AskUser/审批与下一轮请求，不向任意 HTML 开放模型/工具权限。 |
| 自动尺寸、主题tokens、统一控件样式 | 与静态 Vue 宿主兼容；可以不引 React。 |
| React `GenUiCard` + ZCode workspace stores | 宿主逻辑耦合桌面应用，不能当现成 Vue 包使用。`@zcode/ui` 是 private workspace，React19 peer且依赖内部 services/rpc/shared。[package](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/ui/package.json#L1-L24) |
| Node 本地文件/状态服务、Electron partition/custom scheme | 不适合我们的生产形态；`prepareSandbox` 明确要求 desktop sandbox。[service](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/packages/services/src/gen-ui/adapters/service.ts#L21-L43) |
| 5MB HTML 文件预算 | ZCode 的桌面预算，不应照搬到约190KB Dify agent_state；完整artifact历史、轻量交互state、模型摘要需要分别设计。 |

建议后续先明确“内容从哪来、存在哪、刷新后从哪取”，再确定 marker 和 iframe。这样能在 Pi/Dify 限制内获得类似交互体验，而不会引入新的运行底座或破坏状态权威。

## 许可证

仓库 Apache-2.0；visualize 的专门声明明确覆盖 Skill入口、standalone assets、widgets、render脚本、参数runtime。vendor另按 Floating UI MIT、Lucide/D3 ISC，旁置许可证。实际引用需要保留相应许可证、归属与修改标记；本研究不是许可法律意见。[仓库许可证](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/LICENSE#L1-L11)、[visualize 声明](https://github.com/zai-org/ZCode/blob/3c5b227649371507ddc4eb46ac5133afe6db1cab/apps/zcode-cli/packages/visualize-plugin/skills/visualize/LICENSE.md#L1-L5)。

Skill路径：`apps/zcode-cli/packages/visualize-plugin/skills/visualize/SKILL.md`；补充 `references/api.md`、`references/styles.md`、`tweak.md`、`widgets/calendar.md`，导出 `scripts/render.py`、`scripts/vendor.py`。本文集中调查宿主与安全/依赖边界。
