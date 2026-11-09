# Pi visualize 02：本地运行套件与真实历史证据

日期：2026-10-29–30。对应 [02 票](../../.scratch/pi-visualize/issues/02-local-visualization-kit.md)。

本票交付 kit 1.0.0：共享主题/样式、原生表单、可访问 tabs/tooltip、Lucide 初始化，以及固定本地 D3 7.9.0 / Lucide 1.17.0。作者声明 `data-libraries="d3 lucide"`；父工作台按清单只读本地资源，使用浏览器 Fetch SHA-256 integrity 和字节数校验，再在作者脚本前内联注入。没有 CDN 回退、新 Agent 桥或 Pi 运行内核改动。

## 真实 Pi / Dify 保存与重开

Dify 1.15.0，现有独立验证 app `9cdedc0b-d8a6-4b73-a0b5-95bece069037`，Pi Harness 0.6.0。检查时配置的 provider 为 `langgenius/deepseek/deepseek`、模型 `deepseek-flash`，不是模型版本号。两轮 live 都录得真实 `run.state` / `run.done` completed，见 [安全平台摘要](visualize/kit-platform.json)。

这是让真实 Pi/provider 原样输出固定完整片段的可控验收，**不是 03 的内置技能自由生成验收**。第二轮按普通对话要求更新说明，旧作品保留。每幅作品包含 360 条有意义的模拟速率采样，覆盖 120 分钟、20 秒间隔，并由图表和数据表实际使用；没有用于凑长的注释。

同一真实会话 `620c7d61-d0ff-4bce-8a97-b392fde3fc6f`：

| 平台消息 | 回答字符 / UTF-8 字节 | 作品源码字符 / UTF-8 字节 | 回答 SHA-256 |
| --- | --- | --- | --- |
| `60a4ba52-4688-4ac7-86d1-cca045c91e5f` | 30,664 / 31,647 | 30,644 / 31,627 | `09fd2ea7cd484a0cc33575b7268ce737b0b2445afc6aa6ce2d972bff531a4ff4` |
| `18dda298-ec6c-484c-864c-296e8021a178` | 30,553 / 31,346 | 30,533 / 31,326 | `b69bffacc254e3eb0eab21aba6da36f8f6a45b5c89391f8e84ffc8cb5f444015` |

两版均是闭合的合法 `pi-visualize` 围栏，由实际工作台解析、通过库声明校验并执行；这补齐了 01 留下的合法 >16k 作品链路，不把此前含未分离思考的长文本追认为合法作品。

[真实历史结果](visualize/kit-native-history.json) 保存逐消息身份、回答/源码 SHA-256、字节数与三次重取结果：首次历史、刷新、无 cookies/cache/sessionStorage 的新 context。每次原生回答与对应 SSE 逐字一致，源码摘要和内容身份一致。实际操作证明：两个旧/新作品分别可查看，D3/Lucide 正常初始化，滑块/选择/第二窗口改变图形，展开保留 frame 与参数；刷新及新 context 恢复初值（到达 3、单窗口 2、第二窗口关闭）；切换新会话移除全部作品 frame。

该 Dify app 的两条 `agent_thoughts` 仍为空。重开时不自动运行；用户分别点击“查看作品”，作品继续显示“运行状态未确认”，没有补造可信终态，也没有重 POST。原始 service key、console cookies、完整事件原件留在测试机 `/tmp`，不入库。

## 实际套件浏览器行为

浏览器 Chromium `154.0.8037.57`，本地构建产物配与产品一致的专用 CSP / Connection-Allowlist 响应头。临时测试代理只用于 Dify 验证，不是产品后台。

[实际套件行为结果](visualize/kit-browser.json) 通过与 live/history 共用的 `/?replay=visualize-kit`：

- 真正执行 D3 7.9.0、Lucide 和作者脚本，初始化可见图标；slider/select/toggle 改变原生速率柱、D3 排队折线和数值，播放前进、暂停冻结、重置回初值。
- tabs 的 Left/Right/Home/End 更新焦点、选中状态和唯一可见面板；自动回归另覆盖禁用 tab 跳过。tooltip 在键盘焦点显示、Escape 关闭，触摸显示、外部触摸关闭。必要公式在普通可见文字中也存在。
- 浅/深切换改变原生 SVG 填色、D3 系列颜色及 canvas 像素，保持同一个 blob frame 和当前参数；展开/收起也保留同实例。
- 320px 主页面 scrollWidth=320，作品 viewport/scrollWidth=270，均无横向溢出；range/select/switch/button/tab 均测得 44px 高，图表标签与单位可读。宽屏与窄屏截图分别检查控件和图形区域。
- 减少动画偏好下初始暂停，等待后时间不自动增长；仍可手动调参和播放。父/top DOM、localStorage 均为 SecurityError。
- 正常本地交互期间外部请求、POST 和页面脚本错误均为 0。浏览器额外请求缺省 favicon 的本地 404 不属于作品资源或公网请求。

