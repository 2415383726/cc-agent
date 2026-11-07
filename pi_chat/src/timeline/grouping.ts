/**
 * 工具时间线分组。平移上游 ui-chat conversation-nodes 的分组语义（MIT）：
 * 连续的「过程活动」条目（tool/skill/compaction）折入一个可折叠组，消息/
 * 思考/终态/备注把连续段打断；组头标题按类别计数拼装（step-process.ts 的
 * processTitle 语义），进行中组显示 live 词。
 * 偏离：上游按 turn/window 的增量重分组（ProcessState/TurnGroups）在本应用
 * 由投影扁平 entries 全量重算替代；组内 running 判据为「成员工具处于
 * running 状态」（awaiting_* 不是进行中，组头保持已完成词）。
 */
import type { CompactionEntry, SkillEntry, TerminalEntry, ToolEntry, WorkbenchEntry } from '../projection/transcript'
import { PROCESS_DONE, PROCESS_JOIN, PROCESS_LIVE } from './strings'

/** 上游 ProcessActivity（本契约涉及的子集；context/subagents/questions 不在事件面）。 */
export type ProcessActivity =
  | 'read' | 'readImage' | 'search' | 'write' | 'edit' | 'commands' | 'code'
  | 'webSearch' | 'webFetch' | 'plan' | 'tools'

/** 上游 process-activity.ts activity()：工具名 → 类别，未知落 tools。 */
function activityOf(name: string): ProcessActivity {
  if (name === 'read' || name === 'read_image' || name === 'web_fetch') return name === 'read_image' ? 'readImage' : 'read'
  if (name === 'grep' || name === 'glob' || name === 'web_search') return 'search'
  if (name === 'write') return 'write'
  if (name === 'edit' || name === 'apply_patch') return 'edit'
  if (['bash', 'pwsh', 'exec_command', 'write_stdin'].includes(name) || name.startsWith('terminal_')) return 'commands'
  if (name === 'run_code') return 'code'
  return 'tools'
}

/** 内部工具与投影 INTERNAL_TOOL_NAMES 一致：分组侧再守一道（组件不出现工具卡）。 */
const INTERNAL_TOOL_NAMES = new Set(['ask_user', 'activate_skill', 'read_skill_resource'])

export type GroupMember = ToolEntry | SkillEntry | CompactionEntry

export type TimelineSegment =
  | { kind: 'single'; entry: WorkbenchEntry }
  | {
    kind: 'tool-group'
    id: string
    entries: GroupMember[]
    counts: { kind: ProcessActivity; count: number }[]
    running: boolean
  }

/** 是否折入工具组的条目类型。visualize 卡片（带 visual 载荷）独立呈现，不折组。 */
function isGroupable(entry: WorkbenchEntry): entry is GroupMember {
  if (entry.kind === 'tool') {
    return (entry as ToolEntry).visual === undefined
  }
  return entry.kind === 'skill' || entry.kind === 'compaction'
}

