import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import SearchToolCard from './SearchToolCard.vue'

function renderCard(props: Record<string, unknown>) {
  return renderToString(createSSRApp(SearchToolCard, props))
}

const searchResult = {
  result: [
    {
      metadata: {
        document_name: 'xl.txt',
        score: 0.23536099541335034,
      },
      title: 'xl.txt',
      content:
        '比如说现在，王林测试了一下，它的速度，比之以前，更快了，若是全力展开，以王林现在的眼力，已经看到不飞剑飞行的痕迹了。',
    },
    {
      metadata: {
        document_name: 'xl.txt',
        score: 0.20564801661220936,
      },
      title: 'xl.txt',
      content:
        '不过王林记得那时对方还是身穿白衣，可现在短短几个月，居然荣升到黑衣！',
    },
  ],
}

describe('SearchToolCard', () => {
  it('renders Dify knowledge search results as compact carousel items', async () => {
    const html = await renderCard({
      name: 'search',
      toolCallId: 'call_search',
      status: 'complete',
      result: JSON.stringify(searchResult),
    })

    expect(html).toContain('search-tool-card')
    expect(html).toContain('search')
    expect(html).toContain('2 条结果')
    expect(html).toContain('xl.txt')
    expect(html).toContain('23.5%')
    expect(html).toContain('王林测试了一下')
    expect(html).not.toContain('&quot;metadata&quot;')
  })

  it('falls back to the raw result text when search output is not JSON', async () => {
    const html = await renderCard({
      name: 'search',
      toolCallId: 'call_search',
      status: 'complete',
      result: '未找到相关内容',
    })

    expect(html).toContain('未找到相关内容')
    expect(html).toContain('0 条结果')
  })

  it('does not render a source summary beside the status badge', async () => {
    const html = await renderCard({
      name: 'search',
      toolCallId: 'call_search',
      args: { query: '王林' },
      status: 'complete',
      result: JSON.stringify(searchResult),
    })

    expect(html).toContain('已完成')
    expect(html).toContain('王林')
    expect(html).not.toContain('search-source')
  })

  it('does not highlight query matches in the compact card view', async () => {
    const html = await renderCard({
      name: 'search',
      toolCallId: 'call_search',
      args: { query: 'alpha' },
      status: 'complete',
      result: JSON.stringify({
        result: [
          {
            title: 'note.txt',
            content: 'alpha beta alpha',
            metadata: { document_name: 'note.txt', score: 0.42 },
          },
        ],
      }),
    })

    expect(html).toContain('alpha beta alpha')
    expect(html).not.toContain('highlight-match')
    expect(html).not.toContain('<mark')
  })
})
