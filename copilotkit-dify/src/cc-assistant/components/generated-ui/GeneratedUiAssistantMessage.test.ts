import { describe, expect, it } from 'vitest'
import { createSSRApp, defineComponent } from 'vue'
import { renderToString } from '@vue/server-renderer'
import type { Message } from '@ag-ui/core'
import { CopilotChatConfigurationProvider, CopilotKitProvider } from '@copilotkit/vue/v2'
import GeneratedUiAssistantMessage from './GeneratedUiAssistantMessage.vue'

function renderMessage(message: Message) {
  const messages = [message]
  const Inner = defineComponent({
    components: { GeneratedUiAssistantMessage },
    setup: () => ({ message, messages }),
    template: '<GeneratedUiAssistantMessage :message="message" :messages="messages" />',
  })
  const Host = defineComponent({
    components: { CopilotChatConfigurationProvider, CopilotKitProvider, Inner },
    template: '<CopilotKitProvider runtime-url="/api/copilotkit"><CopilotChatConfigurationProvider agent-id="default" thread-id="thread-ui"><Inner /></CopilotChatConfigurationProvider></CopilotKitProvider>',
  })
  return renderToString(createSSRApp(Host))
}

describe('GeneratedUiAssistantMessage', () => {
  it('keeps plain assistant text on the native message', async () => {
    const html = await renderMessage({ id: 'a1', role: 'assistant', content: '普通回答' } as Message)
    expect(html).toContain('data-testid="copilot-assistant-message"')
    expect(html).toContain('普通回答')
  })

  it('renders cc-chart and hides its raw JSON fence', async () => {
    const spec = {
      version: 1,
      chartType: 'line',
      meta: { title: '收入趋势', description: '收入连续增长。', footer: '单位：万元' },
      xKey: 'month',
      series: [{ dataKey: 'actual', label: '实际收入' }],
      data: [{ month: '1月', actual: 82 }, { month: '2月', actual: 91 }],
    }
    const html = await renderMessage({ id: 'a2', role: 'assistant', content: `分析如下\n\`\`\`cc-chart\n${JSON.stringify(spec)}\n\`\`\`` } as Message)
    expect(html).toContain('分析如下')
    expect(html).toContain('data-testid="answer-chart"')
    expect(html).toContain('收入趋势')
    expect(html).toContain('收入连续增长')
    expect(html).toContain('单位：万元')
    expect(html).not.toContain('```cc-chart')
  })

  it('renders mixed business, chart, and mermaid blocks in order', async () => {
    const content = [
      '```cc-record',
      JSON.stringify({ version: 1, meta: { title: '项目档案' }, sections: [{ fields: [{ label: '状态', value: '完成', format: 'status' }] }] }),
      '```',
      '```cc-chart',
      JSON.stringify({ version: 1, chartType: 'bar', meta: { title: '任务趋势' }, xKey: 'day', series: [{ dataKey: 'count' }], data: [{ day: '一', count: 3 }] }),
      '```',
      '```mermaid',
      'graph TD',
      '  A[需求] --> B[上线]',
      '```',
    ].join('\n')
    const html = await renderMessage({ id: 'a3', role: 'assistant', content } as Message)
    expect(html).toContain('data-surface="record"')
    expect(html).toContain('data-testid="answer-chart"')
    expect(html).toContain('data-testid="mermaid-block"')
    expect(html).not.toContain('```cc-chart')
  })

  it('shows removed cc-ui as ordinary code instead of rendering a card', async () => {
    const content = '```cc-ui\n{"version":1,"kind":"summary","data":{}}\n```'
    const html = await renderMessage({ id: 'old-ui', role: 'assistant', content } as Message)
    expect(html).toContain('cc-ui')
    expect(html).not.toContain('data-testid="business-surface"')
  })
  it('shows a chart skeleton as soon as a streamed cc-chart fence starts', async () => {
    const html = await renderMessage({ id: 'pending-chart', role: 'assistant', content: 'Analysis\n```cc-chart\n{"version":1' } as Message)
    expect(html).toContain('data-testid="answer-chart-pending"')
    expect(html).not.toContain('```cc-chart')
  })

  it('shows a lightweight placeholder instead of rendering streamed business JSON as markdown', async () => {
    const html = await renderMessage({ id: 'pending-table', role: 'assistant', content: '说明\n```cc-table\n{"version":1,"meta":' } as Message)
    expect(html).toContain('data-testid="business-surface-pending"')
    expect(html).toContain('正在整理业务表格')
    expect(html).not.toContain('```cc-table')
    expect(html).not.toContain('&quot;version&quot;')
  })
})
