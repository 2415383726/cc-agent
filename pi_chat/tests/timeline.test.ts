import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AssistantMessage from '../src/timeline/AssistantMessage.vue'
import MarkdownContent from '../src/timeline/MarkdownContent.vue'
import NoteRow from '../src/timeline/NoteRow.vue'
import ReasoningRow from '../src/timeline/ReasoningRow.vue'
import TerminalRow from '../src/timeline/TerminalRow.vue'
import UserMessage from '../src/timeline/UserMessage.vue'
import { ScrollFollow } from '../src/timeline/scrollFollow'
import TranscriptView from '../src/timeline/TranscriptView.vue'
import type { MessageEntry, NoteEntry, ReasoningEntry, TerminalEntry, ToolEntry, WorkbenchEntry } from '../src/projection/transcript'

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

/* 组件 seam（spec 测试决策 3）：@vue/test-utils + happy-dom 挂载，只断言外显行为。 */

describe('timeline UserMessage（用户气泡）', () => {
  beforeEach(() => {
    const writeText = vi.fn(() => Promise.resolve())
    Object.defineProperty(window.navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
  })

  afterEach(() => {
    // happy-dom keeps navigator.clipboard across tests; drop the stub again.
    delete (window.navigator as Partial<Navigator>).clipboard
  })

  it('渲染右侧气泡文本与时间戳，复制按钮可点击并给出已复制反馈', async () => {
    const entry = messageEntry({ role: 'user', text: '汇总订单 A-1042，并检查退款政策。' })
    const wrapper = mount(UserMessage, { props: { entry } })
    const bubble = wrapper.find('[data-testid="user-bubble"]')
    expect(bubble.exists()).toBe(true)
    expect(bubble.text()).toBe('汇总订单 A-1042，并检查退款政策。')
    // 时间戳行：HH:mm 形式的时钟文案。
    expect(wrapper.find('[data-testid="user-time"]').text()).toMatch(/^\d{2}:\d{2}$/)

    const copy = wrapper.find('[data-testid="user-copy"]')
    expect(copy.attributes('aria-label')).toBe('复制')
    await copy.trigger('click')
    await flushPromises()
    expect(copy.attributes('aria-label')).toBe('已复制')
    expect(window.navigator.clipboard.writeText).toHaveBeenCalledWith('汇总订单 A-1042，并检查退款政策。')
  })

  it('剪贴板 API 缺失时复制按钮保持可用（best-effort 回退，不抛错）', async () => {
    delete (window.navigator as Partial<Navigator>).clipboard
    const entry = messageEntry({ role: 'user', text: '回退路径' })
    const wrapper = mount(UserMessage, { props: { entry } })
    await wrapper.find('[data-testid="user-copy"]').trigger('click')
    await flushPromises()
    // 无剪贴板宿主不允许崩溃，按钮仍渲染。
    expect(wrapper.find('[data-testid="user-copy"]').exists()).toBe(true)
  })
})

describe('timeline MarkdownContent（助手 markdown）', () => {
  it('渲染标题、列表与表格（dsh 表格滚动包装）', () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        text: [
          '# 标题一',
          '',
          '- 选项甲',
          '- 选项乙',
          '',
          '| 项目 | 值 |',
          '| --- | --- |',
          '| macOS | 27.2 |',
        ].join('\n'),
      },
    })
    expect(wrapper.find('h1').text()).toBe('标题一')
    expect(wrapper.findAll('li').length).toBe(2)
    const table = wrapper.find('[data-testid="md-table"]')
    expect(table.exists()).toBe(true)
    expect(table.find('table').exists()).toBe(true)
  })

  it('代码块带 dsh 横幅与复制钩子，语言标注在 infostring', () => {
    const wrapper = mount(MarkdownContent, {
      props: { text: '```python\nprint("hi")\n```' },
    })
    const block = wrapper.find('[data-testid="md-code-block"]')
    expect(block.exists()).toBe(true)
    expect(block.find('pre code').classes().join(' ')).toContain('language-python')
    const banner = block.find('[data-code-block-banner]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('python')
    expect(block.find('[data-code-copy]').exists()).toBe(true)
  })

  it('点击代码块复制按钮写入剪贴板并反馈已复制', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    Object.defineProperty(window.navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    const wrapper = mount(MarkdownContent, { props: { text: '```bash\necho ok\n```' } })
    const button = wrapper.find('[data-code-copy]')
    await button.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('echo ok\n')
    expect(button.text()).toBe('已复制')
    delete (window.navigator as Partial<Navigator>).clipboard
  })

  it('html:false：原始 HTML 以字面文本呈现，不进入 DOM', () => {
    const wrapper = mount(MarkdownContent, { props: { text: '前文 <img src=x onerror=alert(1)> 后文' } })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
  })
})

