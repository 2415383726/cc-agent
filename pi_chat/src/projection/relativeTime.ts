/**
 * 会话行的紧凑相对时间。分桶逻辑逐字移植自 DeepSeek Harness
 * `ui-primitives/src/relative-time.ts`（MIT），使两处展示同一会话时分桶一致；
 * 文案按 pi_chat 的 zh-CN 基线输出（「刚刚」「4分钟前」「3小时前」）。
 */

/** 相对时间桶（与上游 RelativeTimeUnit 一致）。 */
export type RelativeTimeUnit = 'now' | 'minutes' | 'hours' | 'days' | 'months' | 'years'

/** 结构化相对时间：桶 + 数量（now 桶为 0）。 */
export interface RelativeTime {
  unit: RelativeTimeUnit
  n: number
}

/** 紧凑相对时间分桶；now 注入保证纯函数渲染。 */
export function relativeTime(at: number, now: number): RelativeTime {
  const MIN = 60_000
  const HOUR = 3_600_000
  const DAY = 86_400_000
  const diff = Math.max(0, now - at)
  if (diff < MIN) return { unit: 'now', n: 0 }
  if (diff < HOUR) return { unit: 'minutes', n: Math.floor(diff / MIN) }
  if (diff < DAY) return { unit: 'hours', n: Math.floor(diff / HOUR) }
  if (diff < 30 * DAY) return { unit: 'days', n: Math.floor(diff / DAY) }
  if (diff < 365 * DAY) return { unit: 'months', n: Math.floor(diff / (30 * DAY)) }
  return { unit: 'years', n: Math.floor(diff / (365 * DAY)) }
}

const UNIT_ZH: Record<Exclude<RelativeTimeUnit, 'now'>, string> = {
  minutes: '分钟',
  hours: '小时',
  days: '天',
  months: '个月',
  years: '年',
}

/** zh-CN 行内文案：刚刚 / 4分钟前 / 3小时前 / 2天前 / 4个月前 / 1年前。 */
export function relativeTimeLabel(at: number, now: number): string {
  const { unit, n } = relativeTime(at, now)
  if (unit === 'now') return '刚刚'
  return `${n}${UNIT_ZH[unit]}前`
}
