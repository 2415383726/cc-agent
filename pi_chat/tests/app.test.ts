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

describe('pi_chat 实时模式接线', () => {
  it('默认仍是回放模式；进入实时模式后显示连接表单与实时徽标', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('回放模式')
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('实时模式')
    // 侧栏切到实时控制器：无凭据时列表为空态
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('暂无历史会话')
  })

  it('连接表单校验：缺 API Key 提示；填写后提交触发会话列表刷新（失败有兜底态）', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
    const form = wrapper.find('[data-testid="connection-form"]')
    await form.find('[data-testid="connect-submit"]').trigger('click')
    expect(wrapper.text()).toContain('请填写服务地址与 API Key')
    expect(fetchSpy).not.toHaveBeenCalled()

    await form.find('[data-testid="form-api-key"]').setValue('app-test-key')
    await form.find('[data-testid="connect-submit"]').trigger('click')
    expect(fetchSpy).toHaveBeenCalled()
    await flushPromises()
    // fetch 桩始终拒绝：侧栏进入「加载失败重试」兜底态
    expect(wrapper.find('[data-testid="conversations-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('重试')
  })

  it('实时模式可切回回放模式，回放内容不受影响', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(true)
    await wrapper.find('[data-testid="back-replay"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('回放模式')
    expect(wrapper.text()).toContain('lookup_order')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(false)
  })

  it('实时模式 composer 可发送：点击发送即发起 Dify 请求', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
    await wrapper.find('[data-testid="form-api-key"]').setValue('app-test-key')
    await wrapper.find('[data-testid="connect-submit"]').trigger('click')
    await flushPromises()
    const textarea = wrapper.find('[data-zone="composer"] textarea')
    await textarea.setValue('你好，Dify')
    const send = wrapper.find('[data-zone="composer"] [data-testid="composer-send"]')
    expect(send.attributes('disabled')).toBeUndefined()
    await send.trigger('click')
    await flushPromises()
    // fetch 桩拒绝 → 控制器进入错误终态（transport_failed）
    expect(wrapper.text()).toContain('你好，Dify')
    expect(fetchSpy).toHaveBeenCalled()
  })
})