最终截图已逐张目检。首轮发现的浅色主壳/提示色和控件边框对比已修正；一次 fresh-context 截图在完整绘制前拍到黑块，已丢弃，最终版本明确等待 D3、ready、布局与绘制后重新获取：

- [真实历史浅色](screenshots/pi-visualize-kit-real-history-light.png)、[全新 context 真实历史深色](screenshots/pi-visualize-kit-real-history-fresh-dark.png)
- [套件桌面浅色](screenshots/pi-visualize-kit-desktop-light.png)、[桌面深色](screenshots/pi-visualize-kit-desktop-dark.png)
- [320px 深色控件](screenshots/pi-visualize-kit-mobile-320-dark.png)、[320px 浅色控件](screenshots/pi-visualize-kit-mobile-320-light.png)、[同作品滚到图形区域](screenshots/pi-visualize-kit-mobile-320-figures.png)

## 降级、隔离和发布物

[真实负例与网络接收端](visualize/kit-failures.json)：缺少/不符的 CSP 头、D3 文件缺失、同长度 D3 内容被改动（SRI 不匹配）均保留标题/文字替代，作品 frame 数为 0，无 CDN 重试。未知 kit/library 通过公开内容解析回归拒绝。精确 CSP 响应头已加入 Vite dev 和 Nginx 示例；空 `Connection-Allowlist: ()` 保留，主页面仍能正常访问 Dify。

加载真实库后，`d3.json`、`d3.csv`、fetch、beacon、RTC/STUN 和作者自导航尝试的实际 HTTP/UDP 接收数均为 0。接收端先通过父 HTTP 与直接 UDP 正控制分别收到 1 次请求/数据包，证明观测有效；不以 Promise 拒绝或 Network 列表缺席冒充“没有发出请求”。本票没有降低 01 的双层 opaque sandbox、父 frame/channel 检查、完成门控或权限边界。

发布清单为 [manifest.json](../../pi_workbench/src/visualize/manifest.json)，Vite 将同内容发布为 `dist/visualize/manifest.json`；同目录包含 [NOTICE](../../pi_workbench/public/visualize/NOTICE.txt) 和邻接的完整 vendor 许可证。脚本与许可哈希匹配固定 ZCode `3c5b227649371507ddc4eb46ac5133afe6db1cab` vendor 清单，未修改第三方脚本。共享 CSS/runtime 为本项目编写，没有移植 ZCode React/Electron/CSS 或 Floating UI。ZCode 自有资源的 Apache-2.0 与单独 vendor ISC/MIT 归属区别已记录。

构建前检查 source/public 资源版本、哈希和字节数；静态发布检查同时比对实际 dist 清单和文件/许可证。一次主动改动 dist D3 的同长度字节实验正确令静态检查失败，恢复原始资产后通过；没有为第三方资源放开可执行外链扫描例外。全部 vendor 在工作台公开静态资产目录，不在插件技能扫描目录。

## 自动检查与剩余范围

- TDD 在既定内容解析、组件与控件行为接缝逐步红绿：库 ID、tabs 键盘/禁用状态、tooltip 焦点/触摸/Escape、真实 Lucide 初始化、示例合法性，以及同身份重投影保持原 frame。共享样式不做逐类镜像测试。
- 最终 `npm test` 55/55、`npm run build`、`npm run check:static`、定向 `tsc --noEmit`（`src/visualize/kit.ts` 及其依赖）与 `git diff --check` 通过。没有宣称跑过 Vue 全项目 typecheck。
- Impeccable context/craft-floor 已读取；保留既有工作台风格并增加主题映射，最终机械检测 `[]`。按任务范围，完整功能的独立最终评审留在 04。
- [准确作者 API](../../pi_workbench/docs-visualize-kit.md) 和两个小完整示例已给 03；[部署说明](../../pi_workbench/docs-visualize.md) 明确精确响应头和完整静态资源目录。

本票实际验证的是本机 Chromium154 和所述静态代理；目标生产反向代理头保留、未来浏览器、04 的分页/异常组合与完整发布仍需后续验收。强 CPU/内存配额未纳入承诺。03 的技能发现/激活、自由生成与修订尚未实现；本票不改 Pi 状态或模型/工具调度边界。
