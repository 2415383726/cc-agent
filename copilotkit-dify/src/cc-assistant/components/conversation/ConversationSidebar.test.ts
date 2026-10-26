import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import ConversationSidebar from './ConversationSidebar.vue'

describe('ConversationSidebar', () => {
  const conversations = [
    {
      id: 'conv_1',
      name: 'Plan Review',
      status: 'normal',
      introduction: '',
      inputs: {},
      createdAt: 1780740000,
      updatedAt: 1780740000,
    },
  ]

  it('renders a collapsed icon rail by default when collapsed is true', async () => {
    const app = createSSRApp(ConversationSidebar, {
      activeView: 'home',
      activeConversationId: '',
      conversations,
      loading: false,
      hasMore: true,
      search: '',
      collapsed: true,
    })

    const html = await renderToString(app)

    expect(html).toContain('conversation-sidebar--collapsed')
    expect(html).toContain('conversation-sidebar__rail-button')
    expect(html).toContain('aria-label="打开侧边栏"')
    expect(html).toContain('aria-label="新聊天"')
    expect(html).toContain('aria-label="搜索聊天"')
    expect(html).toContain('aria-label="最近聊天"')
    expect(html).not.toContain('conversation-sidebar__list')
    expect(html).not.toContain('Plan Review')
  })

  it('renders expanded navigation, search, and Dify conversations', async () => {
    const app = createSSRApp(ConversationSidebar, {
      activeView: 'conversation',
      activeConversationId: 'conv_1',
      conversations,
      loading: false,
      hasMore: true,
      search: '',
      collapsed: false,
    })

    const html = await renderToString(app)

    expect(html).toContain('aria-label="折叠侧边栏"')
    expect(html).toContain('conversation-sidebar__new-button')
    expect(html).toContain('conversation-sidebar__search')
    expect(html).toContain('Plan Review')
    expect(html).toContain('conversation-sidebar__load-more')
    expect(html).toContain('conversation-sidebar__menu-button')
    expect(html).not.toContain('>主页<')
    expect(html).not.toContain('<details')
  })

  it('renders a running spinner for conversations currently replying', async () => {
    const app = createSSRApp(ConversationSidebar, {
      activeView: 'conversation',
      activeConversationId: 'conv_1',
      conversations,
      runningConversationIds: ['conv_1'],
      loading: false,
      hasMore: false,
      search: '',
      collapsed: false,
    })

    const html = await renderToString(app)

    expect(html).toContain('conversation-sidebar__running-spinner')
    expect(html).toContain('aria-label="正在回复"')
  })
})