describe('timeline AssistantMessage（助手消息）', () => {
  it('完整渲染 markdown 文本且不重复', () => {
    const text = '订单在 12 天前下单，仍在 30 天退款窗口内。'
    const wrapper = mount(AssistantMessage, {
      props: { entry: messageEntry({ text, streaming: false }) },
    })
    const body = wrapper.find('[data-testid="assistant-body"]')
    expect(body.text()).toContain('30 天退款窗口内')
    expect(wrapper.text().split('30 天退款窗口内').length - 1).toBe(1)
  })

  it('助手消息不再自带运行中指示（由时间线末尾统一渲染）', () => {
    const wrapper = mount(AssistantMessage, {
      props: { entry: messageEntry({ text: '部分回答', streaming: true }) },
    })
    expect(wrapper.find('[data-testid="assistant-running"]').exists()).toBe(false)
  })

  it('运行中指示固定在时间线末尾：后续思考行排在它上面', () => {
    const entries: WorkbenchEntry[] = [
      messageEntry({ id: 'u1', role: 'user', text: '问题', ts: 1000, streaming: false }),
      messageEntry({ id: 'a1', role: 'assistant', text: '先加载技能', ts: 2000, streaming: true }),
      {
        kind: 'reasoning',
        id: 'r1',
        ts: 3000,
        text: '思考中的内容',
        title: '思考',
        streaming: true,
      } as WorkbenchEntry,
    ]
    const wrapper = mount(TranscriptView, { props: { entries, running: true } })
    const rows = wrapper.findAll('li')
    const runningIndex = rows.findIndex((row) => row.find('[data-testid="assistant-running"]').exists())
    expect(runningIndex).toBeGreaterThanOrEqual(0)
    // 指示行必须是最后一个 li
    expect(runningIndex).toBe(rows.length - 1)
    expect(wrapper.text()).toContain('深度求索中')
  })
})

