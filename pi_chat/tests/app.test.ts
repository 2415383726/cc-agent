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
    // 票据 05 后问卷场景渲染完整问卷卡：第 1 题眉题（question.header）与题干可见。
    expect(wrapper.text()).toContain('订单')
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

  it('问卷回放可完整交互：作答、翻页、跳过、提交全程本地闭环', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const select = wrapper.find('select')
    await select.setValue('questionnaire')
    await flushPromises()

    // 第 1 题（必填单选）：选第二个选项，自动翻页。
    await wrapper.findAll('[role="radio"]')[1].trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('2 / 3')
    // 第 2 题（multi，min1/max2）：勾选两项后翻页。
    const checkboxes = wrapper.findAll('[role="checkbox"]')
    await checkboxes[0].trigger('click')
    await checkboxes[1].trigger('click')
    await wrapper.find('[data-testid="question-primary"]').trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('3 / 3')
    // 第 3 题（text 选填）：跳过即提交。
    await wrapper.findAll('button').find((button) => button.text() === '跳过')!.trigger('click')

    // 回放闭环：question.answered 落记录 → 卡片只读回显 + 用户答复气泡 + 回放终态。
    await flushPromises()
    expect(wrapper.find('[data-testid="question-review-status"]').text()).toBe('已回答')
    expect(wrapper.text()).toContain('谢谢，问卷已提交')
    expect(wrapper.text()).toContain('订单 B-2099')
    expect(wrapper.text()).toContain('到货损坏, 商品错误')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('问卷取消走回放本地闭环并渲染取消态', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const select = wrapper.find('select')
    await select.setValue('questionnaire')
    await flushPromises()
    await wrapper.find('[data-testid="card-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="question-review-status"]').text()).toBe('已取消')
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
