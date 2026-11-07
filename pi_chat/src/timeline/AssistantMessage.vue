<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { MessageEntry } from '../projection/transcript'
import MarkdownContent from './MarkdownContent.vue'
import TextShimmer from './TextShimmer.vue'
import { formatRunDuration } from './clock'
import { STRINGS } from './strings'
import { whaleTailSvg } from './icons'
import markdownCss from '../vendor/dsh/ui-chat/src/client/chat/AssistantMarkdown.module.css'
import chatCss from '../vendor/dsh/ui-chat/src/client/chat/ChatView.module.css'

/*
 * 助手消息行。DOM 蓝图：ui-chat AssistantMarkdown.tsx（MIT）——
 * div.root[data-streaming] > div.body（flex 列，块间 16px）> MarkdownText。
 * streaming 时在正文下方渲染 RunningStatus 形态的打字指示行（.running，
 * 鲸尾静帧 + TextShimmer「深度求索中，用时 X 秒 ···」，蓝色令牌与 1s 步进
 * 时钟来自 vendored ChatView.module.css / locale.ts zh 字典）。
 * 偏离：上游 RunningWhaleTail 用 APNG 动画；本应用内联静止 SVG 帧。
 */
const props = defineProps<{ entry: MessageEntry }>()

const now = ref(Date.now())
let timer: number | undefined

watch(
  () => props.entry.streaming,
  (streaming) => {
    if (streaming) {
      now.value = Date.now()
      if (timer === undefined) {
        timer = window.setInterval(() => {
          now.value = Date.now()
        }, 1000)
      }
    } else if (timer !== undefined) {
      window.clearInterval(timer)
      timer = undefined
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (timer !== undefined) window.clearInterval(timer)
})

const runningLabel = computed(() => {
  const elapsed = formatRunDuration(Math.max(1000, now.value - props.entry.ts))
    .map((part) => part.text)
    .join('')
  return STRINGS.deepDivingFor.replace('{duration}', elapsed)
})
</script>

<template>
  <div :class="markdownCss.root" :data-streaming="entry.streaming ? '' : undefined">
    <div :class="markdownCss.body" data-testid="assistant-body">
      <MarkdownContent :text="entry.text" />
    </div>
    <div v-if="entry.streaming" :class="chatCss.running" data-testid="assistant-running" data-chat-running>
      <span class="visually-hidden-timeline" role="status" aria-live="polite" aria-atomic="true">{{ STRINGS.deepDiving }}</span>
      <span :class="chatCss.runningContent">
        <span :class="chatCss.runningIcon" aria-hidden="true" v-html="whaleTailSvg()" />
        <TextShimmer :text="runningLabel" :active="true" :class="chatCss.runningText" />
      </span>
    </div>
  </div>
</template>

<style>
/* 组件自有（非 vendor）： RunningStatus 的 role=status 需要 sr-only 文案，
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