/** 类别计数（按条目数；技能行计入 tools，压缩行不计数——上游压缩标记在组外）。 */
function countActivities(members: GroupMember[]): { kind: ProcessActivity; count: number }[] {
  const counts = new Map<ProcessActivity, number>()
  for (const member of members) {
    if (member.kind !== 'tool') continue
    const kind = activityOf(member.name)
    counts.set(kind, (counts.get(kind) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([kind, count]) => ({ kind, count }))
    .sort((left, right) => right.count - left.count)
}

/**
 * 连续 tool/skill/compaction 条目折组；单条也成组（上游任何过程段都有组头，
 * 且保证组件身份稳定：工具卡始终渲染在组体里）。内部工具名不产生条目。
 */
export function groupTimeline(entries: WorkbenchEntry[], _running: boolean): TimelineSegment[] {
  const segments: TimelineSegment[] = []
  let pending: GroupMember[] = []
  let pendingIds: string[] = []

  const flush = (): void => {
    if (pending.length === 0) return
    segments.push({
      kind: 'tool-group',
      id: `tool-group:${pendingIds[0]}`,
      entries: pending,
      counts: countActivities(pending),
      running: pending.some(
        (member) => member.kind === 'tool' && (member as ToolEntry).status === 'running',
      ),
    })
    pending = []
    pendingIds = []
  }

  for (const entry of entries) {
    if (isGroupable(entry)) {
      if (entry.kind === 'tool' && INTERNAL_TOOL_NAMES.has(entry.name)) continue
      pending.push(entry)
      pendingIds.push(entry.id)
      continue
    }
    flush()
    segments.push({ kind: 'single', entry })
  }
  flush()
  return segments
}

/**
 * 组头标题（上游 step-process.ts processTitle 的 zh 平移）：
 * 进行中取最高类别 live 词；闭合取前三类别 done 词——
 * 一个词原样；两个词以「并」连接且第二个词去共享前缀「已」；
 * 三个以上逗号连接、超出三个补「等」；无类别回落「已完成分析」。
 */
export function groupTitle(
  counts: readonly { kind: string; count: number }[],
  running: boolean,
): string {
  if (running) return PROCESS_LIVE[counts[0]?.kind ?? 'thinking'] ?? PROCESS_LIVE.tools
  const labels = counts.slice(0, 3).map(({ kind }) => PROCESS_DONE[kind] ?? PROCESS_DONE.tools)
  const first = labels[0]
  if (first === undefined) return PROCESS_DONE.thinking
  const continuation = (label: string): string => label.charAt(0).toLowerCase() + label.slice(1)
  const second = labels[1]
  if (second === undefined) return first
  const shared =
    first.startsWith(PROCESS_JOIN.sharedPrefix) && second.startsWith(PROCESS_JOIN.sharedPrefix)
  if (labels.length === 2) {
    const stripped = shared ? second.slice(PROCESS_JOIN.sharedPrefix.length) : second
    return PROCESS_JOIN.joinTwo.replace('{first}', first).replace('{second}', stripped)
  }
  const title = [first, ...labels.slice(1).map(continuation)].join(PROCESS_JOIN.comma)
  return counts.length > 3
    ? PROCESS_JOIN.more.replace('{title}', title)
    : title
}

/**
 * 回合折叠视图（对齐 DeepSeek Harness 的完成态行为）：回答完成后，回合的
 * 过程行（思考/工具组）折叠进「已完成，用时 X 秒」头部，文本消息保持原位
 * 可见；头部可展开还原原始穿插顺序。
 *
 * - 回合以用户消息为界；回合内含**非等待类**终态（completed/failed/stopped…）
 *   即视为闭合，可折叠。awaiting_user/awaiting_approval 是交互等待，不折叠。
 * - 折叠头取回合内最后一条非等待终态（终态即最终事实），提升到回合首位；
 *   其余条目保持原始顺序（展开时组与文本穿插如流式当时）。
 * - 进行中/无终态回合 header 为 null，照常平铺渲染。
 */
export type TurnView = {
  id: string
  /** 闭合回合（可折叠）；进行中/等待交互的回合为 false。 */
  closed: boolean
  /** 回合首条目 ts（毫秒），供「用时 X」从回合起点计算。 */
  startTs: number
  /** 提升为折叠头的终态；null = 平铺渲染（无终态或等待类）。 */
  header: TerminalEntry | null
  /** 回合开头的用户消息段（折叠头之前渲染，始终可见）。 */
  lead: TimelineSegment[]
  /** 原序段（已摘除提升的终态条目，不含 lead）。 */
  segments: TimelineSegment[]
}

const AWAITING_STATUSES = new Set(['awaiting_user', 'awaiting_approval'])

export function turnViews(entries: WorkbenchEntry[], _running: boolean): TurnView[] {
  const turns: WorkbenchEntry[][] = []
  for (const entry of entries) {
    const isUser = entry.kind === 'message' && (entry as { role?: string }).role === 'user'
    if (isUser || turns.length === 0) turns.push([])
    turns[turns.length - 1].push(entry)
  }

  return turns.map((turn, index) => {
    const terminals = turn.filter(
      (entry): entry is TerminalEntry =>
        entry.kind === 'terminal' && !AWAITING_STATUSES.has((entry as TerminalEntry).terminal.status),
    )
    const header = terminals.length > 0 ? terminals[terminals.length - 1] : null
    // 回合开头的用户消息为 lead（折叠头渲染在其后，对齐 DeepSeek 版式）
    let leadEnd = 0
    while (leadEnd < turn.length) {
      const entry = turn[leadEnd]
      if (!(entry.kind === 'message' && (entry as { role?: string }).role === 'user')) break
      leadEnd += 1
    }
    const flow = turn.filter((entry) => entry !== header)
    const lead = groupTimeline(flow.slice(0, leadEnd), false)
    const segments = groupTimeline(flow.slice(leadEnd), false)
    return {
      id: `turn:${index}:${turn[0]?.id ?? 'empty'}`,
      closed: header !== null,
      startTs: turn[0]?.ts ?? 0,
      header,
      lead,
      segments,
    }
  })
}
