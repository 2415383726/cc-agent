import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TurnNavigator from '../src/timeline/TurnNavigator.vue'
import { railItems, type TurnRailItem } from '../src/timeline/rail'
import { turnViews } from '../src/timeline/grouping'
import type { MessageEntry, TerminalEntry, WorkbenchEntry } from '../src/projection/transcript'

// 相对日期：跨天运行不改变「同日只显示时钟」的行为（BASE_TS 原为固定日期，会在日期翻转后失效）。
const BASE_TS = (() => {
  const today = new Date()
  today.setHours(10, 0, 0, 0)
  return today.getTime()
})()

function messageEntry(partial: Partial<MessageEntry>): MessageEntry {
  return {
    id: 'm1',
    kind: 'message',
    role: 'assistant',
    text: '',
    streaming: false,
    ts: BASE_TS,
    ...partial,
  } as MessageEntry
}

function terminalEntry(id: string, ts: number): TerminalEntry {
  return {
    id,
    kind: 'terminal',
    terminal: { status: 'completed', answer: '', error: null, stats: {} },
    ts,
  } as TerminalEntry
}

describe('railItems（回合导航轨条目推导）', () => {
  it('每回合一个刻度：prompt 取用户文本，response 取首条非空助手文本，id 与 turnViews 一致', () => {
    const entries: WorkbenchEntry[] = [
      messageEntry({ id: 'u1', role: 'user', text: '第一个问题', ts: BASE_TS }),
      messageEntry({ id: 'a1', text: '', ts: BASE_TS + 100 }),
      messageEntry({ id: 'a2', text: '最终回答', ts: BASE_TS + 200 }),
      terminalEntry('t1', BASE_TS + 300),
      messageEntry({ id: 'u2', role: 'user', text: '第二个问题', ts: BASE_TS + 400 }),
      messageEntry({ id: 'a3', text: '第二个回答', ts: BASE_TS + 500 }),
      terminalEntry('t2', BASE_TS + 600),
    ]
    const items = railItems(entries)
    expect(items).toHaveLength(2)
    expect(items[0]).toMatchObject({ prompt: '第一个问题', response: '最终回答' })
    expect(items[1]).toMatchObject({ prompt: '第二个问题', response: '第二个回答' })
    const viewIds = turnViews([...entries], false).map((turn) => turn.id)
    expect(items.map((item) => item.id)).toEqual(viewIds)
  })

  it('预览有界：空白折叠为单空格，超长截断补省略号', () => {
    const long = `词${' '.repeat(10)}语`.repeat(80)
    const entries: WorkbenchEntry[] = [
      messageEntry({ id: 'u1', role: 'user', text: long, ts: BASE_TS }),
      terminalEntry('t1', BASE_TS + 100),
    ]
    const [item] = railItems(entries)
    expect(item!.prompt.length).toBeLessThanOrEqual(161)
    expect(item!.prompt.endsWith('…')).toBe(true)
    expect(item!.prompt).not.toContain('  ')
  })

  it('无条目返回空数组；非用户开头的零散条目按 turnViews 语义成空 prompt 刻度', () => {
    expect(railItems([])).toEqual([])
    const [orphan] = railItems([messageEntry({ id: 'a1', text: '孤立回答', ts: BASE_TS })])
    expect(orphan).toMatchObject({ prompt: '', response: '孤立回答' })
    expect(orphan!.id).toBe(turnViews([messageEntry({ id: 'a1', text: '孤立回答', ts: BASE_TS })], false)[0]!.id)
  })
})

describe('TurnNavigator（右侧回合导航轨）', () => {
  const items: TurnRailItem[] = [
    { id: 'turn:0:u1', prompt: '第一个问题', response: '第一个回答' },
    { id: 'turn:1:u2', prompt: '第二个问题', response: '' },
  ]

  it('少于 2 个刻度不渲染轨', () => {
    const single = mount(TurnNavigator, { props: { items: [items[0]!], activeId: null } })
    expect(single.find('[data-testid="turn-navigator"]').exists()).toBe(false)
  })

  it('渲染刻度并标注激活回合（aria-current）', () => {
    const wrapper = mount(TurnNavigator, { props: { items, activeId: items[1]!.id } })
    const marks = wrapper.findAll('[data-testid^="turn-mark-"]')
    expect(marks).toHaveLength(2)
    expect(marks[0]!.attributes('aria-current')).toBeUndefined()
    expect(marks[1]!.attributes('aria-current')).toBe('true')
    expect(marks[0]!.attributes('aria-label')).toBe('第一个问题')
  })

  it('悬停刻度弹出预览卡（问题 + 回答），移出后收起', async () => {
    const wrapper = mount(TurnNavigator, { props: { items, activeId: null } })
    expect(wrapper.find('[data-testid="turn-preview"]').exists()).toBe(false)
    await wrapper.find('[data-testid="turn-mark-0"]').trigger('pointermove')
    const preview = wrapper.find('[data-testid="turn-preview"]')
    expect(preview.exists()).toBe(true)
    expect(preview.text()).toContain('第一个问题')
    expect(preview.text()).toContain('第一个回答')
    await wrapper.find('nav').trigger('pointerleave')
    expect(wrapper.find('[data-testid="turn-preview"]').exists()).toBe(false)
  })

  it('点击刻度上抛 navigate（携带对应条目）', async () => {
    const wrapper = mount(TurnNavigator, { props: { items, activeId: null } })
    await wrapper.find('[data-testid="turn-mark-1"]').trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([[items[1]]])
  })

  it('无回答的回合预览只显示问题行', async () => {
    const wrapper = mount(TurnNavigator, { props: { items, activeId: null } })
    await wrapper.find('[data-testid="turn-mark-1"]').trigger('pointermove')
    const preview = wrapper.find('[data-testid="turn-preview"]')
    expect(preview.exists()).toBe(true)
    expect(preview.text()).toContain('第二个问题')
    expect(preview.text()).not.toContain('第一个回答')
  })
})
