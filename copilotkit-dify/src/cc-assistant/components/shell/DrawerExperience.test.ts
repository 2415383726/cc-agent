import { describe, expect, it, vi } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import DrawerExperience from './DrawerExperience.vue'

const copilotMocks = vi.hoisted(() => ({
  selectConversation: vi.fn(),
  state: {} as Record<string, any>,
}))

vi.mock('@copilotkit/vue/v2', async () => {
  const vue = await import('vue')
  return {
    CopilotChat: vue.defineComponent({
      name: 'CopilotChat',
      setup(_props, { slots }) {
        return () => vue.h('div', { class: 'mock-copilot-chat' }, [
          slots['message-view']?.({ messages: [], isRunning: false }),
          slots.input?.({
            modelValue: '',
            inputMode: 'input',
            isRunning: false,
            onUpdateModelValue: vi.fn(),
            onSubmitMessage: vi.fn(),
            onAddFile: vi.fn(),
            onStop: vi.fn(),
          }),
        ])
      },
    }),
    CopilotChatMessageView: vue.defineComponent({ setup: () => () => vue.h('div') }),
    useAgent: () => ({ agent: vue.ref({ threadId: 'thread-1', messages: [], state: copilotMocks.state, selectConversation: copilotMocks.selectConversation }) }),
    useCopilotKit: () => ({ copilotkit: vue.ref({ runAgent: vi.fn() }) }),
    useDefaultRenderTool: vi.fn(),
    useInterrupt: () => ({ slotProps: vue.ref(null) }),
    useRenderTool: vi.fn(),
  }
})

describe('DrawerExperience', () => {
  it('renders a recovered pending interaction without requiring a live stream event', async () => {
    copilotMocks.state.recovery = { question: { id: 'pending', question: '确认继续导出？',
      purpose: 'clarification', options: [{ label: '继续导出', value: 'allow_once' }] } }
    try {
      const html = await renderToString(createSSRApp(DrawerExperience, {
        activeView: 'chat', conversations: [], expectedThreadId: 'thread-1',
      }))
      expect(html).toContain('确认继续导出？')
      expect(html).toContain('继续导出')
    } finally {
      delete copilotMocks.state.recovery
    }
  })
  it('places the drawer home composer in a bottom input area without keyboard hint text', async () => {
    const app = createSSRApp(DrawerExperience, {
      activeView: 'home',
      conversations: [],
      expectedThreadId: 'thread-1',
      disabledReason: '请先在连接配置中填写 Base URL',
    })

    const html = await renderToString(app)

    expect(html).toContain('drawer-home__content')
    expect(html).toContain('drawer-home__bottom')
    expect(html).toContain('drawer-home-composer')
    expect(html).not.toContain('home-surface')
    expect(html).not.toContain('launcher-box')
    expect(html).not.toContain('assistant-composer__hint')
    expect(html).not.toContain('请先在连接配置中填写 Base URL')
    expect(html).not.toContain('Enter 发送，Shift + Enter 换行')
    expect(html).toContain('home-catalog-card')
    expect(html).not.toContain('home-catalog-panel--pills')
    expect(html).not.toContain('用户')
    expect(html.indexOf('home-catalog-panel')).toBeLessThan(html.indexOf('drawer-home__bottom'))
  })

  it('keeps the drawer home composer editable when Dify config is incomplete', async () => {
    const app = createSSRApp(DrawerExperience, {
      activeView: 'home',
      conversations: [],
      expectedThreadId: 'thread-1',
      disabledReason: '请先配置 Dify Base URL',
    })

    const html = await renderToString(app)

    const textareaMatch = html.match(/<textarea[^>]*>/)
    expect(textareaMatch?.[0]).toBeTruthy()
    expect(textareaMatch?.[0]).not.toContain('disabled')
  })

  it('loads pending history on the visible expected thread and reports completion', async () => {
    copilotMocks.selectConversation.mockResolvedValueOnce({
      loaded: true,
      messageCount: 2,
      hasMore: false,
    })
    const historyLoaded = vi.fn()
    const app = createSSRApp(DrawerExperience, {
      activeView: 'conversation',
      activeConversationId: 'conv_1',
      conversations: [],
      expectedThreadId: 'thread-1',
      pendingHistoryConversationId: 'conv_1',
      pendingHistoryLoadId: 7,
      onHistoryLoaded: historyLoaded,
    })

    await renderToString(app)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(copilotMocks.selectConversation).toHaveBeenCalledWith('conv_1', expect.any(Function))
    expect(historyLoaded).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 'conv_1',
      threadId: 'thread-1',
      requestId: 7,
    }))
  })
})
