# Pi visualize 01：实现与验收证据

日期：2026-10-29；对应 `.scratch/pi-visualize/issues/01-interactive-answer-roundtrip.md`。

本票实现完整原生回答的逐消息归并、专用内容块与格式/字节校验、双层 opaque iframe 宿主、本地 SVG 交互、展开保实例与关闭、可信完成门控，以及未知历史作品的显式查看。未引入 D3/Lucide、共享控件套件或内置生成技能。既有聊天视觉与普通代码渲染保留。

## 验收范围与限制

**真实平台保存、实际浏览器宿主、带日志的历史契约回放分别有证据，不能相互冒充。** 当前 Dify 1.15.0 的 advanced-chat `/v1/messages` 不返回 Pi 过程日志，实际两条记录的 `agent_thoughts` 均为空。因此无法声称“真实 Dify 带正常过程日志的两轮历史重开”已通过。

完整回答由平台逐条保留。没有可信 Pi 终态的完整合法历史作品先显示标题/说明与未确认提示，由用户选择“查看作品”；未知状态保留，最新 Pi 状态不被用于替旧作品补造完成事实。为使本票在实际平台完成刷新/重开闭环，规格既定的最小显式查看入口由04前移至01。录制的真实 live Pi 事件绑定对应原生回答后，作为公开投影接缝的契约回放验证；该 fixture 明确标注并非平台历史原样返回的日志。

## 真实 Dify / Pi 保存

本机 Dify 1.15.0，独立验证 app `9cdedc0b-d8a6-4b73-a0b5-95bece069037`，真实 Pi 插件与配置的 provider。两轮同一会话 `fc2dd357-f5fb-4752-86f9-d571cb1d34e0`；新建独立 HTTP client 重取历史，逐字与 SSE 原生回答一致，不依赖浏览器缓存、显示日志或 `agent_state`。

| 平台消息 | 原生回答字符 / UTF-8 字节 | SHA-256 | 新取历史 |
| --- | --- | --- | --- |
| `6d6fa7d4-c528-4c87-9edd-ed88e09c4ae5` | 16,751 / 17,293 | `8ff8c90ff37ec039c0bfb56eb232d3ece92915a7c8331a70fe1e3e4383473dc5` | 完全一致 |
| `33167c7b-8155-4980-b575-5f9da53926c6` | 3,339 / 3,776 | `5c25426c44a323b18e536af68993851464d84dd4da4eb8f44ba055c858667d70` | 完全一致 |

两轮 live 均录到真实 Pi `run.state` / `run.done`，状态 completed。首轮临时应用当时未打开 runtime thinking 分离，原生回答中包含 provider 的 `<think>` 文本；它证明超过 16,000 字符的 **原生回答** 保存，不能称为超过 16,000 字符的作品源码。第二轮将固定排队片段交真实模型输出，是可控内容验收，不代替 03 的内置技能自由生成与修改验收。

原始结果仅留 `/tmp/pi-visualize-runtime/generated-01/` 与 `ticket01-second/`。密钥不入库。无秘密摘要见 [native-roundtrip.json](visualize/native-roundtrip.json)；公开契约 fixture 位于 `pi_workbench/fixtures/recorded-native-history.json`。另有前置固定 Answer 应用两轮实验（一轮18,674字符/42,752字节）只证明平台原生保存能力，明确没有 Pi 节点，不能当作 Pi 过程日志证据。

## 实际宿主和工作台浏览器

浏览器 Chromium `154.0.8037.57`。实际产品 `public/visualize/sandbox.html` SHA-256：`e7a41f0a661a853695c98413ee70cab2d5aa83a0ec4288fb73045a24a710bc7f`。

[实际 shell 七场景结果](visualize/product-shell.json) 使用真正的本机 HTTP 与 STUN/UDP sink：

- 合法本地 SVG/script 真正执行，并收到 ready/resize；自包含 data 图片正常加载。
- 父 DOM、顶层 DOM和存储访问均抛 SecurityError。
- fetch、远程图片、自导航、RTC与嵌套 RTC 的实际 HTTP/UDP sink 均为零；不是以响应不可读或 request 事件缺席代替网络观测。
- CSP 对子 blob 的继承已实际暴露并修复：外层 hash-only script-src 曾阻止合法脚本；外层缺少 img-src data 曾阻止自包含图片。最终政策允许所需 inline/data 内容，并由 Connection-Allowlist 约束网络。

[实际工作台结果](visualize/workbench-ui.json) 在 `/?replay=visualize` 通过同一展示组件验证：键盘调滑块改变标签、柱宽和趋势；暂停冻结时间；重置恢复默认并暂停；展开/收起保持同一个 blob frame、参数及暂停状态；刷新重新创建作品并回初值；关闭移除双层 frame。390px 页面及作品均无横向溢出，零页面错误、零公网请求。

这是实际产品宿主与固定回放交互的证据，**不是**真实 Dify 历史带日志重开的截图。截图已目检：

- [桌面展开](screenshots/pi-visualize-desktop.png)
- [390px](screenshots/pi-visualize-mobile-390.png)
- [390px展开](screenshots/pi-visualize-mobile-390-expanded.png)

[预检网络核验](visualize/preflight.json) 对真实 `answerSegments` 入口的非法图片、frame、link、doctype、实体、SVGimage、CSS import、script、object及嵌套template观测实际 HTTP sink，均零请求；同页主动 Image/fetch 的正控制确有两个请求到达。嵌套template最初漏过格式检查（未有网络泄漏），最终以递归template.content校验修复，并增加回归用例。

## 支持与部署

