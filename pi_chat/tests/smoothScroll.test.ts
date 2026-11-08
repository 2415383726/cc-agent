import { afterEach, describe, expect, it, vi } from 'vitest'
import { smoothScrollTo } from '../src/timeline/smoothScroll'

/*
 * smoothScrollTo：IAB WebKit 内核接受 scrollTo({behavior:'smooth'}) 却不执
 * 行程序化平滑——回到底部/回合跳转会静默失效。包装器三帧内检测零位移并退
 * 化为瞬时定位；真平滑内核（首帧有位移）不受影响。
 */

function makeScroller(height: number, view: number): HTMLElement {
  const el = document.createElement('div')
  Object.defineProperty(el, 'scrollHeight', { value: height, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: view, configurable: true })
  document.body.appendChild(el)
  return el
}

describe('smoothScrollTo 内核兜底', () => {
  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('平滑被忽略的内核：落点检查零位移 → 退化为瞬时定位', async () => {
    vi.useFakeTimers()
    const el = makeScroller(2000, 500)
    el.scrollTo = () => {} // 模拟内核：接受调用但不滚动
    const rafCallbacks: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      rafCallbacks.push(cb)
      return rafCallbacks.length
    })
    smoothScrollTo(el, 1500)
    expect(el.scrollTop).toBe(0)
    // 路径 A：rAF 链逐帧驱动（嵌套注册的回调随执行逐层入队）
    let guard = 0
    while (rafCallbacks.length > 0 && el.scrollTop === 0 && guard++ < 10) {
      rafCallbacks.shift()!(guard * 16)
    }
    expect(el.scrollTop).toBe(1500)
  })

  it('rAF 挂起（隐藏渲染层）时 150ms 定时器兜底', () => {
    vi.useFakeTimers()
    const el = makeScroller(2000, 500)
    el.scrollTo = () => {} // 动画被挂起：调用后零位移
    vi.stubGlobal('requestAnimationFrame', () => 1) // 永不回调
    smoothScrollTo(el, 1500)
    expect(el.scrollTop).toBe(0)
    vi.advanceTimersByTime(150)
    expect(el.scrollTop).toBe(1500)
  })

  it('平滑生效的内核：首帧已有位移 → 不干预', () => {
    const el = makeScroller(2000, 500)
    el.scrollTo = ((options: ScrollToOptions) => {
      // 模拟真内核：smooth 第一帧推进一段
      el.scrollTop = (options.top as number) * 0.3
    }) as typeof el.scrollTo
    smoothScrollTo(el, 1500)
    expect(el.scrollTop).toBe(450)
  })

  it('目标越界时 clamp 到滚动范围；scrollTo 抛错时直接瞬时定位', () => {
    const el = makeScroller(2000, 500)
    el.scrollTo = () => {
      throw new Error('unsupported signature')
    }
    smoothScrollTo(el, 99999)
    expect(el.scrollTop).toBe(1500)
  })
})
