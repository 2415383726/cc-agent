<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import TextShimmer from './TextShimmer.vue'
import { formatRunDuration } from './clock'
import { STRINGS } from './strings'
import { whaleTailSvg } from './icons'
import chatCss from '../vendor/dsh/ui-chat/src/client/chat/ChatView.module.css'

/*
 * 运行中指示行（上游 RunningStatus 形态：鲸尾静帧 + TextShimmer「深度求索中，
 * 用时 X 秒 ···」）。
 *
 * 它不属于任何一条助手消息：进程行（思考/工具组/技能）会不断追加到消息之后，
 * 若把指示挂在「当时正在流式的助手条目」内部，它就会停在时间线中间。本组件由
 * TranscriptView 渲染在回合末尾，保证它始终是最后一行。
 *
 * 偏离：上游 RunningWhaleTail 用 APNG 动画；本应用内联静止 SVG 帧。
 */
const props = defineProps<{ startTs: number }>()

const now = ref(Date.now())
let timer: number | undefined

function startClock(): void {
  now.value = Date.now()
  if (timer === undefined) {
    timer = window.setInterval(() => {
      now.value = Date.now()
    }, 1000)
  }
}

function stopClock(): void {
  if (timer !== undefined) {
    window.clearInterval(timer)
    timer = undefined
  }
}

watch(() => props.startTs, startClock, { immediate: true })
onBeforeUnmount(stopClock)

const runningLabel = computed(() => {
  const elapsed = formatRunDuration(Math.max(1000, now.value - props.startTs))
    .map((part) => part.text)
    .join('')
  return STRINGS.deepDivingFor.replace('{duration}', elapsed)
})
</script>

<template>
  <div :class="chatCss.running" data-testid="assistant-running" data-chat-running>
    <span class="visually-hidden-timeline" role="status" aria-live="polite" aria-atomic="true">{{ STRINGS.deepDiving }}</span>
    <span :class="chatCss.runningContent">
      <span :class="chatCss.runningIcon" aria-hidden="true" v-html="whaleTailSvg()" />
      <TextShimmer :text="runningLabel" :active="true" :class="chatCss.runningText" />
    </span>
  </div>
</template>

<style>
/* 组件自有（非 vendor）：RunningStatus 的 role=status 需要 sr-only 文案，
   复用上游 accessibility.module.css 的 visuallyHidden 语义（同令牌体系）。 */
.visually-hidden-timeline {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