describe('timeline ReasoningRow（思考折叠行）', () => {
  function reasoningEntry(partial: Partial<ReasoningEntry> = {}): ReasoningEntry {
    return {
      id: 'r1',
      kind: 'reasoning',
      text: '应用政策前，我需要先确认订单状态。\n第二步再读取退款技能文档。',
      streaming: false,
      ts: BASE_TS,
      ...partial,
    }
  }

  it('默认收起：显示思考标签与单行摘要，不显示全文', () => {
    const wrapper = mount(ReasoningRow, { props: { entry: reasoningEntry() } })
    const toggle = wrapper.find('[data-testid="reasoning-toggle"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toContain('思考')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.text()).toContain('应用政策前，我需要先确认订单状态。')
    expect(wrapper.text()).not.toContain('第二步再读取退款技能文档。')
  })

  it('点击展开显示全文，再次点击收起', async () => {
    const wrapper = mount(ReasoningRow, { props: { entry: reasoningEntry() } })
    const toggle = wrapper.find('[data-testid="reasoning-toggle"]')
    await toggle.trigger('click')
    expect(wrapper.find('[data-testid="reasoning-toggle"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-testid="reasoning-body"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('第二步再读取退款技能文档。')

    await wrapper.find('[data-testid="reasoning-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="reasoning-toggle"]').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-testid="reasoning-body"]').exists()).toBe(false)
  })

  it('streaming 时摘要取最近完成段落首行，带流式标记', () => {
    const wrapper = mount(ReasoningRow, {
      props: {
        entry: reasoningEntry({
          streaming: true,
          text: '第一段已完成。\n\n正在生成的第二段还在输出',
        }),
      },
    })
    const toggle = wrapper.find('[data-testid="reasoning-toggle"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.text()).toContain('第一段已完成。')
    expect(toggle.find('[data-streaming]').exists()).toBe(true)
  })
})

describe('timeline TerminalRow（终态行）', () => {
  function terminalEntry(status: string, error: TerminalEntry['terminal']['error'] = null): TerminalEntry {
    return {
      id: 'terminal_run1',
      kind: 'terminal',
      terminal: { status, answer: '', error, stats: {} },
      ts: BASE_TS,
    }
  }

  it('completed：显示 已完成，用时 X秒 头部行，无状态徽标', () => {
    const wrapper = mount(TerminalRow, {
      props: { entry: terminalEntry('completed'), startTs: BASE_TS - 4000 },
    })
    expect(wrapper.find('[data-testid="terminal-label"]').text()).toMatch(/^已完成，用时 \d+秒$/)
    expect(wrapper.find('[data-testid="terminal-badge"]').exists()).toBe(false)
  })

  it('failed：显示失败徽标与错误文案', () => {
    const wrapper = mount(TerminalRow, {
      props: {
        entry: terminalEntry('failed', { code: 'agent_failed', stage: 'runtime', message: '模型调用失败' }),
      },
    })
    expect(wrapper.find('[data-testid="terminal-label"]').text()).toContain('失败')
    const badge = wrapper.find('[data-testid="terminal-badge"]')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('失败')
    expect(wrapper.text()).toContain('Agent 运行失败。')
  })

  it('stopped：显示已停止徽标', () => {
    const wrapper = mount(TerminalRow, { props: { entry: terminalEntry('stopped') } })
    expect(wrapper.find('[data-testid="terminal-badge"]').text()).toBe('已停止')
  })

  it('budget_exhausted：显示预算耗尽徽标', () => {
    const wrapper = mount(TerminalRow, { props: { entry: terminalEntry('budget_exhausted') } })
    expect(wrapper.find('[data-testid="terminal-badge"]').text()).toBe('预算耗尽')
  })

  it('stats 携带 duration_ms 时优先使用', () => {
    const wrapper = mount(TerminalRow, {
      props: {
        entry: {
          id: 'terminal_run2',
          kind: 'terminal',
          terminal: { status: 'completed', answer: '', error: null, stats: { duration_ms: 10_000 } },
          ts: BASE_TS,
        },
      },
    })
    expect(wrapper.find('[data-testid="terminal-label"]').text()).toBe('已完成，用时 10秒')
  })
})

describe('timeline scrollFollow（自动吸底）', () => {
  function fakeScrollport(height: number, scrollHeight: number) {
    const el = { clientHeight: height, scrollHeight, scrollTop: 0 }
    return el
  }

  it('贴底时内容增长保持跟随', () => {
    const follow = new ScrollFollow(true, 80)
    const el = fakeScrollport(600, 600)
    el.scrollTop = el.scrollHeight - el.clientHeight
    expect(follow.sample({ top: el.scrollTop, height: el.clientHeight, floor: el.scrollHeight - el.clientHeight })).toBe(true)
    el.scrollHeight = 900
    follow.toBottom(el, { top: el.scrollTop, height: el.clientHeight, floor: el.scrollHeight - el.clientHeight }, 'instant')
    expect(el.scrollTop).toBe(300)
    expect(follow.active).toBe(true)
  })

  it('用户向上滚动离开底部后停止跟随，回到底部恢复', () => {
    const follow = new ScrollFollow(true, 80)
    const el = fakeScrollport(600, 2000)
    el.scrollTop = 400
    expect(follow.sample({ top: 400, height: 600, floor: 1400 })).toBe(false)
    expect(follow.active).toBe(false)
    expect(follow.sample({ top: 1330, height: 600, floor: 1400 })).toBe(true)
  })
})

describe('timeline NoteRow（备注行）', () => {
  it('渲染备注文本，警告语气可见', () => {
    const entry: NoteEntry = {
      id: 'note1',
      kind: 'note',
      text: '回放模式：没有发起 Dify 请求或模型调用。',
      tone: 'info',
      ts: BASE_TS,
    }
    const wrapper = mount(NoteRow, { props: { entry } })
    expect(wrapper.find('[data-testid="note-row"]').text()).toBe('回放模式：没有发起 Dify 请求或模型调用。')
    expect(wrapper.find('[data-testid="note-row"]').attributes('data-tone')).toBe('info')
  })
})

describe('TranscriptView 回合折叠（完成态过程收进终态头）', () => {

  function toolEntry(id: string): ToolEntry {
    return {
      id,
      kind: 'tool',
      ts: BASE_TS + 1000,
      callId: id,
      name: 'bash',
      args: { cmd: 'echo hi' },
      updates: [],
      status: 'ok',
      result: 'hi',
      artifacts: [],
      isError: false,
      executionOutcome: 'success',
    }
  }

  function turnEntries(): WorkbenchEntry[] {
    return [
      { id: 'u1', kind: 'message', role: 'user', text: '跑一下', streaming: false, ts: BASE_TS } as MessageEntry,
      { id: 'r1', kind: 'reasoning', text: '先跑命令。', streaming: false, ts: BASE_TS + 500 } as ReasoningEntry,
      toolEntry('t1'),
      messageEntry({ id: 'a1', role: 'assistant', text: '中间进度说明。', ts: BASE_TS + 1500 }),
      messageEntry({ id: 'a2', role: 'assistant', text: '最终答案。', ts: BASE_TS + 2000 }),
      {
        id: 'terminal_run1',
        kind: 'terminal',
        terminal: { status: 'completed', answer: '', error: null, stats: {} },
        ts: BASE_TS + 9000,
      } as TerminalEntry,
    ]
  }

  it('闭合回合默认折叠：终态头在回合顶部带 chevron，思考/工具行隐藏，文本原位可见', () => {
    const wrapper = mount(TranscriptView, { props: { entries: turnEntries(), running: false } })
    const header = wrapper.find('[data-testid="terminal-row"]')
    expect(header.exists()).toBe(true)
    expect(header.element.tagName).toBe('BUTTON')
    expect(header.attributes('aria-expanded')).toBe('false')
    expect(header.find('[data-testid="terminal-chevron"]').exists()).toBe(true)
    expect(header.text()).toMatch(/^已完成，用时 \d+秒$/)
    // 过程行折叠
    expect(wrapper.find('[data-testid="reasoning-toggle"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('已调用工具')
    // 文本原位可见
    expect(wrapper.text()).toContain('中间进度说明。')
    expect(wrapper.text()).toContain('最终答案。')
  })

  it('点击终态头展开：思考/工具组按原始穿插顺序还原，可再收起', async () => {
    const wrapper = mount(TranscriptView, { props: { entries: turnEntries(), running: false } })
    await wrapper.find('[data-testid="terminal-row"]').trigger('click')
    expect(wrapper.find('[data-testid="terminal-row"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-testid="reasoning-toggle"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('执行了命令')
    await wrapper.find('[data-testid="terminal-row"]').trigger('click')
    expect(wrapper.find('[data-testid="terminal-row"]').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-testid="reasoning-toggle"]').exists()).toBe(false)
  })

  it('进行中回合（无终态）不折叠、无 chevron，过程行照常可见', () => {
    const entries = turnEntries().filter((entry) => entry.kind !== 'terminal')
    const wrapper = mount(TranscriptView, { props: { entries, running: true } })
    expect(wrapper.find('[data-testid="terminal-row"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="reasoning-toggle"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('执行了命令')
  })

  it('awaiting_user 等待类终态不折叠（问卷作答期间过程行可见）', () => {
    const entries = [
      ...turnEntries().filter((entry) => entry.kind !== 'terminal'),
      {
        id: 'terminal_run2',
        kind: 'terminal',
        terminal: { status: 'awaiting_user', answer: '', error: null, stats: {} },
        ts: BASE_TS + 9000,
      } as TerminalEntry,
    ]
    const wrapper = mount(TranscriptView, { props: { entries, running: false } })
    const header = wrapper.find('[data-testid="terminal-row"]')
    expect(header.exists()).toBe(true)
    expect(header.element.tagName).toBe('DIV')
    expect(header.attributes('aria-expanded')).toBeUndefined()
    // 过程行保持可见（等待期不收起）
    expect(wrapper.find('[data-testid="reasoning-toggle"]').exists()).toBe(true)
  })

  it('多回合：各自折叠，时长从各自回合起点计算', async () => {
    const first = turnEntries()
    const second: WorkbenchEntry[] = [
      { id: 'u2', kind: 'message', role: 'user', text: '再来一轮', streaming: false, ts: BASE_TS + 60_000 } as MessageEntry,
      toolEntry('t2'),
      messageEntry({ id: 'a3', role: 'assistant', text: '第二轮答案。', ts: BASE_TS + 62_000 }),
      {
        id: 'terminal_run3',
        kind: 'terminal',
        terminal: { status: 'completed', answer: '', error: null, stats: { duration_ms: 3000 } },
        ts: BASE_TS + 63_000,
      } as TerminalEntry,
    ]
    const wrapper = mount(TranscriptView, { props: { entries: [...first, ...second], running: false } })
    const headers = wrapper.findAll('[data-testid="terminal-row"]')
    expect(headers).toHaveLength(2)
    // 第一回合：无 stats → 从回合起点（u1 ts）到终态 ts
    expect(headers[0].text()).toMatch(/^已完成，用时 9秒$/)
    // 第二回合：stats.duration_ms 优先
    expect(headers[1].text()).toBe('已完成，用时 3秒')
    // 两回合均折叠
    expect(headers.every((h) => h.attributes('aria-expanded') === 'false')).toBe(true)
    expect(wrapper.text()).toContain('第二轮答案。')
  })
})

describe('TranscriptView 回合尾（助手文本后的 copy + 时钟行）', () => {
  function toolEntry(id: string): ToolEntry {
    return {
      id,
      kind: 'tool',
      ts: BASE_TS + 1000,
      callId: id,
      name: 'bash',
      args: { cmd: 'echo hi' },
      updates: [],
      status: 'ok',
      result: 'hi',
      artifacts: [],
      isError: false,
      executionOutcome: 'success',
    }
  }

  function turnEntries(): WorkbenchEntry[] {
    return [
      { id: 'u1', kind: 'message', role: 'user', text: '跑一下', streaming: false, ts: BASE_TS } as MessageEntry,
      toolEntry('t1'),
      messageEntry({ id: 'a1', role: 'assistant', text: '中间进度说明。', ts: BASE_TS + 1500 }),
      messageEntry({ id: 'a2', role: 'assistant', text: '最终答案。', ts: BASE_TS + 2000 }),
      {
        id: 'terminal_run1',
        kind: 'terminal',
        terminal: { status: 'completed', answer: '', error: null, stats: {} },
        ts: BASE_TS + 9000,
      } as TerminalEntry,
    ]
  }

  it('闭合回合渲染回合尾：copy 按钮 + 助手时钟（clock=end，时间取最后助手消息）', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    Object.defineProperty(window.navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    const wrapper = mount(TranscriptView, { props: { entries: turnEntries(), running: false } })
    const tail = wrapper.find('[data-testid="turn-tail"]')
    expect(tail.exists()).toBe(true)
    const copy = tail.find('button')
    expect(copy.attributes('aria-label')).toBe('复制')
    expect(tail.find('[data-testid="assistant-time"]').exists()).toBe(true)
    // copy 动作写最后一条助手文本
    await copy.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('最终答案。')
    delete (window.navigator as Partial<Navigator>).clipboard
  })

  it('进行中回合无回合尾；助手无文本（纯工具回合）也无回合尾', () => {
    const running = turnEntries().filter((entry) => entry.kind !== 'terminal')
    const runningView = mount(TranscriptView, { props: { entries: running, running: true } })
    expect(runningView.find('[data-testid="turn-tail"]').exists()).toBe(false)

    const toolOnly: WorkbenchEntry[] = [
      { id: 'u2', kind: 'message', role: 'user', text: '只跑工具', streaming: false, ts: BASE_TS } as MessageEntry,
      toolEntry('t2'),
      {
        id: 'terminal_run2',
        kind: 'terminal',
        terminal: { status: 'completed', answer: '', error: null, stats: {} },
        ts: BASE_TS + 5000,
      } as TerminalEntry,
    ]
    const toolOnlyView = mount(TranscriptView, { props: { entries: toolOnly, running: false } })
    expect(toolOnlyView.find('[data-testid="turn-tail"]').exists()).toBe(false)
  })

  it('回合尾的锚点属性：每回合首元素带 data-turn-anchor（导航轨跳转锚）', () => {
    const wrapper = mount(TranscriptView, { props: { entries: turnEntries(), running: false } })
    const anchors = wrapper.findAll('[data-turn-anchor]')
    expect(anchors).toHaveLength(1)
    expect(anchors[0].attributes('data-turn-anchor')).toBe('turn:0:u1')
  })
})

describe('回合尾 hover 揭示（上游 data-actions-reveal）', () => {
  function twoTurnEntries(): WorkbenchEntry[] {
    const terminal = (id: string, ts: number) =>
      ({
        id,
        kind: 'terminal',
        terminal: { status: 'completed', answer: '', error: null, stats: {} },
        ts,
      }) as TerminalEntry
    return [
      { id: 'u1', kind: 'message', role: 'user', text: '第一问', streaming: false, ts: BASE_TS } as MessageEntry,
      messageEntry({ id: 'a1', role: 'assistant', text: '第一答。', ts: BASE_TS + 1000 }),
      terminal('t_run1', BASE_TS + 2000),
      { id: 'u2', kind: 'message', role: 'user', text: '第二问', streaming: false, ts: BASE_TS + 3000 } as MessageEntry,
      messageEntry({ id: 'a2', role: 'assistant', text: '第二答。', ts: BASE_TS + 4000 }),
      terminal('t_run2', BASE_TS + 5000),
    ]
  }

  it('非最终回合尾带 data-actions-reveal="hover"，最终回合尾不带', () => {
    const wrapper = mount(TranscriptView, { props: { entries: twoTurnEntries(), running: false } })
    const tails = wrapper.findAll('[data-testid="turn-tail"]')
    expect(tails).toHaveLength(2)
    expect(tails[0].attributes('data-actions-reveal')).toBe('hover')
    expect(tails[1].attributes('data-actions-reveal')).toBeUndefined()
  })

  it('用户消息行带 data-chat-flow-kind="user"（更早行 hover 揭示的兄弟选择器锚点）', () => {
    const wrapper = mount(TranscriptView, { props: { entries: twoTurnEntries(), running: false } })
    const userRows = wrapper.findAll('[data-chat-flow-kind="user"]')
    expect(userRows.length).toBe(2)
  })
})
