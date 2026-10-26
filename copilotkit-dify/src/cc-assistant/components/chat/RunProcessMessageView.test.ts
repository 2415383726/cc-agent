import { describe, expect, it } from 'vitest'
import { createSSRApp, defineComponent } from 'vue'
import { renderToString } from '@vue/server-renderer'
import type { Message } from '@ag-ui/core'
import {
  CopilotChatConfigurationProvider,
  CopilotKitProvider,
  useDefaultRenderTool,
} from '@copilotkit/vue/v2'
import RunProcessMessageView from './RunProcessMessageView.vue'
import DefaultToolCallCard from '../tool-cards/DefaultToolCallCard.vue'

function renderMessageView(messages: Message[], isRunning: boolean) {
  const Inner = defineComponent({
    components: { RunProcessMessageView },
    setup() {
      useDefaultRenderTool({
        render: DefaultToolCallCard,
      })
      return { messages, isRunning }
    },
    template: '<RunProcessMessageView :messages="messages" :is-running="isRunning" />',
  })
  const Host = defineComponent({
    components: {
      CopilotChatConfigurationProvider,
      CopilotKitProvider,
      Inner,
    },
    template: `
      <CopilotKitProvider runtime-url="/api/copilotkit">
        <CopilotChatConfigurationProvider agent-id="default" thread-id="thread-1">
          <Inner />
        </CopilotChatConfigurationProvider>
      </CopilotKitProvider>
    `,
  })
  return renderToString(createSSRApp(Host))
}

describe('RunProcessMessageView', () => {
  it('keeps native user and final assistant messages around a collapsed process summary', async () => {
    const messages = [
      { id: 'u1', role: 'user', content: '生成一个报告' },
      { id: 'r1', role: 'reasoning', content: 'internal reasoning' },
      { id: 'mid1', role: 'assistant', content: '我先说明中间判断。' },
      { id: 'a1', role: 'assistant', content: '报告已生成。' },
    ] as Message[]

    const html = await renderMessageView(messages, false)

    expect(html).toContain('data-testid="copilot-user-message"')
    expect(html).toContain('data-testid="run-process-summary"')
    expect(html).not.toContain('data-testid="run-process-content"')
    expect(html).toContain('data-testid="copilot-assistant-message"')
    expect(html).toContain('报告已生成。')
    expect(html).not.toContain('internal reasoning')
    expect(html).not.toContain('我先说明中间判断。')
  })

  it('renders the active assistant turn as the original process message stream', async () => {
    const messages = [
      { id: 'u1', role: 'user', content: '读取 README' },
      { id: 'r1', role: 'reasoning', content: 'checking files' },
      { id: 'mid1', role: 'assistant', content: '我先检查项目结构。' },
      {
        id: 'tc1',
        role: 'assistant',
        content: '',
        toolCalls: [
          {
            id: 'call_1',
            type: 'function',
            function: {
              name: 'weekday',
              arguments: '{"year":2026,"month":6,"day":27}',
            },
          },
        ],
      },
      {
        id: 'tr1',
        role: 'tool',
        toolCallId: 'call_1',
        content: 'June 27, 2026 is Saturday.',
      },
    ] as Message[]

    const html = await renderMessageView(messages, true)

    expect(html).toContain('data-testid="copilot-user-message"')
    expect(html).toContain('data-testid="run-process-summary" open')
    expect(html).toContain('data-testid="run-process-content"')
    expect(html).toContain('分析中')
    expect(html).not.toContain('Thought for')
    expect(html).not.toContain('Thinking')
    expect(html).toContain('我先检查项目结构。')
    expect(html).toContain('weekday')
    expect(html).toContain('June 27, 2026 is Saturday.')
  })

  it('labels completed reasoning as thinking instead of still thinking', async () => {
    const messages = [
      { id: 'u1', role: 'user', content: '今天星期几' },
      { id: 'r1', role: 'reasoning', content: 'checking date' },
    ] as Message[]

    const html = await renderMessageView(messages, false)

    expect(html).toContain('分析过程')
    expect(html).not.toContain('分析中')
  })

  it('renders final structured record while keeping process collapsed', async () => {
    const messages = [
      { id: 'u1', role: 'user', content: '整理一个摘要卡' },
      { id: 'r1', role: 'reasoning', content: 'building ui spec' },
      {
        id: 'a1',
        role: 'assistant',
        content: [
          '已生成摘要。',
          '```cc-record',
          JSON.stringify({
            version: 1,
            meta: { title: '项目档案' },
            sections: [{ fields: [{ label: '检查结果', value: '完成 2 项检查' }] }],
          }),
          '```',
        ].join('\n'),
      },
    ] as Message[]

    const html = await renderMessageView(messages, false)

    expect(html).toContain('data-testid="run-process-summary"')
    expect(html).not.toContain('building ui spec')
    expect(html).toContain('已生成摘要。')
    expect(html).toContain('data-surface="record"')
    expect(html).toContain('项目档案')
    expect(html).toContain('完成 2 项检查')
    expect(html).not.toContain('```cc-record')
  })
  it('shows the streaming final answer while collapsing its completed process', async () => {
    const messages = [
      { id: 'u1', role: 'user', content: 'Analyze this' },
      { id: 'r1', role: 'reasoning', content: 'working' },
      {
        id: 'tc1', role: 'assistant', content: '',
        toolCalls: [{ id: 'call_1', type: 'function', function: { name: 'weekday', arguments: '{}' } }],
      },
      { id: 'tr1', role: 'tool', toolCallId: 'call_1', content: 'done' },
      { id: 'final1', role: 'assistant', content: 'Streaming final answer' },
    ] as Message[]

    const html = await renderMessageView(messages, true)
    expect(html).toContain('data-testid="run-process-summary"')
    expect(html).not.toContain('data-testid="run-process-summary" open')
    expect(html).not.toContain('data-testid="run-process-content"')
    expect(html).toContain('Streaming final answer')
  })
})
