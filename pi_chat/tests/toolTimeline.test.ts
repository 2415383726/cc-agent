import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { classifyTool, formatToolBody, toolRowState, toolSummary, toolTitle } from '../src/timeline/toolModel'
import { groupTimeline, groupTitle } from '../src/timeline/grouping'
import ToolCard from '../src/timeline/ToolCard.vue'
import ToolGroupRow from '../src/timeline/ToolGroupRow.vue'
import SkillRow from '../src/timeline/SkillRow.vue'
import CompactionRow from '../src/timeline/CompactionRow.vue'
import type { CompactionEntry, SkillEntry, ToolEntry, WorkbenchEntry } from '../src/projection/transcript'

const BASE_TS = new Date('2026-11-07T10:00:00').getTime()

function toolEntry(partial: Partial<ToolEntry>): ToolEntry {
  return {
    id: 't1',
    kind: 'tool',
    callId: 'call_1',
    name: 'lookup_order',
    args: {},
    updates: [],
    status: 'ok',
    result: '',
    artifacts: [],
    isError: false,
    executionOutcome: 'executed',
    ts: BASE_TS,
    ...partial,
  }
}

function skillEntry(partial: Partial<SkillEntry> = {}): SkillEntry {
  return {
    id: 's1',
    kind: 'skill',
    skill: 'refund-policy',
    action: 'activate',
    source: 'app',
    activatedBy: 'model',
    ts: BASE_TS,
    ...partial,
  }
}

function compactionEntry(partial: Partial<CompactionEntry> = {}): CompactionEntry {
  return {
    id: 'c1',
    kind: 'compaction',
    phase: 'end',
    tokensBefore: 48_210,
    summaryChars: 612,
    ts: BASE_TS,
    ...partial,
  }
}

/* 纯函数 seam：variant 分类 / 中文标题 / 摘要派生 / 参数格式化 / 状态映射。 */

describe('toolModel（工具行纯函数）', () => {
  it('classifyTool 按上游映射工具名分类，未知工具落 others', () => {
    expect(classifyTool('bash')).toBe('bash')
    expect(classifyTool('web_search')).toBe('search')
    expect(classifyTool('read')).toBe('read')
    expect(classifyTool('apply_patch')).toBe('edit')
    expect(classifyTool('run_code')).toBe('code')
    expect(classifyTool('lookup_order')).toBe('others')
  })

  it('toolTitle 给出 zh 变体标题，通用工具 titled 工具调用', () => {
    expect(toolTitle('bash')).toBe('运行命令')
    expect(toolTitle('web_search')).toBe('搜索')
    expect(toolTitle('lookup_order')).toBe('工具调用')
  })

  it('toolSummary 通用工具以工具名开头并拼接首个字符串参数', () => {
    expect(toolSummary(toolEntry({ name: 'lookup_order', args: { order_id: 'A-1042' } })))
      .toBe('lookup_order · A-1042')
  })

  it('toolSummary bash 变体取 command/description 首行', () => {
    expect(toolSummary(toolEntry({ name: 'bash', args: { command: 'echo hi\necho second' } })))
      .toBe('echo hi')
  })

  it('formatToolBody 将参数对象格式化为两空格缩进 JSON', () => {
    expect(formatToolBody('others', { order_id: 'A-1042' })).toBe('{\n  "order_id": "A-1042"\n}')
  })

  it('formatToolBody 非对象参数原样返回（PartialArguments 语义外溢回退）', () => {
    expect(formatToolBody('others', 'raw-truncated')).toBe('raw-truncated')
    expect(formatToolBody('others', undefined)).toBeNull()
  })

  it('toolRowState 映射投影状态：运行族→running，error→error，stopped/not_executed→stopped，unknown→stopped', () => {
    expect(toolRowState('running')).toBe('running')
    expect(toolRowState('awaiting_approval')).toBe('running')
    expect(toolRowState('ok')).toBe('ok')
    expect(toolRowState('error')).toBe('error')
    expect(toolRowState('stopped')).toBe('stopped')
    expect(toolRowState('not_executed')).toBe('stopped')
    expect(toolRowState('unknown')).toBe('stopped')
  })
})

