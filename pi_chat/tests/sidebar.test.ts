import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { WorkbenchController } from '../src/dify/controller'
import type { UiState } from '../src/dify/controller'
import SidebarRail from '../src/shell/SidebarRail.vue'

const NOW = Date.now()
const MIN = 60_000
const HOUR = 3_600_000

function fakeUi(overrides: Partial<UiState> = {}): UiState {
  return {
    running: false,
    stopping: false,
    stopRequested: false,
    connected: true,
    error: '',
    conversationId: 'c1',
    conversations: [
      { id: 'c1', name: '问候', updatedAt: NOW - 4 * MIN },
      { id: 'c2', name: '数据整理', updatedAt: NOW - 3 * HOUR },
    ],
    conversationsError: '',
    actionNote: '',
    loadingHistory: false,
    hasMore: false,
    firstId: '',
    stoppedNote: '',
    ...overrides,
  }
}

function fakeController(ui: UiState = fakeUi()): WorkbenchController {
  return {
    view: { entries: [], warnings: [], outputs: [] },
    ui,
    send: vi.fn(async () => {}),
    stop: vi.fn(async () => {}),
    upload: vi.fn(async () => null),
    submitAnswers: vi.fn(async () => {}),
    cancelQuestion: vi.fn(async () => {}),
    submitApproval: vi.fn(async () => {}),
    refreshConversations: vi.fn(async () => {}),
    loadConversation: vi.fn(async () => {}),
    newConversation: vi.fn(),
    renameConversation: vi.fn(async () => true),
    deleteConversation: vi.fn(async () => true),
    updateConfig: vi.fn(),
  } as unknown as WorkbenchController
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SidebarRail 侧栏会话列表', () => {
  it('渲染会话条目：标题、相对时间与当前项高亮', () => {
    const controller = fakeController()
    const wrapper = mount(SidebarRail, { props: { controller } })
    const items = wrapper.findAll('[data-testid="conversation-item"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('问候')
    expect(items[0].text()).toContain('4分钟前')
    expect(items[1].text()).toContain('3小时前')
    expect(items[0].attributes('aria-selected')).toBe('true')
    expect(items[1].attributes('aria-selected')).toBe('false')
  })

  it('点击条目切换会话；新会话按钮调用 newConversation', async () => {
    const controller = fakeController()
    const wrapper = mount(SidebarRail, { props: { controller } })
    await wrapper.findAll('[data-testid="conversation-item"]')[1].trigger('click')
    expect(controller.loadConversation).toHaveBeenCalledWith('c2')
    await wrapper.find('[data-testid="new-conversation"]').trigger('click')
    expect(controller.newConversation).toHaveBeenCalledTimes(1)
  })

  it('重命名：内联输入框预填当前名，Enter 提交裁剪后的名字', async () => {
    const controller = fakeController()
    const wrapper = mount(SidebarRail, { props: { controller } })
    const row = wrapper.findAll('[data-testid="conversation-item"]')[0]
    await row.find('[data-testid="rename-button"]').trigger('click')
    const input = row.find('[data-testid="rename-input"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLInputElement).value).toBe('问候')
    await input.setValue('  新问候  ')
    await input.trigger('keydown.enter')
    await flushPromises()
    expect(controller.renameConversation).toHaveBeenCalledWith('c1', '新问候')
    expect(wrapper.find('[data-testid="rename-input"]').exists()).toBe(false)
  })

  it('重命名：Escape 取消且不提交', async () => {
    const controller = fakeController()
    const wrapper = mount(SidebarRail, { props: { controller } })
    const row = wrapper.findAll('[data-testid="conversation-item"]')[0]
    await row.find('[data-testid="rename-button"]').trigger('click')
    await row.find('[data-testid="rename-input"]').trigger('keydown.esc')
    expect(controller.renameConversation).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="rename-input"]').exists()).toBe(false)
  })

  it('删除：先内联确认，确认后才调用删除', async () => {
    const controller = fakeController()
    const wrapper = mount(SidebarRail, { props: { controller } })
    const row = wrapper.findAll('[data-testid="conversation-item"]')[0]
    await row.find('[data-testid="delete-button"]').trigger('click')
    expect(wrapper.find('[data-testid="confirm-delete"]').exists()).toBe(true)
    expect(controller.deleteConversation).not.toHaveBeenCalled()
    await wrapper.find('[data-testid="confirm-delete-no"]').trigger('click')
    expect(controller.deleteConversation).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="confirm-delete"]').exists()).toBe(false)
    await row.find('[data-testid="delete-button"]').trigger('click')
    await wrapper.find('[data-testid="confirm-delete-yes"]').trigger('click')
    await flushPromises()
    expect(controller.deleteConversation).toHaveBeenCalledWith('c1')
    expect(wrapper.find('[data-testid="confirm-delete"]').exists()).toBe(false)
  })

  it('列表加载失败：显示加载失败与重试，重试调用 refreshConversations', async () => {
    const controller = fakeController(fakeUi({ conversations: [], conversationsError: 'Unauthorized' }))
    const wrapper = mount(SidebarRail, { props: { controller } })
    expect(wrapper.find('[data-testid="conversations-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('加载失败')
    await wrapper.find('[data-testid="conversations-retry"]').trigger('click')
    expect(controller.refreshConversations).toHaveBeenCalledTimes(1)
  })

  it('空列表显示暂无历史会话', () => {
    const controller = fakeController(fakeUi({ conversations: [] }))
    const wrapper = mount(SidebarRail, { props: { controller } })
    expect(wrapper.text()).toContain('暂无历史会话')
  })

  it('操作失败提示（actionNote）可见', () => {
    const controller = fakeController(fakeUi({ actionNote: '重命名失败：Permission Denied' }))
    const wrapper = mount(SidebarRail, { props: { controller } })
    expect(wrapper.find('[data-testid="action-note"]').text()).toContain('重命名失败')
  })

  it('无控制器（回放基线）：显示回放提示，新会话按钮禁用', async () => {
    const wrapper = mount(SidebarRail, { props: { controller: null } })
    expect(wrapper.find('[data-testid="replay-notice"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="new-conversation"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(false)
  })
})
