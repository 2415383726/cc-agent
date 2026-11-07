// check:static 的模式层：给定产物文本，返回禁用模式的命中清单。
// 自 pi_workbench/scripts/check-static.mjs 机制照搬；文件遍历、哈希与报告落盘在 check-static.mjs（CLI）。
// 不变量：构建产物零硬编码外链 / 零追踪器 / 零旧后端与 SDK 残留（见 pi_chat/README.md）。
export const FORBIDDEN = [
  /\bsrc\s*=\s*["']https?:/i,
  /\bhref\s*=\s*["']https?:/i,
  /url\(\s*["']?https?:/i,
  /\bfetch\(\s*["'`]https?:/i,
  /\bimport\(\s*["'`]https?:/i,
  /wss?:\/\//i,
  /pi-coding-agent/i,
  /@earendil-works/i,
  /\/api\/pi\//i,
  /fonts\.googleapis\.com/i,
  /cdn\.jsdelivr\.net/i,
  /unpkg\.com/i,
  /google-analytics/i,
]

export const TEXT_EXTENSIONS = new Set(['.html', '.js', '.css', '.json', '.svg', '.txt', '.map'])

/** 扫描一段产物文本，返回 [{ pattern, match }]；match 截断到 80 字符。 */
export function scanText(text) {
  const violations = []
  for (const pattern of FORBIDDEN) {
    const match = text.match(pattern)
    if (match) violations.push({ pattern: String(pattern), match: match[0].slice(0, 80) })
  }
  return violations
}
