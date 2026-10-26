import { describe, expect, it } from 'vitest'
import { buildChartOption, chartSpecToCsv, escapeHtml, formatChartValue, suggestedChartHeight } from './chartRendering'
import type { ChartSpec } from './chartSpec'

const meta = { title: '收入分析' }

describe('chart rendering helpers', () => {
  it('formats numbers consistently', () => {
    expect(formatChartValue(12500, { valueFormat: 'compact', valuePrefix: '¥' })).toContain('¥')
    expect(formatChartValue(12.6, { valueFormat: 'integer', valueSuffix: ' 件' })).toBe('13 件')
    expect(formatChartValue(35, { valueFormat: 'percent' })).toBe('35%')
  })

  it('builds horizontal bars and line legends', () => {
    const bar: ChartSpec = { version: 1, chartType: 'bar', meta, orientation: 'horizontal', xKey: 'name', series: [{ dataKey: 'value', valueSuffix: '万' }], data: [{ name: '企业版', value: 648 }] }
    const option: any = buildChartOption(bar)
    expect(option.xAxis.type).toBe('value')
    expect(option.yAxis.type).toBe('category')
    expect(option.series[0].type).toBe('bar')
    expect(suggestedChartHeight(bar)).toBeGreaterThanOrEqual(320)
  })

  it('builds donut, scatter, and radar semantics', () => {
    const pie: ChartSpec = { version: 1, chartType: 'pie', meta, nameKey: 'segment', valueKey: 'value', data: [{ segment: '企业', value: 8 }, { segment: '团队', value: 5 }] }
    const scatter: ChartSpec = { version: 1, chartType: 'scatter', meta, xKey: 'spend', labelKey: 'month', series: [{ dataKey: 'revenue' }], data: [{ month: '1月', spend: 18, revenue: 76 }] }
    const radar: ChartSpec = { version: 1, chartType: 'radar', meta, nameKey: 'metric', series: [{ dataKey: 'a' }], data: [{ metric: '速度', a: 80 }, { metric: '质量', a: 90 }, { metric: '稳定', a: 70 }] }
    expect((buildChartOption(pie) as any).series[0].radius).toEqual(['48%', '70%'])
    expect((buildChartOption(scatter) as any).series[0].data[0]).toEqual([18, 76, '1月'])
    expect((buildChartOption(radar) as any).radar.indicator).toHaveLength(3)
  })

  it('exports UTF-8 CSV with quoting and escapes tooltip content', () => {
    const spec: ChartSpec = { version: 1, chartType: 'bar', meta, xKey: 'name', series: [{ dataKey: 'value' }], data: [{ name: '企业,版', value: 648 }] }
    const csv = chartSpecToCsv(spec)
    expect(csv.charCodeAt(0)).toBe(0xFEFF)
    expect(csv).toContain('"企业,版"')
    expect(escapeHtml('<img onerror=x>')).toBe('&lt;img onerror=x&gt;')
  })
})