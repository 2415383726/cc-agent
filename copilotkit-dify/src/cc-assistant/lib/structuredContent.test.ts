import { describe, expect, it } from 'vitest'
import { parseStructuredContentParts } from './structuredContent'

function fence(language: string, value: unknown) {
  return `\`\`\`${language}\n${JSON.stringify(value)}\n\`\`\``
}

describe('structured answer protocols', () => {
  it('parses record, table, compare, and timeline fences', () => {
    const content = [
      fence('cc-record', { version: 1, meta: { title: '档案' }, sections: [{ fields: [{ label: '姓名', value: '张三' }] }] }),
      fence('cc-table', { version: 1, meta: { title: '名单' }, columns: [{ key: 'name', label: '姓名' }], rows: [{ id: '1', values: { name: '张三' } }] }),
      fence('cc-compare', { version: 1, meta: { title: '对比' }, subjects: [{ id: 'a', label: '甲' }, { id: 'b', label: '乙' }], criteria: [{ id: 'age', label: '年龄', values: { a: 30, b: 32 } }] }),
      fence('cc-timeline', { version: 1, meta: { title: '履历' }, items: [{ id: '1', time: '2024', title: '任职' }] }),
    ].join('\n')
    expect(parseStructuredContentParts(content).map(part => part.type)).toEqual(['record', 'table', 'compare', 'timeline'])
  })

  it('keeps invalid and removed protocols as markdown code blocks', () => {
    const invalid = fence('cc-record', { version: 1, meta: { title: '缺少 sections' } })
    const removed = fence('cc-ui', { version: 1, kind: 'summary', data: {} })
    const mixed = `${invalid}\n${fence('cc-timeline', { version: 1, meta: { title: '有效' }, items: [{ id: '1', time: '今天', title: '完成' }] })}`
    const parts = parseStructuredContentParts(mixed)
    expect(parts[0]).toMatchObject({ type: 'markdown' })
    expect((parts[0] as any).content).toContain('```cc-record')
    expect(parseStructuredContentParts(removed)).toEqual([])
  })

  it('rejects unknown fields through strict schemas', () => {
    const content = fence('cc-record', { version: 1, meta: { title: '档案' }, sections: [{ fields: [{ label: '姓名', value: '张三' }] }], url: 'https://example.com' })
    expect(parseStructuredContentParts(content)).toEqual([{ type: 'markdown', content }])
  })

  it('keeps completed business specs referentially stable across streaming reparses', () => {
    const record = fence('cc-record', { version: 1, meta: { title: '档案' }, sections: [{ fields: [{ label: '姓名', value: '张三' }] }] })
    const first = parseStructuredContentParts(record)
    const second = parseStructuredContentParts(`${record}\n后续说明仍在生成`)

    expect((second[0] as any).spec).toBe((first[0] as any).spec)
  })

  it('uses a lightweight pending part for an unfinished business fence', () => {
    expect(parseStructuredContentParts('说明\n```cc-table\n{"version":1')).toEqual([
      { type: 'markdown', content: '说明' },
      { type: 'surface-pending', surface: 'table' },
    ])
  })

  it('does not reparse a completed card while the next business fence streams', () => {
    const record = fence('cc-record', { version: 1, meta: { title: '档案' }, sections: [{ fields: [{ label: '姓名', value: '张三' }] }] })
    const completed = parseStructuredContentParts(record)
    const combined = parseStructuredContentParts(`${record}\n\`\`\`cc-compare\n{"version":1`)

    expect(combined.map(part => part.type)).toEqual(['record', 'surface-pending'])
    expect((combined[0] as any).spec).toBe((completed[0] as any).spec)
  })
})
