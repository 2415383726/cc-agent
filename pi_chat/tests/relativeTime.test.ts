import { describe, expect, it } from 'vitest'

import { relativeTime, relativeTimeLabel } from '../src/projection/relativeTime'

const NOW = Date.UTC(2026, 10, 7, 8, 0, 0) // 2026-11-07T08:00:00Z
const MIN = 60_000
const HOUR = 3_600_000
const DAY = 86_400_000

describe('relativeTime 分桶（对齐 Harness relative-time）', () => {
  it('一分钟内是 now 桶', () => {
    expect(relativeTime(NOW - 30_000, NOW)).toEqual({ unit: 'now', n: 0 })
  })

  it('一小时内按分钟分桶', () => {
    expect(relativeTime(NOW - 4 * MIN, NOW)).toEqual({ unit: 'minutes', n: 4 })
    expect(relativeTime(NOW - 59 * MIN, NOW)).toEqual({ unit: 'minutes', n: 59 })
  })

  it('一天内按小时、30 天内按天分桶', () => {
    expect(relativeTime(NOW - 3 * HOUR, NOW)).toEqual({ unit: 'hours', n: 3 })
    expect(relativeTime(NOW - 2 * DAY, NOW)).toEqual({ unit: 'days', n: 2 })
  })

  it('更早按月/年分桶', () => {
    expect(relativeTime(NOW - 40 * DAY, NOW)).toEqual({ unit: 'months', n: 1 })
    expect(relativeTime(NOW - 400 * DAY, NOW)).toEqual({ unit: 'years', n: 1 })
  })

  it('未来时间按 now 处理（不产生负数）', () => {
    expect(relativeTime(NOW + 5 * MIN, NOW)).toEqual({ unit: 'now', n: 0 })
  })
})

describe('relativeTimeLabel zh-CN 文案', () => {
  it('now 桶为「刚刚」', () => {
    expect(relativeTimeLabel(NOW - 10_000, NOW)).toBe('刚刚')
  })

  it('分钟桶为「4分钟」样式（对齐 dsh 会话行，无「前」）', () => {
    expect(relativeTimeLabel(NOW - 4 * MIN, NOW)).toBe('4分钟')
    expect(relativeTimeLabel(NOW - 1 * MIN, NOW)).toBe('1分钟')
  })

  it('小时/天/月/年桶为「3小时」「2天」「4个月」「1年」样式', () => {
    expect(relativeTimeLabel(NOW - 3 * HOUR, NOW)).toBe('3小时')
    expect(relativeTimeLabel(NOW - 2 * DAY, NOW)).toBe('2天')
    expect(relativeTimeLabel(NOW - 120 * DAY, NOW)).toBe('4个月')
    expect(relativeTimeLabel(NOW - 400 * DAY, NOW)).toBe('1年')
  })
})