/* 纯函数 seam：连续工具活动分组与分组头标题拼装。 */

describe('grouping（工具时间线分组）', () => {
  it('连续 tool/skill/compaction 归入同组，message/reasoning/note/terminal 保持单条', () => {
    const entries: WorkbenchEntry[] = [
      toolEntry({ id: 't1' }),
      skillEntry({ id: 's1' }),
      compactionEntry({ id: 'c1' }),
    ]
    const segments = groupTimeline(entries, false)
    expect(segments).toHaveLength(1)
    expect(segments[0]?.kind).toBe('tool-group')
    if (segments[0]?.kind === 'tool-group') {
      expect(segments[0].entries.map((entry) => entry.id)).toEqual(['t1', 's1', 'c1'])
    }
  })

  it('message 打断连续工具活动：前后各自成组', () => {
    const entries: WorkbenchEntry[] = [
      toolEntry({ id: 't1' }),
      { id: 'm1', kind: 'message', role: 'assistant', text: '正文', streaming: false, ts: BASE_TS },
      toolEntry({ id: 't2' }),
    ]
    const segments = groupTimeline(entries, false)
    expect(segments.map((segment) => segment.kind)).toEqual(['tool-group', 'single', 'tool-group'])
  })

  it('组内成员不含内部工具（ask_user/activate_skill/read_skill_resource 由投影隐藏，分组侧再守一道）', () => {
    const entries: WorkbenchEntry[] = [
      toolEntry({ id: 't1', callId: 'ask_1', name: 'ask_user' }),
      skillEntry({ id: 's1', action: 'read' }),
    ]
    const segments = groupTimeline(entries, false)
    const group = segments.find((segment) => segment.kind === 'tool-group')
    if (group?.kind === 'tool-group') {
      expect(group.entries.map((entry) => entry.id)).toEqual(['s1'])
    }
    expect(groupTimeline([toolEntry({ id: 't1', name: 'activate_skill' })], false)).toHaveLength(0)
    expect(groupTimeline([toolEntry({ id: 't1', name: 'read_skill_resource' })], false)).toHaveLength(0)
  })

  it('组 running 取决于成员工具是否处于 running 状态', () => {
    expect(groupTimeline([toolEntry({ status: 'running' })], true)[0]?.running).toBe(true)
    expect(groupTimeline([toolEntry({ status: 'ok' })], true)[0]?.running).toBe(false)
    expect(groupTimeline([toolEntry({ status: 'awaiting_approval' })], false)[0]?.running).toBe(false)
  })

  it('groupTitle：单类别已调用工具；双类别去共享前缀「已」以「并」连接', () => {
    expect(groupTitle([{ kind: 'tools', count: 2 }], false)).toBe('已调用工具')
    expect(groupTitle([{ kind: 'tools', count: 1 }, { kind: 'commands', count: 1 }], false))
      .toBe('已调用工具并执行了命令')
  })

  it('groupTitle：三类别逗号连接，超三类加「等」', () => {
    const three = [
      { kind: 'tools', count: 1 },
      { kind: 'commands', count: 1 },
      { kind: 'read', count: 2 },
    ]
    expect(groupTitle(three, false)).toBe('已调用工具，执行了命令，已读取文件')
    const four = [...three, { kind: 'search', count: 1 }]
    expect(groupTitle(four, false)).toBe('已调用工具，执行了命令，已读取文件等')
  })

  it('groupTitle：运行中组显示 live 词（正在调用工具），无类别时回落已完成分析', () => {
    expect(groupTitle([{ kind: 'tools', count: 1 }], true)).toBe('正在调用工具')
    expect(groupTitle([{ kind: 'commands', count: 1 }], true)).toBe('正在运行命令')
    expect(groupTitle([], false)).toBe('已完成分析')
  })
})

/* 组件 seam（spec 测试决策 3）：@vue/test-utils + happy-dom 挂载，只断言外显行为。 */

