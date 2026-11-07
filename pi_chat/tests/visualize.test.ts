import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { SCHEMA } from '../src/contract/display'
import { applyEvent, newView } from '../src/projection/transcript'
import { groupTimeline } from '../src/timeline/grouping'
import TranscriptView from '../src/timeline/TranscriptView.vue'
import VisualizationCard from '../src/timeline/VisualizationCard.vue'
import { buildFrameDoc, FRAME_CSP } from '../src/vendor/dshv/shell'
import type { MessageEntry, TerminalEntry, ToolEntry, WorkbenchEntry } from '../src/projection/transcript'

let seq = 0
function event(type: string, fields: Record<string, unknown> = {}) {
  seq += 1
  return {
    schema: SCHEMA,
    schema_version: 1,
    type,
    run_id: 'run_test',
    seq,
    ts: seq,
    ...fields,
  } as any
}

const FRAGMENT = `<div id="v"><button class="btn" onclick="run()">排序</button><script>function run(){document.getElementById('v').setAttribute('data-ran','1')}</script></div>`

function visualizeEnd(fields: Record<string, unknown> = {}) {
  return event('tool.end', {
    tool_call_id: 'viz1',
    name: 'visualize',
    status: 'ok',
    is_error: false,
    execution_outcome: 'executed',
    result: 'Rendered "排序演示" as an inline card (120 chars).',
    visual: { fragment: FRAGMENT, title: '排序演示', mode: 'inline', size_bytes: 120 },
    ...fields,
  })
}

describe('visualize 投影（tool.end visual 载荷）', () => {
  it('解析 visual 字段为卡片载荷', () => {
    const view = newView()
    applyEvent(view, visualizeEnd())
    const tool = view.entries.find((entry) => entry.kind === 'tool') as ToolEntry
    expect(tool.visual).toEqual({ fragment: FRAGMENT, title: '排序演示', mode: 'inline', size_bytes: 120 })
    // 模型侧确认行保持原样（不回显片段）
    expect(tool.result).not.toContain(FRAGMENT)
  })

  it('载荷残缺时降级为 undefined（普通工具结果卡）', () => {
    const view = newView()
    applyEvent(view, visualizeEnd({ visual: { fragment: '  ' } }))
    applyEvent(view, event('tool.start', { tool_call_id: 'c2', name: 'lookup' }))
    applyEvent(view, visualizeEnd({ tool_call_id: 'c2', visual: 42 }))
    const tools = view.entries.filter((entry) => entry.kind === 'tool') as ToolEntry[]
    expect(tools).toHaveLength(2)
    expect(tools.every((tool) => tool.visual === undefined)).toBe(true)
  })
})

describe('visualize 分组豁免（不折入工具组）', () => {
  it('visualize 卡与普通工具之间保持独立段落', () => {
    const entries: WorkbenchEntry[] = []
    const view = newView()
    applyEvent(view, event('tool.start', { tool_call_id: 'c1', name: 'lookup_order' }))
    applyEvent(view, event('tool.end', { tool_call_id: 'c1', name: 'lookup_order', status: 'ok', result: 'ok' }))
    applyEvent(view, visualizeEnd())
    applyEvent(view, event('tool.start', { tool_call_id: 'c3', name: 'web_search' }))
    applyEvent(view, event('tool.end', { tool_call_id: 'c3', name: 'web_search', status: 'ok', result: 'ok' }))
    entries.push(...view.entries)
    const segments = groupTimeline(entries, false)
    const singles = segments.filter((segment) => segment.kind === 'single')
    const groups = segments.filter((segment) => segment.kind === 'tool-group')
    expect(groups).toHaveLength(2)
    expect(singles).toHaveLength(1)
    expect((singles[0]!.entry as ToolEntry).name).toBe('visualize')
  })
})

describe('VisualizationCard（沙箱卡片）', () => {
  it('渲染沙箱 iframe 与卡头（标题/mode），不外泄片段文本', () => {
    const view = newView()
    applyEvent(view, visualizeEnd())
    const entry = view.entries.find((item) => item.kind === 'tool') as ToolEntry
    const wrapper = mount(VisualizationCard, { props: { entry } })
    const frame = wrapper.find('[data-testid="visualize-frame"]')
    expect(frame.exists()).toBe(true)
    expect(frame.attributes('sandbox')).toBe('allow-scripts')
    expect(frame.attributes('title')).toBe('排序演示')
    expect(wrapper.find('[data-testid="visualize-title"]').text()).toBe('排序演示')
    // srcdoc 在属性里，不进入包裹层文本
    expect(wrapper.text()).not.toContain(FRAGMENT)
  })

  it('片段缺失降级为占位说明，不渲染空 iframe', () => {
    const entry = {
      id: 'tool_viz9',
      kind: 'tool',
      callId: 'viz9',
      name: 'visualize',
      args: {},
      updates: [],
      status: 'ok',
      result: 'Rendered "T" as an inline card (10 chars).',
      artifacts: [],
      isError: false,
      executionOutcome: 'executed',
      ts: 1,
    } as ToolEntry
    const wrapper = mount(VisualizationCard, { props: { entry } })
    expect(wrapper.find('[data-testid="visualize-frame"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="visualize-missing"]').exists()).toBe(true)
  })
})

describe('shell 帧文档组装（零网络 CSP）', () => {
  it('CSP 无任何外链源，srcdoc 包含片段与高度上报器', () => {
    expect(FRAME_CSP).toContain("default-src 'none'")
    expect(FRAME_CSP).not.toMatch(/https?:\/\//)
    const doc = buildFrameDoc({
      fragment: '<p>hi</p>',
      title: 'T & <b>',
      themeVars: { foreground: 'rgb(1 2 3)', bad: 'a; b' },
      colorScheme: 'light',
      reportToken: 'call_1',
    })
    expect(doc).toContain('<p>hi</p>')
    expect(doc).toContain("content=\"default-src 'none'")
    expect(doc).toContain('--dsh-viz-foreground: rgb(1 2 3)')
    // 恶意/畸形变量被清洗掉
    expect(doc).not.toContain('--dsh-viz-bad')
    expect(doc).toContain('dsh-viz:height')
    expect(doc).toContain('<title>T &amp; &lt;b&gt;</title>')
    // 主题桥接值不允许逃出样式块
    expect(doc).not.toContain('a; b')
  })
})

describe('TranscriptView 中的 visualize 卡', () => {
  function entries(): WorkbenchEntry[] {
    return [
      { id: 'u1', kind: 'message', role: 'user', text: '画个卡片', streaming: false, ts: 1 } as MessageEntry,
      { id: 't_viz', kind: 'tool', callId: 'viz1', name: 'visualize', args: {}, updates: [], status: 'ok', result: 'ok', artifacts: [], isError: false, executionOutcome: 'executed', ts: 2, visual: { fragment: FRAGMENT, title: '排序演示', mode: 'inline', size_bytes: 120 } } as unknown as ToolEntry,
      { id: 'term', kind: 'terminal', terminal: { status: 'completed', answer: '', error: null, stats: {} }, ts: 3 } as TerminalEntry,
    ]
  }

  it('回合内渲染卡片；回合折叠后卡片保持可见（内容行不随过程行隐藏）', () => {
    const wrapper = mount(TranscriptView, { props: { entries: entries(), running: false } })
    expect(wrapper.find('[data-testid="visualize-card"]').exists()).toBe(true)
    const header = wrapper.find('[data-testid="terminal-row"]')
    expect(header.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-testid="visualize-frame"]').exists()).toBe(true)
  })
})
