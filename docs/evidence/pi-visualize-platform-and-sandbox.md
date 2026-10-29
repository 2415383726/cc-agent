# Pi 可视化：平台保存与浏览器隔离前置实验

日期：2026-10-29。基线：Pi v2 修复提交 `2226ec4`，功能规格见[规格 v1](../../.scratch/pi-visualize/spec.md)。本记录是独立实验，不能代替最终产品链路验收。

## 原生回答保存

独立 Dify 1.15.0 高级聊天应用使用固定合成作品，经 Code → Answer 输出两轮内容。同一会话中，SSE 回答、历史 API 回答及全新 HTTP 客户端重取内容逐字一致，不依赖浏览器缓存或 Pi 状态。

| 轮次 | Unicode 字符数 | UTF-8 字节数 | SSE/历史/新客户端 |
| --- | --- | --- | --- |
| 1 | 18,674 | 42,752 | 全部一致 |
| 2 | 4,054 | 8,352 | 全部一致 |

逐轮消息身份和内容摘要保存在[无密钥实验结果](pi-visualize/platform-roundtrip.json)。临时应用没有 Pi 节点、模型生成或可信 Pi 完成日志；第一轮 HTML 注释用于扩大体积。这证明平台可保存大于日志裁剪阈值的内容，不证明最终交互、技能生成或产品历史合并已经通过。没有修改原有验证应用。

## 沙箱不等于无网络

使用独立浏览器 profile 和本机 HTTP/UDP 接收端实测，避免把请求事件或拒绝响应误当成出站阻断。

- 只有脚本 iframe 沙箱和子 CSP，页面仍能通过自身导航发 HTTP 请求。
- `connect-src 'none'` 不阻断 WebRTC STUN UDP；Chromium 143/154 均收到真实包。
- 父页面的 `frame-src blob:` 可以阻断作者 blob frame 自导航，但不能单独解决 WebRTC。
- 专用静态 shell 的 HTTP 响应增加 `Connection-Allowlist: ()` 后，Chromium 154 阻断测试的 HTTP 与 STUN 渠道，主页面正常 fetch 仍成功。该策略也在本机普通 HTTP 非安全上下文验证；目标代理链仍须验收响应头保留。
- Chromium 143 忽略这个头，仍可发送 STUN。因此收到头本身不代表引擎支持，旧版/未知浏览器必须文字降级。
- 没有可靠的标准 JavaScript 支持反射。UA/响应头预检是兼容与部署门控，不是应对伪造 UA 或关闭安全特性的自定义浏览器的证明。标准浏览器按规范执行策略是支持前提。

原始合成实验结果：

- [Chromium 154：CSP、导航与 STUN](pi-visualize/pi-visualize-sandbox-results-154.0.8037.57.json)
- [Chromium 143：旧版反例](pi-visualize/pi-visualize-sandbox-results-143.0.7499.4.json)
- [Chromium 154：专用 shell 与主页面请求](pi-visualize/pi-visualize-static-shell-results-154.0.8037.57.json)
- [Chromium 154：普通 HTTP 非安全上下文](pi-visualize/pi-visualize-static-shell-results-154.0.8037.57-http-insecure.json)

实验脚本只创建临时本机 HTTP/UDP 接收端，产品交付不需要这些服务。最终产品须在实际宿主上重做关键浏览器回归；不能靠禁止某些 JavaScript 字符串或改写全局构造器替代网络边界。此处也不宣称浏览器任意脚本的强 CPU/内存配额或消灭所有侧信道。

## 实施决定

采用自包含的专用静态 shell，向该文档单独添加连接限制与严格 CSP；主工作台的 Dify 网络保持正常。作者内容在不授予同源能力的执行环境中运行，后续导航受外层策略限制。所有库和样式由受控宿主提供，shell 不自行从 CDN 或网络补齐。

支持正常 Chromium 154+，当前直接测试版本为 `154.0.8037.57`；154 之后按兼容性约定开放并持续回归。缺少部署策略、不支持浏览器或无法核验时，保持会话可读并显示作品文字替代，不允许手动忽略限制。

这进一步明确了规格中的无公网依赖、隔离和错误降级要求，不改变 Dify/Pi 宿主或增加常驻后端。

## 官方依据

- [Chrome：Connection Allowlists 发布与支持版本](https://developer.chrome.com/blog/connection-allowlist-announcement)
- [Chrome：限制出站连接的部署指南](https://developer.chrome.com/docs/modern-web-guidance/guides/security/restrict-outbound-connections)
- [WICG Connection Allowlists：响应头与继承模型](https://wicg.github.io/connection-allowlists/)
- [CSP3 frame-src：frame 导航边界](https://www.w3.org/TR/CSP3/#directive-frame-src)
