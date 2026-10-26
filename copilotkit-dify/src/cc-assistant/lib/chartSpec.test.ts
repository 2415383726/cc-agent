import { describe, expect, it } from 'vitest'
import { normalizeChartSpec } from './chartSpec'

const meta = { title: '示例图表', description: '说明' }

describe('normalizeChartSpec', () => {
  it.each([
    { version: 1, chartType: 'bar', meta, xKey: 'name', series: [{ dataKey: 'value' }], data: [{ name: 'A', value: 1 }] },
    { version: 1, chartType: 'line', meta, xKey: 'month', series: [{ dataKey: 'actual' }], data: [{ month: '1月', actual: 82 }] },
    { version: 1, chartType: 'pie', meta, nameKey: 'name', valueKey: 'value', data: [{ name: 'A', value: 2 }, { name: 'B', value: 3 }] },
    { version: 1, chartType: 'scatter', meta, xKey: 'x', labelKey: 'label', series: [{ dataKey: 'y' }], data: [{ label: '1月', x: 12, y: 75 }] },
    { version: 1, chartType: 'radar', meta, nameKey: 'metric', maxKey: 'max', series: [{ dataKey: 'team', label: '团队' }], data: [{ metric: '速度', team: 80, max: 100 }, { metric: '质量', team: 90, max: 100 }, { metric: '稳定性', team: 75, max: 100 }] },
  ])('accepts a valid $chartType chart', (spec) => {
    expect(normalizeChartSpec(spec)?.chartType).toBe(spec.chartType)
  })

  it('rejects invalid versions, mappings, values, and unknown fields', () => {
    expect(normalizeChartSpec({ version: 2, chartType: 'bar', meta, xKey: 'name', series: [{ dataKey: 'value' }], data: [{ name: 'A', value: 1 }] })).toBeNull()
    expect(normalizeChartSpec({ version: 1, chartType: 'line', meta, xKey: 'month', series: [{ dataKey: 'missing' }], data: [{ month: '1月', actual: 82 }] })).toBeNull()
    expect(normalizeChartSpec({ version: 1, chartType: 'pie', meta, nameKey: 'name', valueKey: 'value', data: [{ name: 'A', value: -2 }, { name: 'B', value: 3 }] })).toBeNull()
    expect(normalizeChartSpec({ version: 1, chartType: 'bar', meta, xKey: 'name', series: [{ dataKey: 'value' }], data: [{ name: 'A', value: 1 }], color: 'red' })).toBeNull()
  })

  it('parses JSON strings and rejects malformed JSON', () => {
    const spec = { version: 1, chartType: 'bar', meta, xKey: 'name', series: [{ dataKey: 'value' }], data: [{ name: 'A', value: 1 }] }
    expect(normalizeChartSpec(JSON.stringify(spec))?.chartType).toBe('bar')
    expect(normalizeChartSpec('{bad json')).toBeNull()
  })
})