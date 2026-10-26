import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import RecordSurface from './RecordSurface.vue'
import TableSurface from './TableSurface.vue'
import CompareSurface from './CompareSurface.vue'
import TimelineSurface from './TimelineSurface.vue'

describe('business answer surfaces', () => {
  it('renders grouped record fields and actions', async () => {
    const html = await renderToString(createSSRApp(RecordSurface, { spec: { version: 1, meta: { title: '人员档案', status: '在岗' }, sections: [{ title: '基本信息', fields: [{ label: '姓名', value: '张三' }, { label: '标签', value: ['骨干'], format: 'tags' }] }], actions: [{ id: 'more', label: '继续分析', prompt: '继续分析' }] } }))
    expect(html).toContain('data-surface="record"')
    expect(html).toContain('基本信息')
    expect(html).toContain('继续分析')
  })

  it('renders typed tables, comparisons, and timeline order', async () => {
    const table = await renderToString(createSSRApp(TableSurface, { spec: { version: 1, meta: { title: '名单' }, columns: [{ key: 'score', label: '得分', format: 'number', sortable: true }], rows: [{ id: '1', values: { score: 91 } }] } }))
    expect(table).toContain('table-viewport')
    expect(table).toContain('aria-sort="none"')
    const compare = await renderToString(createSSRApp(CompareSurface, { spec: { version: 1, meta: { title: '比较' }, subjects: [{ id: 'a', label: '甲' }, { id: 'b', label: '乙' }], criteria: [{ id: 'c', label: '经验', values: { a: '5年', b: '3年' }, highlight: 'a' }] } }))
    expect(compare).toContain('highlighted')
    const timeline = await renderToString(createSSRApp(TimelineSurface, { spec: { version: 1, meta: { title: '履历' }, items: [{ id: '1', time: '2022', title: '第一段' }, { id: '2', time: '2024', title: '第二段' }] } }))
    expect(timeline.indexOf('第一段')).toBeLessThan(timeline.indexOf('第二段'))
  })
})
