<script setup lang="ts">
import { computed } from 'vue'
import type { TerminalEntry } from '../projection/transcript'
import { errorText, statusText } from '../projection/labels'
import { formatRunDuration } from './clock'
import { iconSvg } from './icons'
import { STRINGS } from './strings'
import terminalCss from '../vendor/dsh/ui-chat/src/client/chat/TurnProcessNodeView.module.css'

/*
 * 终态行。DOM 蓝图：ui-chat TurnProcessNodeView.tsx（MIT）——
 * button.root（33px 头部行、底部 0.5px 分隔线、tertiary 色、hover 升级）
 *   > span.label（ellipsis 单行）> 时长片段 span.durationNumber（tabular-nums 等宽）
 * 文案规则平移上游：completed → 「已完成，用时 X 秒」；stopped → 「已停止」；
 * 失败 → 状态文案（labels.ts 的 statusText，含处理失败/预算耗尽等）。
 * 状态徽标为组件自有（.pi-terminal-badge，令牌着色；上游无徽标概念，状态由
 * 文案本身区分）；失败附加 errorText 错误行。
 * 折叠头（对齐上游 Turn process 折叠语义）：collapsible 时渲染为 disclosure
 * 按钮（aria-expanded + chevron），点击上抛 toggle；折叠体由 TranscriptView
 * 承载（回合过程行：思考/工具组）。等待交互（awaiting_*）不可折叠。
 */
const props = defineProps<{
  entry: TerminalEntry
  /** 回合起点（毫秒）；stats 无 duration 时以 起点→终态 计算，同上游 Math.max(1000, …)。 */
  startTs?: number
  /** 折叠头模式：可点击展开/收起回合过程行。 */
  collapsible?: boolean
  /** 折叠体当前是否展开（仅 collapsible 时有意义）。 */
  expanded?: boolean
}>()

const emit = defineEmits<{ toggle: [] }>()

const terminal = computed(() => props.entry.terminal)
const completed = computed(() => terminal.value.status === 'completed')

function formatRunDurationText(ms: number): string {
  return formatRunDuration(ms)
    .map((part) => part.text)
    .join('')
}

const durationText = computed(() => {
  if (!completed.value) return ''
  const stats = terminal.value.stats || {}
  if (typeof stats.duration_ms === 'number') return formatRunDurationText(stats.duration_ms)
  if (typeof stats.duration === 'number') return formatRunDurationText(stats.duration)
  if (typeof props.startTs === 'number') {
    return formatRunDurationText(Math.max(1000, props.entry.ts - props.startTs))
  }
  return ''
})

const badgeVisible = computed(() => !completed.value)
const badgeTone = computed(() => {
  switch (terminal.value.status) {
    case 'failed':
      return 'error'
    case 'stopped':
    case 'cancelled':
    case 'stopped_unconfirmed':
      return 'warning'
    case 'budget_exhausted':
    case 'context_overflow':
    case 'context_too_large':
    case 'unknown':
    case 'state_save_failed':
      return 'warning'
    default:
      return 'neutral'
  }
})

const errorMessage = computed(() => {
  const error = terminal.value.error
  if (!error?.message) return ''
  return errorText(error.code, error.message)
})

const chevron = computed(() =>
  iconSvg(props.expanded ? 'chevron-up' : 'chevron-down', 14),
)
</script>

<template>
  <component
    :is="collapsible ? 'button' : 'div'"
    :class="terminalCss.root"
    data-testid="terminal-row"
    :role="collapsible ? undefined : 'status'"
    :type="collapsible ? 'button' : undefined"
    :aria-expanded="collapsible ? String(expanded === true) : undefined"
    :data-collapsible="collapsible ? 'true' : undefined"
    @click="collapsible ? emit('toggle') : undefined"
  >
    <span :class="terminalCss.label" data-testid="terminal-label">
      <template v-if="completed && durationText">{{ STRINGS.turnProcessTook }}<span :class="terminalCss.durationNumber">{{ durationText }}</span></template>
      <template v-else>{{ statusText(terminal.status) }}</template>
    </span>
    <span
      v-if="badgeVisible"
      class="pi-terminal-badge"
      :data-tone="badgeTone"
      data-testid="terminal-badge"
    >{{ statusText(terminal.status) }}</span>
    <span
      v-if="collapsible"
      class="pi-terminal-chevron"
      data-testid="terminal-chevron"
      aria-hidden="true"
      v-html="chevron"
    />
    <span v-if="errorMessage" class="pi-terminal-error" data-testid="terminal-error">{{ errorMessage }}</span>
  </component>
</template>

<style>
/* 组件自有（非 vendor）：状态徽标与失败错误行，令牌着色。
   上游 TurnProcessNodeView 不带徽标；徽标沿用模式徽标的 caption chip 语言。 */
.pi-terminal-badge {
  flex: none;
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: var(--dsw-radius-sm, 8px);
  background: var(--dsw-alias-interactive-bg-hover, rgba(0, 0, 0, 0.04));
  color: var(--dsw-alias-label-secondary, #545557);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}

.pi-terminal-badge[data-tone='error'] {
  background: color-mix(in srgb, var(--dsw-alias-state-error-primary, #c0392b) 10%, transparent);
  color: var(--dsw-alias-state-error-primary, #c0392b);
}

.pi-terminal-badge[data-tone='warning'] {
  background: color-mix(in srgb, var(--dsw-alias-state-warn-primary, #b8860b) 12%, transparent);
  color: var(--dsw-alias-state-warn-primary, #b8860b);
}

.pi-terminal-error {
  flex: 1 1 100%;
  min-width: 0;
  overflow: hidden;
  color: var(--dsw-alias-label-secondary, #545557);
  font-size: var(--dsh-content-font-size-secondary, 13px);
  line-height: calc(20px + var(--dsh-content-font-delta-secondary, 0px));
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 组件自有：折叠头 chevron（上游 Turn process 头部的展开指示）。 */
button[data-testid='terminal-row'] {
  width: 100%;
  cursor: pointer;
  text-align: left;
}

button[data-testid='terminal-row'] .pi-terminal-chevron {
  flex: none;
  display: inline-flex;
  align-items: center;
  color: var(--dsw-alias-label-tertiary, #909094);
}

button[data-testid='terminal-row'] .pi-terminal-chevron svg {
  display: block;
}
</style>
