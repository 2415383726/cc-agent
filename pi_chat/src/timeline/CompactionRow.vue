<script setup lang="ts">
import { computed } from 'vue'
import type { CompactionEntry } from '../projection/transcript'
import { COMPACTION_STRINGS } from './strings'
import { iconSvg } from './icons'
import TextShimmer from './TextShimmer.vue'
import css from '../vendor/dsh/ui-chat/src/client/chat/MessageItem.module.css'

/*
 * 压缩行。DOM 蓝图：ui-chat CompactionItem.tsx（MIT），类名零改动引用
 * vendored MessageItem.module.css 的 compaction 片段。图标同上游
 * （leading = api 场景图标，hover/focus 交换 chevron-right）。
 * 偏离：上游在窗口内含压缩摘要时展开 MarkdownText 正文；本契约的
 * compaction.start/end 事件不携带摘要文本，行不可展开（按钮 disabled），
 * 摘要槽呈现投影保留的 tokens/字符数；start 阶段以 shimmer 呈现进行态。
 */
const props = defineProps<{ entry: CompactionEntry }>()

const running = computed(() => props.entry.phase === 'start')

const summaryText = computed(() => {
  if (running.value) return COMPACTION_STRINGS.running
  const parts: string[] = []
  if (typeof props.entry.tokensBefore === 'number') parts.push(`压缩前 ${props.entry.tokensBefore} tokens`)
  if (typeof props.entry.summaryChars === 'number') parts.push(`摘要 ${props.entry.summaryChars} 字符`)
  return parts.join(' · ') || '压缩完成'
})

const apiIcon = iconSvg('api')
const chevronRight = iconSvg('chevron-right')
</script>

<template>
  <div :class="css.compactionRow" data-testid="compaction-row">
    <button
      type="button"
      :class="css.compactionButton"
      disabled
      :aria-label="`${COMPACTION_STRINGS.title}：${summaryText}`"
    >
      <span :class="css.compactionLeading" aria-hidden="true">
        <span :class="css.compactionContextIcon" data-compaction-icon="context" v-html="apiIcon" />
        <span :class="css.compactionDisclosureIcon" data-compaction-disclosure="collapsed" v-html="chevronRight" />
      </span>
      <span :class="css.compactionTitle">{{ COMPACTION_STRINGS.title }}</span>
      <span :class="css.compactionSep" aria-hidden="true" />
      <span :class="css.compactionSummary">
        <TextShimmer :text="summaryText" :active="running" />
      </span>
    </button>
  </div>
</template>
