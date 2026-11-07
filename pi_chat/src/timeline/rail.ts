/**
 * 回合导航轨的条目推导（纯函数）。平移上游 turn-rail-items.ts 的
 * 「已加载窗口」一侧（MIT）：每回合一个刻度，问题预览取回合首条用户消息
 * 文本，回答预览取回合内第一条非空助手文本。直接复用 turnViews 的回合
 * 切分与 id，保证刻度 id 与 TranscriptView 的 DOM 锚点（data-turn-anchor）
 * 一致。本应用无分页历史，「unloaded」锚点与 outline 合并不适用；预览
 * 截断在 JS 侧定界（DOM 层再由 CSS 行数截断兜底）。
 */
import { turnViews, type TurnView } from './grouping'
import type { MessageEntry, WorkbenchEntry } from '../projection/transcript'

export interface TurnRailItem {
  /** 回合视图 id（turnViews 的 id，同时是 DOM 锚点 data-turn-anchor 值）。 */
  readonly id: string
  /** 有界问题预览（回合首条用户消息）。 */
  readonly prompt: string
  /** 有界回答预览（回合首条非空助手文本）。 */
  readonly response: string
}

/** 预览上限（字符）：与上游「bounded preview」同级的信息量。 */
const PREVIEW_LIMIT = 160

function bounded(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > PREVIEW_LIMIT ? `${flat.slice(0, PREVIEW_LIMIT)}…` : flat
}

const isUserMessage = (entry: WorkbenchEntry): entry is MessageEntry =>
  entry.kind === 'message' && entry.role === 'user'
const isAssistantMessage = (entry: WorkbenchEntry): entry is MessageEntry =>
  entry.kind === 'message' && entry.role === 'assistant'

/** 回合首条用户消息与首条非空助手文本（lead 优先，其后按原序扫段）。 */
function turnPreview(turn: TurnView): { prompt: string; response: string } {
  let prompt = ''
  let response = ''
  for (const segment of [...turn.lead, ...turn.segments]) {
    if (segment.kind !== 'single') continue
    const entry = segment.entry
    if (prompt === '' && isUserMessage(entry)) prompt = bounded(entry.text)
    if (
      response === '' &&
      isAssistantMessage(entry) &&
      entry.text.trim() !== ''
    ) {
      response = bounded(entry.text)
    }
    if (prompt !== '' && response !== '') break
  }
  return { prompt, response }
}

export function railItems(entries: readonly WorkbenchEntry[]): TurnRailItem[] {
  return turnViews([...entries], false).map((turn) => ({
    id: turn.id,
    ...turnPreview(turn),
  }))
}
