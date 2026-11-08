import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
    expect(items[0].text()).toContain('4分钟')
    expect(items[1].text()).toContain('3小时')
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

  it('无控制器（组件级兜底）：显示未连接提示，新会话按钮禁用', async () => {
    const wrapper = mount(SidebarRail, { props: { controller: null } })
    expect(wrapper.find('[data-testid="disconnected-notice"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="new-conversation"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(false)
  })
})

describe('SidebarRail 折叠（对齐 dsh：淡出卸载 → 56px 导轨 → 展开淡入）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('折叠开关：点击上抛 toggle，aria-expanded 表达当前态', async () => {
    const controller = fakeController()
    const wrapper = mount(SidebarRail, { props: { controller } })
    const toggle = wrapper.find('[data-testid="sidebar-toggle"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.attributes('aria-expanded')).toBe('true')
    await toggle.trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })

  it('折叠相位：宽内容淡出期间仍挂载，150ms settle 后卸载列表、保留导轨控件', async () => {
    const controller = fakeController()
    const wrapper = mount(SidebarRail, { props: { controller } })
    await wrapper.setProps({ collapsed: true })
    // 淡出相位（settled=false）：列表仍挂载（冻结宽度、整列淡出）
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(true)
    vi.advanceTimersByTime(150)
    await wrapper.vm.$nextTick()
    // settle：列表卸载，导轨只剩折叠开关 + 新会话图标
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="sidebar-toggle"]').exists()).toBe(true)
    const newSession = wrapper.find('[data-testid="new-conversation"]')
    expect(newSession.exists()).toBe(true)
    expect(newSession.attributes('aria-label')).toBe('新会话')
  })

  it('展开恢复：列表重新挂载，aria-expanded 翻转', async () => {
    const controller = fakeController()
    const wrapper = mount(SidebarRail, { props: { controller, collapsed: true } })
    vi.advanceTimersByTime(150)
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(false)
    await wrapper.setProps({ collapsed: false })
    expect(wrapper.find('[data-testid="sidebar-toggle"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(true)
  })

  it('冷折叠渲染（初始即 collapsed，settle 后）：无宽内容、无 railIn 动画相位', async () => {
    const controller = fakeController()
    mount(SidebarRail, { props: { controller, collapsed: true } })
    // 冷渲染不经过淡出：settled 即刻为真（初始 collapsed 直接导轨态）
    vi.advanceTimersByTime(150)
    const wrapper = mount(SidebarRail, { props: { controller, collapsed: true } })
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(false)
  })
})

describe('AppShell 折叠轨道（280 ↔ 56）', () => {
  it('展开态：280px 轨道，无折叠标注', async () => {
    const { default: AppShell } = await import('../src/shell/AppShell.vue')
    const wrapper = mount(AppShell, { props: { sidebarCollapsed: false } })
    const frame = wrapper.find('[class*="frame"]')
    expect(frame.attributes('style')).toContain('280px')
    expect(frame.attributes('data-sidebar-collapsed')).toBeUndefined()
    expect(wrapper.find('[data-zone="sidebar"]').exists()).toBe(true)
  })

  it('折叠态：56px 轨道 + data-sidebar-collapsed 标注', async () => {
    const { default: AppShell } = await import('../src/shell/AppShell.vue')
    const wrapper = mount(AppShell, { props: { sidebarCollapsed: true } })
    const frame = wrapper.find('[class*="frame"]')
    expect(frame.attributes('style')).toContain('56px')
    expect(frame.attributes('data-sidebar-collapsed')).toBeDefined()
  })

  it('折叠切换期间挂 data-animating（轨道缓动），320ms 后摘除', async () => {
    vi.useFakeTimers()
    try {
      const { default: AppShell } = await import('../src/shell/AppShell.vue')
      const wrapper = mount(AppShell, { props: { sidebarCollapsed: false } })
      await wrapper.setProps({ sidebarCollapsed: true })
      expect(wrapper.find('[class*="frame"]').attributes('data-animating')).toBeDefined()
      vi.advanceTimersByTime(320)
      await wrapper.vm.$nextTick()
      expect(wrapper.find('[class*="frame"]').attributes('data-animating')).toBeUndefined()
    } finally {
      vi.useRealTimers()
    }
  })
})
