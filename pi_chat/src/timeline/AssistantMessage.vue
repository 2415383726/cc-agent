<script setup lang="ts">
import type { MessageEntry } from '../projection/transcript'
import MarkdownContent from './MarkdownContent.vue'
import markdownCss from '../vendor/dsh/ui-chat/src/client/chat/AssistantMarkdown.module.css'

/*
 * 助手消息行。DOM 蓝图：ui-chat AssistantMarkdown.tsx（MIT）——
 * div.root[data-streaming] > div.body（flex 列，块间 16px）> MarkdownText。
 * 运行中指示行不在此渲染：进程行会追加到消息之后，挂在这里会停在时间线
 * 中间；它由 TranscriptView 在回合末尾统一渲染（RunningStatusRow.vue）。
 */
defineProps<{ entry: MessageEntry }>()

</script>

<template>
  <div :class="markdownCss.root" :data-streaming="entry.streaming ? '' : undefined">
    <div :class="markdownCss.body" data-testid="assistant-body">
      <MarkdownContent :text="entry.text" />
    </div>
  </div>
</template>
