import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import AnswerChart from './AnswerChart.vue'

const spec = {
  version: 1 as const,
  chartType: 'bar' as const,
  meta: { title: '各产品季度销量', description: '对比五款产品本季度销量。', footer: '单位：件｜示例数据' },
  xKey: 'product',
  series: [{ dataKey: 'sales', label: '销量' }],
  data: [{ product: '产品 A', sales: 1250 }],
}

describe('AnswerChart', () => {
  it('renders the analysis canvas header, plot, footer, and accessible menu', async () => {
    const html = await renderToString(createSSRApp(AnswerChart, { spec }))
    expect(html).toContain('data-testid="answer-chart"')
    expect(html).toContain('各产品季度销量')
    expect(html).toContain('对比五款产品本季度销量')
    expect(html).toContain('单位：件｜示例数据')
    expect(html).toContain('aria-label="图表操作"')
    expect(html).not.toContain('structured-chart')
  })
})