describe('ToolCard（工具折叠卡）', () => {
  it('默认收起：标题 + 摘要 + 状态徽标（已完成），无参数/结果区', () => {
    const entry = toolEntry({ args: { order_id: 'A-1042' }, result: '订单 A-1042 · 已支付' })
    const wrapper = mount(ToolCard, { props: { entry } })
    const toggle = wrapper.find('[data-testid="tool-toggle"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.text()).toContain('工具调用')
    expect(toggle.text()).toContain('lookup_order · A-1042')
    const badge = wrapper.find('[data-testid="tool-status"]')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('已完成')
    expect(wrapper.attributes('data-state')).toBe('ok')
    expect(wrapper.find('[data-testid="tool-body"]').exists()).toBe(false)
  })

  it('点击展开：参数区为两空格缩进 JSON，结果区呈现结果文本；再点收起', async () => {
    const entry = toolEntry({ args: { order_id: 'A-1042' }, result: '订单 A-1042 · 已支付 · 12 天前下单' })
    const wrapper = mount(ToolCard, { props: { entry } })
    await wrapper.find('[data-testid="tool-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="tool-toggle"]').attributes('aria-expanded')).toBe('true')
    const body = wrapper.find('[data-testid="tool-body"]')
    expect(body.exists()).toBe(true)
    expect(wrapper.find('[data-testid="tool-input"]').text()).toBe('{\n  "order_id": "A-1042"\n}')
    expect(wrapper.find('[data-testid="tool-output"]').text()).toContain('12 天前下单')

    await wrapper.find('[data-testid="tool-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="tool-toggle"]').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-testid="tool-body"]').exists()).toBe(false)
  })

  it('运行中：徽标显示 运行中，data-state=running，行头有 shimmer 转态指示，参数可先行展开', () => {
    const entry = toolEntry({ status: 'running', args: { order_id: 'A-1042' }, result: '' })
    const wrapper = mount(ToolCard, { props: { entry } })
    expect(wrapper.find('[data-testid="tool-status"]').text()).toBe('运行中')
    expect(wrapper.attributes('data-state')).toBe('running')
    expect(wrapper.find('[data-testid="tool-toggle"] [data-shimmer]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tool-output"]').exists()).toBe(false)
  })

  it('失败：徽标显示 失败，折叠摘要与结果区均为错误着色，且失败结果不被吞掉', async () => {
    const entry = toolEntry({
      status: 'error',
      isError: true,
      args: { record: 'stale-14' },
      result: '工具执行失败：连接超时',
    })
    const wrapper = mount(ToolCard, { props: { entry } })
    expect(wrapper.find('[data-testid="tool-status"]').text()).toBe('失败')
    expect(wrapper.attributes('data-state')).toBe('error')
    const summary = wrapper.find('[data-testid="tool-summary"]')
    expect(summary.classes().join(' ')).toContain('errorSummary')

    // 失败结果仍可展开呈现（配对不变量：合成结果进入输出区并带错误着色）。
    await wrapper.find('[data-testid="tool-toggle"]').trigger('click')
    const output = wrapper.find('[data-testid="tool-output"]')
    expect(output.exists()).toBe(true)
    expect(output.text()).toContain('连接超时')
    expect(output.attributes('data-error')).toBeDefined()
  })

  it('tool.update 进度文本并入结果区（updates 先于 result）', async () => {
    const entry = toolEntry({ updates: ['已找到订单 A-1042'], result: '已支付 · 12 天前下单' })
    const wrapper = mount(ToolCard, { props: { entry } })
    await wrapper.find('[data-testid="tool-toggle"]').trigger('click')
    const output = wrapper.find('[data-testid="tool-output"]').text()
    expect(output.indexOf('已找到订单 A-1042')).toBeLessThan(output.indexOf('已支付'))
  })

  it('内部工具（ask_user）不渲染工具卡（组件侧再断言投影隐藏规则）', () => {
    for (const name of ['ask_user', 'activate_skill', 'read_skill_resource']) {
      const wrapper = mount(ToolCard, { props: { entry: toolEntry({ name }) } })
      expect(wrapper.find('[data-testid="tool-toggle"]').exists()).toBe(false)
      expect(wrapper.text()).toBe('')
    }
  })
})

