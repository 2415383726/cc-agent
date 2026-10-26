import { describe, expect, it, vi } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import CcDifyAssistant from './CcDifyAssistant.vue'
import { createAssistantLauncher } from '../../lib/assistantLauncher'

vi.mock('@copilotkit/vue/v2', async () => {
  const vue = await import('vue')
  return {
    CopilotKitProvider: vue.defineComponent({
      name: 'CopilotKitProvider',
      props: ['renderActivityMessages'],
      setup(_props, { slots }) {
        return () => vue.h('div', { class: 'mock-copilot-provider' }, slots.default?.())
      },
    }),
    CopilotChatConfigurationProvider: vue.defineComponent({
      name: 'CopilotChatConfigurationProvider',
      props: ['threadId'],
      setup(_props, { slots }) {
        return () => vue.h('div', { class: 'mock-chat-config' }, slots.default?.())
      },
    }),
    CopilotChat: vue.defineComponent({
      name: 'CopilotChat',
      setup() {
        return () => vue.h('div', { class: 'mock-copilot-chat' })
      },
    }),
    createA2UIMessageRenderer: vi.fn(() => ({ activityType: 'a2ui.message' })),
    useAgent: () => ({ agent: vue.ref({ threadId: 'thread-1', messages: [], addMessage: vi.fn(), selectConversation: vi.fn() }) }),
    useCopilotKit: () => ({ copilotkit: vue.ref({ runAgent: vi.fn() }) }),
    useDefaultRenderTool: vi.fn(),
    useInterrupt: () => ({ slotProps: vue.ref(null) }),
    useRenderTool: vi.fn(),
  }
})

describe('CcDifyAssistant', () => {
  it('renders only the assistant shell without the demo connection panel or outer home surface', async () => {
    const app = createSSRApp(CcDifyAssistant, {
      dify: {
        baseUrl: 'https://dify.example/v1',
        apiKey: 'app-xxx',
        user: 'user-1',
        token: 'agent-token',
      },
      catalog: {
        skills: [{ name: 'meeting-notes', label: '会议纪要', description: '整理会议记录' }],
        suggestedQuestions: [],
      },
      title: '系统助手',
      storageKeyPrefix: 'cadre-system-assistant',
    })

    const html = await renderToString(app)

    expect(html).toContain('mock-copilot-provider')
    expect(html).toContain('系统助手')
    expect(html).toContain('drawer-fab')
    expect(html).not.toContain('连接配置')
    expect(html).not.toContain('config-panel')
    expect(html).not.toContain('home-surface')
    expect(html).not.toContain('launcher-box')
  })

  it('launches with a fresh conversation and slash-prefixed selected skill text', async () => {
    const calls: string[] = []
    const freshAgent = {
      addMessage: vi.fn(() => calls.push('fresh.addMessage')),
    }
    const staleAgent = {
      addMessage: vi.fn(() => calls.push('stale.addMessage')),
    }
    const launcher = createAssistantLauncher({
      getAgent: () => staleAgent,
      getDisabledReason: () => '',
      openDrawer: () => calls.push('openDrawer'),
      prepareConversation: async () => {
        calls.push('prepareConversation')
        return freshAgent
      },
      runAgent: async () => {
        calls.push('runAgent')
      },
    })

    const submitted = await launcher.launchWithMessage('整理下面的会议内容', {
      selectedSkill: {
        kind: 'skill',
        name: 'meeting-notes',
        label: '会议纪要',
        description: '',
        category: '办公',
      },
    })

    expect(submitted).toBe(true)
    expect(staleAgent.addMessage).not.toHaveBeenCalled()
    expect(freshAgent.addMessage).toHaveBeenCalledWith(expect.objectContaining({
      role: 'user',
      content: '/meeting-notes 整理下面的会议内容',
    }))
    expect(calls).toEqual(['prepareConversation', 'openDrawer', 'fresh.addMessage', 'runAgent'])
  })
})
