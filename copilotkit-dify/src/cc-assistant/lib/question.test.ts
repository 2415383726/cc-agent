import { describe, expect, it } from 'vitest'
import { buildInterruptResumePayload, normalizeInterruptQuestion } from './question'

describe('structured interrupt questions', () => {
  it('normalizes form fields and builds values plus a readable answer', () => {
    const question = normalizeInterruptQuestion({
      id: 'prompt-1',
      question: '补充检索条件',
      fields: [
        { name: 'keyword', label: '关键词', type: 'text', required: true },
        { name: 'levels', label: '层级', type: 'multiselect', options: ['省级', '市级'], defaultValue: ['市级'] },
        { name: 'active', label: '仅看有效', type: 'checkbox', defaultValue: true },
        {
          name: 'budget', label: '预算', type: 'number', group: '范围', width: 'half',
          description: '填写含税预算', min: 0, max: 1000, step: 10, prefix: '¥', suffix: '万元',
        },
        { name: 'period', label: '统计周期', type: 'daterange', defaultValue: ['2026-01-01', '2026-06-30'] },
        { name: 'method', label: '办理方式', type: 'radio', options: [{ label: '线上', value: 'online', description: '全程在线办理' }] },
      ],
    })
    expect(question.fields).toHaveLength(6)
    expect(question.fields[3]).toMatchObject({ group: '范围', width: 'half', min: 0, max: 1000, prefix: '¥', suffix: '万元' })
    expect(question.fields[4].defaultValue).toEqual(['2026-01-01', '2026-06-30'])
    const payload = buildInterruptResumePayload(question, [], '', { keyword: '数字化', levels: ['市级'], active: true })
    expect(payload?.values).toEqual({ keyword: '数字化', levels: ['市级'], active: true })
    expect(payload?.answer).toContain('关键词：数字化')
    expect(payload?.answer).toContain('仅看有效：是')
  })

  it('normalizes disabled descriptive options without exposing unknown field types', () => {
    const question = normalizeInterruptQuestion({
      fields: [
        { name: 'channel', label: '渠道', type: 'radio', options: [{ label: '柜台', value: 'desk', disabled: true }] },
        { name: 'legacy', label: '旧字段', type: 'color' },
      ],
    })
    expect(question.fields[0].options[0]).toMatchObject({ value: 'desk', disabled: true })
    expect(question.fields[1].type).toBe('text')
  })

  it('keeps the existing simple choice payload', () => {
    const question = normalizeInterruptQuestion({ id: 'p2', question: '继续吗', options: [{ label: '继续', value: 'yes' }] })
    const payload = buildInterruptResumePayload(question, ['yes'], '')
    expect(payload?.selectedValues).toEqual(['yes'])
    expect(payload?.answer).toBe('继续')
  })
})
