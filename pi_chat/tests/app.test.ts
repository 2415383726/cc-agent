import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'

const fetchSpy = vi.fn(() => Promise.reject(new Error('回放模式不允许网络请求')))

beforeEach(() => {
  fetchSpy.mockClear()
  vi.stubGlobal('fetch', fetchSpy)
  window.history.replaceState({}, '', '/')
})

describe('pi_chat replay shell', () => {
  it('默认渲染 process 场景，回放标注可见，且零网络请求', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('回放模式')
    expect(wrapper.text()).toContain('lookup_order')
    expect(wrapper.text()).toContain('refund-policy')
    expect(wrapper.text()).toContain('已完成')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('三个场景都在回放清单中可选，切换即渲染对应场景', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const select = wrapper.find('select')
    const optionText = select.findAll('option').map((option) => option.text())
    expect(optionText.some((text) => text.includes('工具、技能与压缩'))).toBe(true)
    expect(optionText.some((text) => text.includes('问卷暂停与答复'))).toBe(true)
    expect(optionText.some((text) => text.includes('工具审批与未知写操作'))).toBe(true)

    await select.setValue('questionnaire')
    await flushPromises()
    expect(wrapper.text()).toContain('退款信息')
    expect(wrapper.text()).toContain('要退款的是哪个订单？')

    await select.setValue('approval')
    await flushPromises()
    expect(wrapper.text()).toContain('delete_record')
    expect(wrapper.text()).toContain('等待审批')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('?replay=<id> URL 参数选择对应场景', async () => {
    window.history.replaceState({}, '', '/?replay=approval')
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('delete_record')
    expect(wrapper.text()).toContain('等待审批')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('应用壳为三区布局：侧栏轨道、时间线滚动区、composer 区', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('[data-zone="sidebar"]').exists()).toBe(true)
    const timeline = wrapper.find('[data-zone="timeline"]')
    expect(timeline.exists()).toBe(true)
    expect(timeline.find('[aria-label="会话记录"]').exists()).toBe(true)
    const composer = wrapper.find('[data-zone="composer"]')
    expect(composer.exists()).toBe(true)
    expect(wrapper.text()).toContain('新会话')
    expect(wrapper.text()).toContain('回放模式')
  })

  it('composer 可输入文本，发送为禁用占位，输入不发网络请求', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const textarea = wrapper.find('[data-zone="composer"] textarea')
    expect(textarea.exists()).toBe(true)
    expect(textarea.attributes('disabled')).toBeUndefined()
    await textarea.setValue('你好，pi chat')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('你好，pi chat')
    expect(wrapper.text()).not.toContain('回放模式不允许网络请求')

    const send = wrapper.find('[data-zone="composer"] [data-testid="composer-send"]')
    expect(send.exists()).toBe(true)
    expect(send.attributes('disabled')).toBeDefined()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
