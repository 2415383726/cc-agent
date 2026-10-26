import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import DefaultToolCallCard from './DefaultToolCallCard.vue'

function renderCard(props: Record<string, unknown>) {
  return renderToString(createSSRApp(DefaultToolCallCard, props))
}

describe('DefaultToolCallCard', () => {
  it('renders the compact completed tool card with a folded summary', async () => {
    const html = await renderCard({
      name: 'weekday',
      toolCallId: 'call_1',
      args: {
        year: 2026,
        month: 6,
        day: 27,
      },
      status: 'complete',
      result: 'June 27, 2026 is Saturday.',
    })

    expect(html).toContain('big-tool-card')
    expect(html).toContain('big-tool-header')
    expect(html).toContain('weekday')
    expect(html).toContain('已完成')
    expect(html).toContain('June 27, 2026 is Saturday.')
    expect(html).not.toContain('参数')
    expect(html).not.toContain('&quot;year&quot;: 2026')
    expect(html).not.toContain('Arguments')
  })

  it('uses the current minimal status labels for in-progress and pending states', async () => {
    const running = await renderCard({
      name: 'weekday',
      toolCallId: 'call_1',
      status: 'executing',
    })
    const pending = await renderCard({
      name: 'run_python',
      toolCallId: 'call_2',
      status: 'waiting_permission',
    })

    expect(running).toContain('执行中')
    expect(pending).toContain('准备中')
  })
})
