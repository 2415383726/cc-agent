import { beforeAll, beforeEach, expect, it } from 'vitest'
import runtime from '../public/visualize/kit-1.js?raw'

const api = () => (window as any).PiViz
beforeAll(() => { new Function(runtime)() })
beforeEach(() => { document.body.innerHTML = '' })

it('keeps one selected tab and visible panel while keyboard users move through available tabs', () => {
  document.body.innerHTML = `<div data-viz-tabs><div role="tablist" aria-label="图解视图">
    <button role="tab" aria-controls="first">图解</button><button role="tab" aria-controls="skip" disabled>不可用</button><button role="tab" aria-controls="last">数据</button>
    </div><section id="first" role="tabpanel">本地图形</section><section id="skip" role="tabpanel">不可用</section><section id="last" role="tabpanel">数据表格</section></div>`
  api().init()
  const tabs = [...document.querySelectorAll<HTMLButtonElement>('[role=tab]')]
  expect(tabs.map((tab) => tab.getAttribute('aria-selected'))).toEqual(['true', 'false', 'false'])
  tabs[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
  expect(tabs[2].getAttribute('aria-selected')).toBe('true')
  expect(document.querySelector('#last')!.hasAttribute('hidden')).toBe(false)
  expect(document.querySelector('#first')!.hasAttribute('hidden')).toBe(true)
  tabs[2].dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }))
  expect(tabs[0].getAttribute('aria-selected')).toBe('true')
  tabs[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }))
  expect(tabs[2].getAttribute('aria-selected')).toBe('true')
})

it('shows supplementary tooltip text on focus and touch and dismisses with Escape', () => {
  document.body.innerHTML = '<button data-viz-tooltip="每分钟的平均到达人数" aria-describedby="units">到达速度说明</button><span id="units">人/分钟</span>'
  api().init()
  const button = document.querySelector('button')!
  button.dispatchEvent(new FocusEvent('focus'))
  const tooltip = document.querySelector<HTMLElement>('[role=tooltip]')!
  expect(tooltip.textContent).toBe('每分钟的平均到达人数')
  expect(tooltip.hidden).toBe(false)
  expect(button.getAttribute('aria-describedby')).toContain('units ')
  button.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  expect(tooltip.hidden).toBe(true)
  button.dispatchEvent(new PointerEvent('pointerdown', { pointerType: 'touch', bubbles: true }))
  expect(tooltip.hidden).toBe(false)
  document.body.dispatchEvent(new PointerEvent('pointerdown', { pointerType: 'touch', bubbles: true }))
  expect(tooltip.hidden).toBe(true)
})

it('exposes resolved theme colors for canvas and initializes real local icons', async () => {
  document.documentElement.style.setProperty('--viz-series-1', 'rgb(123, 104, 216)')
  document.documentElement.style.setProperty('--viz-bg', 'rgb(255, 255, 255)')
  expect(api().getTheme().colors.series1).toBe('rgb(123, 104, 216)')
  const { default: lucide } = await import('../public/visualize/vendor/lucide-1.17.0.js?raw')
  new Function(lucide)()
  document.body.innerHTML = '<button><i data-lucide="play" aria-hidden="true"></i>播放演示</button>'
  api().init()
  expect(document.querySelector('button svg')?.getAttribute('aria-hidden')).toBe('true')
  expect(document.querySelector('button')?.textContent).toContain('播放演示')
})
