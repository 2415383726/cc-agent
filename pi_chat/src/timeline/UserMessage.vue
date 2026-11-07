<script setup lang="ts">
import type { MessageEntry } from '../projection/transcript'
import MessageActions from './MessageActions.vue'
import itemCss from '../vendor/dsh/ui-chat/src/client/chat/MessageItem.module.css'
import bubbleCss from '../vendor/dsh/ui-primitives/src/UserMessageBubble.module.css'

/*
 * 用户消息行。DOM 蓝图：ui-chat MessageItem.module.css .userRow（右对齐列，
 * gap 6）+ UserContent.tsx 的 .userStack（最大宽度按内容宽度轴的 0.702 份额）
 * + ui-primitives UserMessageBubble（--dsw-specific-bubble 气泡面、
 * radius-xl、10px 16px 内距、pre-wrap）。文案为纯文本（上游 user-text 同样
 * 不做 markdown）；气泡下方为 MessageActions（时钟在前 + 复制按钮）。
 */
defineProps<{ entry: MessageEntry }>()
</script>

<template>
  <div :class="itemCss.userRow">
    <div :class="itemCss.userStack">
      <div :class="bubbleCss.bubble" data-message-bubble data-testid="user-bubble">{{ entry.text }}</div>
    </div>
    <MessageActions :text="entry.text" :time="entry.ts" clock="start" />
  </div>
</template>
