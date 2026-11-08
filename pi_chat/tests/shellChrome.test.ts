import { describe, expect, it, vi, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import ConversationColumn from '../src/shell/ConversationColumn.vue'
import SidebarRail from '../src/shell/SidebarRail.vue'

/*
 * 壳层细节（对齐 dsh-web 的第 2 轮迭代）：回到底部浮动钮、导轨态鲸尾标
 * 互换、quietBars 滚动条跟随与列表底部渐隐。CSS-module 类名经 hash，
 * 断言结构存在与事件语义，样式规则由 vendored 模块保证。
 */

describe('ConversationColumn 回到底部浮动钮', () => {
  it('toBottomVisible=true 渲染 toBottomSlot，点击发出 to-bottom', async () => {
    const wrapper = mount(ConversationColumn, {
      props: { title: 'T', toBottomVisible: true, railItems: [] },
    })
    const slot = wrapper.find('[data-testid="to-bottom-slot"]')
    expect(slot.exists()).toBe(true)
    const button = wrapper.find('[data-testid="to-bottom"]')
    expect(button.attributes('aria-label')).toBe('回到底部')
    expect(button.find('svg').exists()).toBe(true)
    await button.trigger('click')
    expect(wrapper.emitted('toBottom')).toHaveLength(1)
  })

  it('toBottomVisible=false（跟随中）不渲染浮动钮', () => {
    const wrapper = mount(ConversationColumn, {
      props: { title: 'T', toBottomVisible: false, railItems: [] },
    })
    expect(wrapper.find('[data-testid="to-bottom-slot"]').exists()).toBe(false)
  })

  it('跟随中滚动体带 data-chat-following-tail（禁用 UA 滚动锚定的锚点）', async () => {
    const following = mount(ConversationColumn, { props: { toBottomVisible: false, railItems: [] } })
    expect(following.find('[data-chat-following-tail]').exists()).toBe(true)
    const detached = mount(ConversationColumn, { props: { toBottomVisible: true, railItems: [] } })
    expect(detached.find('[data-chat-following-tail]').exists()).toBe(false)
  })
})

describe('SidebarRail 导轨细节（quietBars / 鲸尾标 / scrollFade）', () => {
  it('折叠导轨态：静止渲染鲸尾标 + panel 图标（悬停互换由 vendored CSS 接管）', () => {
    const wrapper = mount(SidebarRail, { props: { collapsed: true } })
    expect(wrapper.find('[data-testid="sidebar-toggle"] .railMark, [data-testid="sidebar-toggle"] [class*="railMark"]').exists() || wrapper.html().includes('railMark'))
      .toBe(true)
    // 根类含 quietBars（指针未进入）
    expect(wrapper.attributes('class')).toContain('quietBars')
  })

  it('展开态：scrollFade 渐隐 span 渲染在 scrollRegion 内', () => {
    const wrapper = mount(SidebarRail, { props: { collapsed: false } })
    expect(wrapper.html()).toContain('scrollFade')
  })

  it('指针进入取消 quietBars；离开后驻留 2s 才收回（linger 语义）', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(SidebarRail, { props: { collapsed: false } })
      expect(wrapper.attributes('class')).toContain('quietBars')
      await wrapper.trigger('pointerenter')
      expect(wrapper.attributes('class')).not.toContain('quietBars')
      await wrapper.trigger('pointerleave')
      // linger：滚动条在指针离开后再驻留 SCROLLBAR_LINGER_MS。
      expect(wrapper.attributes('class')).not.toContain('quietBars')
      vi.advanceTimersByTime(2001)
      await nextTick()
      expect(wrapper.attributes('class')).toContain('quietBars')
      // 驻留期内指针返回：取消待决隐藏，bars 保持显现。
      await wrapper.trigger('pointerenter')
      expect(wrapper.attributes('class')).not.toContain('quietBars')
    } finally {
      vi.useRealTimers()
    }
  })

  afterEach(() => {
    vi.useRealTimers()
  })
})
