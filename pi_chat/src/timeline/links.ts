/**
 * 输出文件链接的协议护栏（P3-3）：只放行 http/https 与站内相对引用，拒绝
 * javascript:/data:/blob: 等一切可执行或非常规协议。输出文件 URL 来自 Dify
 * 平台消息与远端 MCP 产物，属于不可信输入——绑定到 href 前先过这道闸，
 * 拒绝的链接退化为纯文本文件名（不渲染 <a>）。
 */

/** 有 scheme 的绝对 URL；`javascript:...`、`data:...` 都会被它识别。 */
const SCHEME = /^[a-zA-Z][a-zA-Z0-9+.-]*:/

/**
 * 返回可安全绑定到 href 的值；不可信/不可识别的输入返回 null。
 * - http:/https: 绝对地址 → 原样放行
 * - 无 scheme 的相对引用（/path、./path、path、#frag、//host）→ 放行
 *   （协议相对地址继承页面协议，仍是 http(s) 轴）
 * - 其余 scheme（javascript:/data:/blob:/...）→ 拒绝
 */
export function safeOutputHref(url: unknown): string | null {
  const value = String(url ?? '').trim()
  if (!value) return null
  const scheme = SCHEME.exec(value)?.[0]
  if (!scheme) return value // 无 scheme → 相对引用
  return /^https?:$/i.test(scheme) ? value : null
}
