<script setup lang="ts">
import type { MessageEntry } from '../projection/transcript'
import { formatFileSize } from '../projection/labels'
import MessageActions from './MessageActions.vue'
import itemCss from '../vendor/dsh/ui-chat/src/client/chat/MessageItem.module.css'
import bubbleCss from '../vendor/dsh/ui-primitives/src/UserMessageBubble.module.css'

/*
 * 用户消息行。DOM 蓝图：ui-chat MessageItem.module.css .userRow（右对齐列，
 * gap 6）+ UserContent.tsx 的 .userStack（最大宽度按内容宽度轴的 0.702 份额）
 * + ui-primitives UserMessageBubble（--dsw-specific-bubble 气泡面、
 * radius-xl、10px 16px 内距、pre-wrap）。文案为纯文本（上游 user-text 同样
 * 不做 markdown）；气泡下方为 MessageActions（时钟在前 + 复制按钮）。
 * 附件只展示安全元数据 chips（名称/类型/大小，票 08）：无内容访问、无链接，
 * 与 composer 待发送 chips 同一信息面。
 */
defineProps<{ entry: MessageEntry }>()
</script>

<template>
  <div :class="itemCss.userRow">
    <div :class="itemCss.userStack">
      <div :class="bubbleCss.bubble" data-message-bubble data-testid="user-bubble">{{ entry.text }}</div>
      <!-- 附件安全元数据 chips：与气泡同栈，只读展示。 -->
      <div v-if="entry.files?.length" class="pi-user-files">
        <span
          v-for="file in entry.files"
          :key="file.id || file.name"
          class="pi-user-file"
          data-testid="message-file-chip"
        >
          {{ file.name || file.id }} · {{ file.mimeType || file.type || '文件' }} · {{ formatFileSize(file.size) }}
        </span>
      </div>
    </div>
    <MessageActions :text="entry.text" :time="entry.ts" clock="start" />
  </div>
</template>

<style>
/* 组件自有（非 vendor）：用户消息附件的安全元数据 chips（名称/类型/大小）。 */
.pi-user-files {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 2px;
}

.pi-user-file {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border: 0.5px solid var(--dsw-alias-border-l3);
  border-radius: var(--dsw-radius-sm);
  background: var(--dsw-alias-interactive-bg-hover);
  color: var(--dsw-alias-label-secondary);
  font-size: 12px;
  line-height: 18px;
  overflow-wrap: anywhere;
}
</style>
