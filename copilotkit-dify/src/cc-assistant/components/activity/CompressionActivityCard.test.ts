import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import CompressionActivityCard from './CompressionActivityCard.vue'

describe('CompressionActivityCard', () => {
  it('renders the started state as a lightweight separator', async () => {
    const app = createSSRApp(CompressionActivityCard, {
      activityType: 'cc_agent.compression',
      content: {
        status: 'started',
        trigger: 'auto',
        compressionId: 'compression:auto:1',
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('上下文压缩中')
    expect(html).not.toContain('上下文已压缩')
    expect(html).not.toContain('compressionId')
  })

  it('renders the completed state as a lightweight separator with concise detail', async () => {
    const app = createSSRApp(CompressionActivityCard, {
      activityType: 'cc_agent.compression',
      content: {
        status: 'completed',
        trigger: 'auto',
        summarized_messages: 12,
        truncated_observations: 2,
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('上下文已压缩')
    expect(html).toContain('已整理 12 条消息')
    expect(html).not.toContain('compressed_reason')
  })
})
