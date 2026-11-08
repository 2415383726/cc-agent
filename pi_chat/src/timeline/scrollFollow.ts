/**
 * 自动吸底跟随（平移自上游 ui-chat chat/use-scroll-follow.ts 的 ScrollFollow，
 * MIT）。裁掉 WeakMap 归主（bind/forElement，Vue 接线自行持有一份）；意图
 * 模型逐条保留：
 * - 读者向上滚离底部即暂停跟随，回到阈值内（FOLLOW_THRESHOLD）即恢复；
 * - 原生动画进度不算读者移动（animating 期间 sample 保留意图）；
 * - 内容增长用 instant 跟随；动画进行中的增长请求 retarget 而不切断；
 * - 用户点击「回到底部」用 smooth，reduced motion 退回立即定位；
 * - 读者手势（wheel/touchstart）先 interrupt 未竟动画，再由实际移动改写意图；
 * - scrollend（或降级防抖）settle：停在目标外则释放跟随意图。
 * Vue 接线在 App.vue（滚动监听 + 条目增长 watcher），这是框架无关 pure TS。
 */

import { smoothScrollTo } from './smoothScroll'

export interface ViewportMetrics {
  readonly top: number
  readonly floor: number
  readonly height: number
}

export function scrollMetrics(element: HTMLElement): ViewportMetrics {
  const height = element.clientHeight
  return { top: element.scrollTop, height, floor: Math.max(0, element.scrollHeight - height) }
}

export function elementToMetrics(element: HTMLElement): ViewportMetrics {
  return scrollMetrics(element)
}

export class ScrollFollow {
  private following: boolean
  private target: number | null = null
  private lastTop: number | undefined = undefined

  constructor(
    initial: boolean,
    private readonly threshold: number,
  ) {
    this.following = initial
  }

  get active(): boolean {
    return this.following
  }

  /** 未竟的原生跟随动画（有 outstanding 目标偏移）。 */
  get animating(): boolean {
    return this.target !== null
  }

  nearBottom(metrics: ViewportMetrics): boolean {
    return Math.abs(metrics.floor - metrics.top) <= this.threshold
  }

  setFollowing(active: boolean): void {
    this.following = active
    if (!active) this.target = null
  }

  /** 采纳下一次可见布局为新的读者位置（切换会话/重置意图）。 */
  reset(): void {
    this.setFollowing(false)
    this.lastTop = undefined
  }

  /**
   * 采样一次滚动位置并更新跟随意图；`movedByReader` 缺省时与上次采样比较。
   * 原生动画进行中不采纳（动画进度不是读者移动）。
   */
  sample(metrics: ViewportMetrics, movedByReader?: boolean): boolean {
    const moved =
      movedByReader ??
      (this.lastTop === undefined || Math.abs(metrics.top - this.lastTop) > 0.5)
    this.lastTop = metrics.top
    if (!this.animating && moved) this.following = this.nearBottom(metrics)
    return this.active
  }

  /** 结算原生滚动：停在目标之外（阈值外）则释放跟随意图。 */
  settle(metrics: ViewportMetrics): boolean {
    const target = this.target
    this.target = null
    return this.sample(
      metrics,
      target === null ? undefined : Math.abs(metrics.top - Math.min(target, metrics.floor)) > this.threshold,
    )
  }

  /** 立即定位到目标偏移并采纳随后的跟随意图；动画中的 jump 用 instant 切断。 */
  jump(element: HTMLElement, metrics: ViewportMetrics, top: number): ViewportMetrics {
    const animated = this.animating
    this.target = null
    const clamped = Math.max(0, Math.min(metrics.floor, top))
    if (animated) element.scrollTo({ top: clamped, behavior: 'instant' })
    else if (clamped !== metrics.top) element.scrollTop = clamped
    const landed: ViewportMetrics = { ...metrics, top: element.scrollTop }
    this.lastTop = landed.top
    this.following = this.nearBottom(landed)
    return landed
  }

  /**
   * 跟随到测量底部。`instant`（内容增长）：动画中 retarget，静止且近底/远则
   * 立即定位；`smooth`（用户点击回到底部）：reduced motion 退回立即定位，
   * 否则平滑滚动到目标。`respect reduced motion 无需区分——立即定位` 的旧行为
   * 已对齐上游：只有 smooth 请求在 reduced motion 下退化为 jump。
   */
  toBottom(
    element: HTMLElement,
    metrics: ViewportMetrics,
    behavior: 'instant' | 'smooth' = 'instant',
  ): ViewportMetrics {
    this.following = true
    if (metrics.top === metrics.floor) return this.jump(element, metrics, metrics.floor)
    if (behavior === 'instant' && this.animating) {
      // 内容增长打断了进行中的动画：retarget 到新底而不是切断到底。
      if (this.target !== metrics.floor) {
        this.target = metrics.floor
        smoothScrollTo(element, metrics.floor)
      }
      return metrics
    }
    if (behavior === 'instant' || (!this.animating && this.nearBottom(metrics))) {
      return this.jump(element, metrics, metrics.floor)
    }
    if (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return this.jump(element, metrics, metrics.floor)
    }
    if (this.target === null) {
      this.target = metrics.floor
      smoothScrollTo(element, metrics.floor)
    }
    return metrics
  }

  /** 读者手势前取消未竟原生动画；此后的实际移动才改写跟随意图。 */
  interrupt(element: HTMLElement, metrics: ViewportMetrics): void {
    if (!this.animating) return
    this.target = null
    this.lastTop = metrics.top
    element.scrollTo({ top: metrics.top, behavior: 'instant' })
  }
}
