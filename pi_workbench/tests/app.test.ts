import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockRejectedValue(new Error('no deployment config in test')),
  )
})

describe('static workbench replay', () => {
  it('renders a full process replay without a backend', async () => {
    window.history.replaceState({}, '', '/?replay=process')
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('lookup_order')
    expect(wrapper.text()).toContain('refund-policy')
    expect(wrapper.text()).toContain('上下文已压缩')
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).not.toContain('Dify not configured')
  })

  it('renders an actionable questionnaire in replay mode', async () => {
    window.history.replaceState({}, '', '/?replay=questionnaire')
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('退款信息')
    expect(wrapper.text()).toContain('要退款的是哪个订单？')
    expect(wrapper.text()).toContain('提交答案')
    const radios = wrapper.findAll('input[type="radio"]')
    await radios[0].setValue()
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    await wrapper.findAll('button').find((button) => button.text().includes('提交答案'))!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('问卷已提交')
    expect(wrapper.text()).toContain('已回答')
  })
})
