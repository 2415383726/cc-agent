/**
 * 平滑滚动兜底：部分内核（IAB WebKit）对 `scrollTo({behavior:'smooth'})`
 * 不执行程序化平滑——后台/隐藏渲染层会挂起滚动动画，个别内核则根本不实
 * 现。两种情况下 scrollTop 都纹丝不动，回到底部/回合跳转静默失效。
 * 此包装在平滑请求后做一次落点检查（rAF 链 + 150ms 定时器，先到先结算）：
 * 位移为零且未到目标则立即定位（instant 语义始终可用）。动画正常推进时
 * 该检查自动让路（150ms 内必有位移或已到目标）。
 */

export function smoothScrollTo(element: HTMLElement, top: number): void {
  const clamped = Math.max(0, Math.min(element.scrollHeight - element.clientHeight, top))
  const startTop = element.scrollTop
  if (startTop === clamped) return
  try {
    element.scrollTo({ top: clamped, behavior: 'smooth' })
  } catch {
    element.scrollTop = clamped
    return
  }
  let settled = false
  const settleInstant = (): void => {
    if (settled) return
    settled = true
    if (Math.abs(element.scrollTop - startTop) < 0.1 && element.scrollTop !== clamped) {
      element.scrollTop = clamped
    }
  }
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(settleInstant)))
  }
  if (typeof window !== 'undefined' && typeof window.setTimeout === 'function') {
    window.setTimeout(settleInstant, 150)
  } else {
    settleInstant()
  }
}
