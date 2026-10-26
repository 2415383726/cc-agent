import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import InterruptCard from './InterruptCard.vue'
import { normalizeInterruptQuestion } from '../../lib/question'

describe('InterruptCard', () => {
  it('renders grouped responsive business fields and descriptive choices', async () => {
    const question = normalizeInterruptQuestion({
      id: 'filters-1',
      question: '请补充干部检索条件',
      fields: [
        {
          name: 'keyword', label: '姓名或工号', type: 'text', required: true,
          group: '基本条件', width: 'half', description: '支持姓名或完整工号', placeholder: '例如：张明',
        },
        {
          name: 'budget', label: '预算', type: 'number', group: '基本条件', width: 'half',
          prefix: '¥', suffix: '万元', min: 0, max: 1000,
        },
        {
          name: 'period', label: '统计周期', type: 'daterange', group: '统计范围', required: true,
          defaultValue: ['2026-01-01', '2026-06-30'],
        },
        {
          name: 'method', label: '办理方式', type: 'radio', group: '统计范围',
          options: [
            { label: '线上办理', value: 'online', description: '全程在线完成' },
            { label: '线下办理', value: 'offline', disabled: true },
          ],
        },
      ],
    })

    const html = await renderToString(createSSRApp({
      render: () => h(InterruptCard, { question, resolve: vi.fn() }),
    }))

    expect(html).toContain('<form')
    expect(html).toContain('基本条件')
    expect(html).toContain('统计范围')
    expect(html).toContain('is-half')
    expect(html).toContain('支持姓名或完整工号')
    expect(html).toContain('type="number"')
    expect(html).toContain('开始日期')
    expect(html).toContain('结束日期')
    expect(html).toContain('type="radio"')
    expect(html).toContain('全程在线完成')
    expect(html).toContain('disabled')
    expect(html).toContain('提交并继续')
  })

  it('keeps custom input and simple options available', async () => {
    const question = normalizeInterruptQuestion({
      id: 'choice-1',
      question: '请选择处理方式',
      options: [{ label: '立即处理', value: 'now', description: '现在开始执行' }],
      allowCustomInput: true,
    })
    const html = await renderToString(createSSRApp({
      render: () => h(InterruptCard, { question, resolve: vi.fn() }),
    }))
    expect(html).toContain('立即处理')
    expect(html).toContain('现在开始执行')
    expect(html).toContain('补充说明')
    expect(html).toContain('name="customInput"')
  })
})
