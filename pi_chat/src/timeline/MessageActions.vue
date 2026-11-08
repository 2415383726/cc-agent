<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatMessageClock } from './clock'
import { iconSvg } from './icons'
import { writeClipboard } from '../vendor/dsh/ui-primitives/src/clipboard'
import { STRINGS } from './strings'
import actionsCss from '../vendor/dsh/ui-chat/src/client/chat/MessageIconActions.module.css'

/*
 * 消息 IconActions 行（Vue 重写）。DOM 蓝图：ui-chat MessageIconActions.tsx
 * （MIT）去掉 branch / usage / Tooltip：span.time（clock=start 在前、clock=end
 * 在 endInfo 内）+ button.action（copy ↔ check 图标切换即复制反馈）。
 * 图标显隐与时间戳排版全部来自 vendored MessageIconActions.module.css。
 */
const props = defineProps<{
  text: string
  time?: number
  clock: 'start' | 'end'
}>()

const copied = ref(false)
const clockLabel = computed(() => (props.time === undefined ? '' : formatMessageClock(props.time)))
const copyIcon = computed(() => iconSvg(copied.value ? 'check' : 'copy'))
const copyLabel = computed(() => (copied.value ? STRINGS.copied : STRINGS.copy))
const timeClass = computed(() =>
  props.clock === 'start' ? actionsCss.timeStart : actionsCss.timeEnd,
)

let resetTimer: number | undefined

async function onCopy(): Promise<void> {
  if (copied.value) return
  const accepted = await writeClipboard(props.text)
  if (!accepted) return
  copied.value = true
  if (resetTimer !== undefined) window.clearTimeout(resetTimer)
  resetTimer = window.setTimeout(() => {
    copied.value = false
  }, 1000)
}
</script>

<template>
  <div :class="actionsCss.actions" :data-clock="clock">
    <span v-if="clock === 'start' && time !== undefined" :class="timeClass" data-testid="user-time">
      {{ clockLabel }}
    </span>
    <button
      type="button"
      :class="actionsCss.action"
      :aria-label="copyLabel"
      :title="copyLabel"
      data-testid="user-copy"
      @click="onCopy"
    >
      <span v-html="copyIcon" />
    </button>
    <span v-if="clock === 'end'" :class="actionsCss.endInfo">
      <span v-if="time !== undefined" :class="timeClass" data-testid="assistant-time">{{ clockLabel }}</span>
    </span>
  </div>
</template>