标准 Chromium154+ 加专用静态 shell 的 `Connection-Allowlist: ()` 是本票明确支持边界；本次只实测154。旧浏览器或缺头部署只能文字降级，不提供绕过按钮。UA和响应头预检是兼容/部署门控，不是策略的 JS polyfill，不能证明伪造 UA 或关闭浏览器安全实现的环境。

部署说明与 exact-location Nginx 示例见 `pi_workbench/docs-visualize.md` 和 `pi_workbench/deploy/nginx-visualize.conf.example`。Vite dev为专用URL加头，普通静态服务器/preview不会自动安装生产响应头。主页面不施加空 allowlist，Dify 请求继续走既有边界。

## 自动检查

TDD 在已确认的投影/历史、内容解析、组件接缝逐条红绿；覆盖逐轮裁剪文本替换、原始回答空白保真、前轮终态不冒认后轮、版本/根元素/闭合围栏/外链/嵌套template、64KiB边界/多字节/Unicode字段/第三块、生成与停止门控、缺策略拒绝、伪造消息、同实例展开及关闭。真实事件契约回放与合成边界用例并存。

最终工作台测试49/49通过，Vite build通过，check:static零违规，git diff --check通过。产品未改 Pi 运行内核，本票不声称新增 Python 行为。Impeccable context/craft-floor已读取，保留 incumbent 样式；最终机械检测无发现。未另起子代理作独立设计评审，供主实现会话接续整体评审。

## 对01验收项逐项结论

| 票内验收项 | 结论及证据类型 |
| --- | --- |
| 真实Dify完整回答与>16k回答、逐轮摘要 | 通过平台/Pi服务API；长原生回答含未分离provider reasoning，作品预算另用精确单测 |
| 完整回答按消息/run合并并保留过程/终态 | 通过公开投影/控制层及真实事件契约回放 |
| 专用块、普通代码/用户/工具来源边界 | 通过同一组件与协议接缝；工具结果仍纯pre文本 |
| 真闭合、版本、结构、外链、UTF-8预算、字段上限 | 通过解析接缝边界回归；真实预检sink零请求 |
| 滑块/暂停/reset/展开同实例/刷新初值/样式隔离 | 通过真实工作台回放浏览器；主DOM隔离由真实shell检查 |
| opaque沙箱、父访问拒绝、无公网与无RTC请求 | 通过实际产品shell HTTP+UDP sink，受支持浏览器/响应头边界明确 |
| 完整回答+可信completed才自动执行、停止/失败不执行 | 通过组件/控制层；可信状态按run绑定，无缺失终态补造 |
| live/history/replay共用；带日志两轮历史 | 共用实现通过；真实live事件+历史answer契约回放通过；真实平台无过程日志保持未确认；两幅合法原生历史显式重开、刷新及全新浏览器恢复已通过（见补充） |
| 必要测试与真实证据 | 以上自动检查与无秘密摘要/截图均保留；技能、共享套件、复杂异常/分页仍属02–04 |


## 补充：真实无日志历史的最小重开闭环

同一真实 Dify 会话新增第三轮固定作品，平台消息 `24af8ced-1b52-45ab-b83a-69ee04148315`：3,339字符 / 3,776 UTF-8字节，SHA-256 `5c25426c44a323b18e536af68993851464d84dd4da4eb8f44ba055c858667d70`。第二、三轮为两幅合法作品；它们虽然标题/源码相同，但平台消息身份不同，分别保留。首轮16,751字符回答中 `</think>` 与围栏在同一行，严格Markdown不会将其识别为作品；它只证明长原生回答保存，不证明大于16k合法作品回答的整链路，此项由后续票补充。

实际 Chromium154工作台经仅本机代理读取真实 Dify API（代理只在服务器加凭据，浏览器使用非秘密占位值），通过[完整历史结果](visualize/real-history.json)：

- 初次打开两幅作品均不自动创建frame；逐幅用户显式激活后运行，持续显示“运行状态未确认”。完整回归用键盘Enter激活原生按钮；首幅也在早先运行中以鼠标打开。第二幅鼠标定位在首幅测高变化时有测试时序抖动，不声称所有pointer时序已通过，04可继续覆盖。
- 滑块即时改变柱宽；暂停冻结时间；展开保留当前参数。刷新后重新取平台历史，内容摘要与身份一致，需再次显式查看，并恢复初值。
- 全新browser context没有此前cookie、session/local storage或浏览器缓存，仍从真实平台恢复两幅作品。切换到新会话后全部frame释放。
- 整个浏览器恢复流程没有任何POST，没有公网请求，没有页面脚本异常。未恢复Agent执行，也未改未知作品终态。
- 真实恢复暴露并修复了latest-state答复重复：已有原生历史时只恢复状态/pending，不把state.last_answer作为新助手消息插入；公开controller回归仍验证问卷恢复。
- 目检截图曾发现外层透明canvas露出白块，已为shell和作者文档root显式设置背景；复测背景及frame尺寸正确，重新执行实际shell七场景，HTTP/UDP仍为零。

[真实历史已打开且保留当前参数](screenshots/pi-visualize-real-history-opened.png)，[全新context恢复初始参数](screenshots/pi-visualize-real-history-fresh-context.png)。截图已逐张目检，最终无白块。原始临时脚本 `/tmp/pi-visualize-history-browser.cjs` 与原始结果 `/tmp/pi-visualize-real-history-results.json`；服务凭据不入库。

04仍负责历史分页、异常/断流组合及完整交付矩阵；本补充不冒称平台保存了Pi过程日志，也不冒称大于16k合法作品已通过全链路。
