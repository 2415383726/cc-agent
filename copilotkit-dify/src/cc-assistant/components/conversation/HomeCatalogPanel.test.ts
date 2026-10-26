import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import HomeCatalogPanel from './HomeCatalogPanel.vue'
import { normalizeAssistantCatalog } from '../../lib/assistantCatalog'

describe('HomeCatalogPanel', () => {
  it('renders skill cards with icons and category tags', async () => {
    const catalog = normalizeAssistantCatalog({
      skills: [
        {
          name: 'email-drafter',
          label: 'Email drafter',
          description: 'Draft a professional email',
          category: 'Communication',
          icon: 'mail',
        },
      ],
      suggestedQuestions: [
        { title: 'Draft a follow-up email', message: 'Draft a follow-up email' },
      ],
    })
    const app = createSSRApp(HomeCatalogPanel, { catalog })

    const html = await renderToString(app)

    expect(html).toContain('home-catalog-card__icon')
    expect(html).toContain('data-icon="mail"')
    expect(html).toContain('Communication')
    expect(html).toContain('Email drafter')
    expect(html).not.toContain('Draft a follow-up email')
  })

  it('renders suggested questions below the skill matrix when explicitly enabled', async () => {
    const catalog = normalizeAssistantCatalog({
      skills: [
        {
          name: 'meeting-notes',
          label: 'Meeting notes',
          description: 'Summarize notes',
          category: 'Office',
        },
        {
          name: 'weekly-report',
          label: 'Weekly report',
          description: 'Create a weekly report',
          category: 'Office',
        },
        {
          name: 'email-drafter',
          label: 'Email drafter',
          description: 'Draft an email',
          category: 'Communication',
        },
        {
          name: 'content-writer',
          label: 'Content writer',
          description: 'Draft content',
          category: 'Writing',
        },
      ],
      suggestedQuestions: [
        { title: '拆解需求', message: '帮我梳理这段需求，拆成目标、风险和下一步' },
        { title: '分析客户反馈', message: '帮我分析这段客户反馈，提炼问题和处理建议' },
        { title: '整理执行清单', message: '帮我把这段工作记录整理成可执行清单' },
      ],
    })
    const app = createSSRApp(HomeCatalogPanel, { catalog, showSuggestedQuestions: true })

    const html = await renderToString(app)

    expect(html).not.toContain('home-catalog-card--question')
    expect(html).toContain('拆解需求')
    expect(html).toContain('分析客户反馈')
    expect(html).toContain('home-question-list')
    expect(html).toContain('整理执行清单')
    expect(html).toContain('点击后会填入下方输入框')
  })

  it('renders skills and suggested questions in pill variant', async () => {
    const catalog = normalizeAssistantCatalog({
      skills: [
        {
          name: 'meeting-notes',
          label: 'Meeting notes',
          description: 'Summarize notes',
          category: 'Office',
        },
        {
          name: 'weekly-report',
          label: 'Weekly report',
          description: 'Create a weekly report',
          category: 'Office',
        },
        {
          name: 'email-drafter',
          label: 'Email drafter',
          description: 'Draft an email',
          category: 'Communication',
        },
        {
          name: 'content-writer',
          label: 'Content writer',
          description: 'Draft content',
          category: 'Writing',
        },
      ],
      suggestedQuestions: [
        { title: 'Draft a follow-up email', message: 'Draft a follow-up email' },
      ],
    })
    const app = createSSRApp(HomeCatalogPanel, {
      catalog,
      compact: true,
      variant: 'pills',
      showSuggestedQuestions: true,
    })

    const html = await renderToString(app)

    expect(html).toContain('home-catalog-panel--pills')
    expect(html).toContain('Meeting notes')
    expect(html).toContain('home-question-list')
    expect(html).toContain('Draft a follow-up email')
  })

  it('hides suggested questions when the catalog does not provide any', async () => {
    const catalog = normalizeAssistantCatalog({
      skills: [
        {
          name: 'meeting-notes',
          label: 'Meeting notes',
          description: 'Summarize notes',
          category: 'Office',
        },
      ],
      suggestedQuestions: [],
    })
    const app = createSSRApp(HomeCatalogPanel, { catalog })

    const html = await renderToString(app)

    expect(html).not.toContain('推荐问题')
    expect(html).not.toContain('home-question-list')
  })

  it('hides default suggested questions unless explicitly enabled', async () => {
    const app = createSSRApp(HomeCatalogPanel)

    const html = await renderToString(app)

    expect(html).not.toContain('推荐问题')
    expect(html).not.toContain('home-question-list')
    expect(html).not.toContain('帮我把这段会议记录整理成纪要和待办')
    expect(html).not.toContain('根据这周工作内容生成一版周报')
    expect(html).not.toContain('帮我起草一封客户跟进邮件')
  })
})