describe('ToolGroupRow（已调用工具分组）', () => {
  it('默认展开：组头显示传入标题，体内容可见；点击组头收起/再展开', async () => {
    const wrapper = mount(ToolGroupRow, {
      props: { label: '已调用工具并执行了命令', activity: 'tools', running: false },
      slots: { default: '<div data-testid="group-member">成员行</div>' },
    })
    const header = wrapper.find('[data-testid="tool-group-header"]')
    expect(header.exists()).toBe(true)
    expect(header.text()).toContain('已调用工具并执行了命令')
    expect(header.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-testid="group-member"]').exists()).toBe(true)

    await header.trigger('click')
    expect(wrapper.find('[data-testid="tool-group-header"]').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-testid="group-member"]').exists()).toBe(false)

    await wrapper.find('[data-testid="tool-group-header"]').trigger('click')
    expect(wrapper.find('[data-testid="group-member"]').exists()).toBe(true)
  })

  it('进行中组：组头文本带 shimmer 指示', () => {
    const wrapper = mount(ToolGroupRow, {
      props: { label: '正在调用工具', activity: 'tools', running: true },
      slots: { default: '' },
    })
    expect(wrapper.find('[data-testid="tool-group-header"] [data-shimmer]').exists()).toBe(true)
  })

  it('组头 leading 图标随类别切换（命令类用 api 图标行）', () => {
    const wrapper = mount(ToolGroupRow, {
      props: { label: '执行了命令', activity: 'commands', running: false },
      slots: { default: '' },
    })
    expect(wrapper.find('[data-testid="tool-group-activity"][data-activity="commands"]').exists()).toBe(true)
  })
})

describe('SkillRow（加载技能行）', () => {
  it('折叠行显示 加载技能 · 技能名；点击展开说明卡（来源/激活方），再点收起', async () => {
    const wrapper = mount(SkillRow, { props: { entry: skillEntry() } })
    const toggle = wrapper.find('[data-testid="skill-toggle"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.text()).toContain('加载技能')
    expect(toggle.text()).toContain('refund-policy')
    expect(wrapper.find('[data-testid="skill-body"]').exists()).toBe(false)

    await toggle.trigger('click')
    expect(wrapper.find('[data-testid="skill-toggle"]').attributes('aria-expanded')).toBe('true')
    const body = wrapper.find('[data-testid="skill-body"]')
    expect(body.exists()).toBe(true)
    expect(body.text()).toContain('说明')
    expect(body.text()).toContain('app')
    expect(body.text()).toContain('model')

    await wrapper.find('[data-testid="skill-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="skill-body"]').exists()).toBe(false)
  })

  it('读取条目摘要带资料路径，展开显示资料路径与字符数', async () => {
    const wrapper = mount(SkillRow, {
      props: { entry: skillEntry({ id: 's2', action: 'read', path: 'guide.md', offset: 0, totalChars: 188 }) },
    })
    expect(wrapper.find('[data-testid="skill-summary"]').text()).toBe('refund-policy · guide.md')
    await wrapper.find('[data-testid="skill-toggle"]').trigger('click')
    const body = wrapper.find('[data-testid="skill-body"]').text()
    expect(body).toContain('guide.md')
    expect(body).toContain('188')
  })
})

describe('CompactionRow（压缩行）', () => {
  it('完成态：标题 上下文已压缩，摘要含压缩前 tokens 与摘要字符数', () => {
    const wrapper = mount(CompactionRow, { props: { entry: compactionEntry() } })
    const row = wrapper.find('[data-testid="compaction-row"]')
    expect(row.text()).toContain('上下文已压缩')
    expect(row.text()).toContain('48210')
    expect(row.text()).toContain('612')
  })

  it('进行态（compaction.start）：摘要显示 正在压缩… 且带 shimmer', () => {
    const wrapper = mount(CompactionRow, {
      props: { entry: compactionEntry({ phase: 'start', summaryChars: undefined }) },
    })
    const row = wrapper.find('[data-testid="compaction-row"]')
    expect(row.text()).toContain('正在压缩…')
    expect(row.find('[data-shimmer]').exists()).toBe(true)
  })
})
