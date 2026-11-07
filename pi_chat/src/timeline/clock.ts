/**
 * 消息时钟与运行时长。忠实改写自上游 ui-chat/src/client/chat/message-chrome.ts
 * 的 formatMessageClock / formatRunDuration（MIT）；locale 模板以 STRINGS 常量
 * 内联（上游经 translate seat 注入，此处应用为纯 zh-CN，零依赖化）。
 */
import { STRINGS } from './strings'

export interface RunDurationPart {
  readonly text: string
  readonly numeric: boolean
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

/** elapsed ms → [小时][分][秒] 片段；负数取零、小数向下取整，进位同上游。 */
export function formatRunDuration(ms: number): RunDurationPart[] {
  const total = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor(total / 60) % 60
  const seconds = total % 60
  const parts: RunDurationPart[] = []
  if (hours > 0) parts.push({ text: String(hours), numeric: true }, { text: STRINGS.hourUnit, numeric: false })
  if (total >= 60) parts.push({ text: String(minutes), numeric: true }, { text: STRINGS.minuteUnit, numeric: false })
  parts.push({ text: String(seconds), numeric: true }, { text: STRINGS.secondUnit, numeric: false })
  return parts
}

/** 片段拼接为纯文本（供 aria / 测试断言）。 */
export function formatRunDurationText(ms: number): string {
  return formatRunDuration(ms)
    .map((part) => part.text)
    .join('')
}

/**
 * 紧凑消息时钟：同日 → HH:mm；今年 → {m}月{d}日 HH:mm；跨年 → {y}年{m}月{d}日 HH:mm。
 * 24 小时制补零，与上游一致。
 */
export function formatMessageClock(time: number, now: number = Date.now()): string {
  const d = new Date(time)
  const n = new Date(now)
  const clock = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  if (d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate()) {
    return clock
  }
  const template =
    d.getFullYear() === n.getFullYear()
      ? STRINGS.clockMd
      : STRINGS.clockYmd
  const date = template
    .replace('{y}', String(d.getFullYear()))
    .replace('{m}', String(d.getMonth() + 1))
    .replace('{d}', String(d.getDate()))
  return `${date} ${clock}`
}
