/**
 * 自动吸底跟随（best-effort 平移自上游 ui-chat chat/use-scroll-follow.ts 的
 * ScrollFollow，MIT）。裁掉了 WeakMap 归主、原生动画 retarget 与 interrupt：
 * 回放/回放式直播里「读者向上滚离底部即暂停跟随，回到阈值内即恢复」的意图
 * 模型保持一致。Vue 接线在 useAutoScroll（组合式），这是框架无关 pure TS。
 */

export interface ViewportMetrics {
  readonly top: number
  readonly floor: number
  readonly height: number
}

export function scrollMetrics(element: HTMLElement): ViewportMetrics {
  const height = element.clientHeight
  return { top: element.scrollTop, height, floor: Math.max(0, element.scrollHeight - height) }
}

export class ScrollFollow {
  private following: boolean

  constructor(initial: boolean, private readonly threshold: number) {
    this.following = initial
  }

  get active(): boolean {
    return this.following
  }

  nearBottom(metrics: ViewportMetrics): boolean {
    return Math.abs(metrics.floor - metrics.top) <= this.threshold
  }

  setFollowing(active: boolean): void {
    this.following = active
  }

  /**
   * 采样一次滚动位置并更新跟随意图；`movedByReader` 缺省时与上次采样比较
   * （程序化滚动/原生动画进度不算读者移动）。
   */
  sample(metrics: ViewportMetrics, movedByReader?: boolean): boolean {
    const moved =
      movedByReader ??
      (this.lastTop === undefined || Math.abs(metrics.top - this.lastTop) > 0.5)
    this.lastTop = metrics.top
    if (moved) this.following = this.nearBottom(metrics)
    return this.active
  }

  /** 立即定位到目标偏移并采纳随后的跟随意图。 */
  jump(element: HTMLElement, metrics: ViewportMetrics, top: number): ViewportMetrics {
    const target = Math.max(0, Math.min(metrics.floor, top))
    element.scrollTop = target
    const landed: ViewportMetrics = { ...metrics, top: element.scrollTop }
    this.lastTop = landed.top
    this.following = this.nearBottom(landed)
    return landed
  }

  /** 跟随到测量底部；respect reduced motion 无需区分——立即定位。 */
  toBottom(element: HTMLElement, metrics: ViewportMetrics, behavior: 'instant' | 'smooth' = 'instant'): ViewportMetrics {
    this.following = true
    void behavior
    return this.jump(element, metrics, metrics.floor)
  }

  private lastTop: number | undefined = undefined
}

export function elementToMetrics(element: HTMLElement): ViewportMetrics {
  return scrollMetrics(element)
}
