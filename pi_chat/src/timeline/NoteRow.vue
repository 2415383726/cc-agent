<script setup lang="ts">
import type { NoteEntry } from '../projection/transcript'

/*
 * 备注行（abort 通知、回放提示等活动注记）。上游无一对一组件——按 Harness
 * 行语言以组件自有样式实现：caption 级 tertiary 文本行，语气经 data-tone
 * 着色（warning → 警示色、error → 错误色）。
 */
defineProps<{ entry: NoteEntry }>()
</script>

<template>
  <div class="pi-note-row" :data-tone="entry.tone || 'info'" data-testid="note-row">
    {{ entry.text }}
  </div>
</template>

<style>
/* 组件自有（非 vendor）：备注行，令牌着色的 caption 行。 */
.pi-note-row {
  padding: 2px 0;
  color: var(--dsw-alias-label-tertiary, rgba(0, 0, 0, 0.45));
  font-size: var(--dsh-content-font-size-secondary, 13px);
  line-height: calc(20px + var(--dsh-content-font-delta-secondary, 0px));
  overflow-wrap: anywhere;
}

.pi-note-row[data-tone='warning'] {
  color: var(--dsw-alias-state-warn-primary, #b8860b);
}

.pi-note-row[data-tone='error'] {
  color: var(--dsw-alias-state-error-primary, #c0392b);
}
</style>
