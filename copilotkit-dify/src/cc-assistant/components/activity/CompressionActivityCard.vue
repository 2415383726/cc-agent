<template>
  <div class="compression-separator" role="status" aria-live="polite">
    <span class="compression-line" aria-hidden="true" />
    <span class="compression-label">
      <span v-if="isStarted" class="compression-pulse" aria-hidden="true" />
      <span class="compression-title">{{ titleText }}</span>
      <span v-if="detailText" class="compression-detail">{{ detailText }}</span>
    </span>
    <span class="compression-line" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  activityType?: string
  content?: unknown
}>()

const metadata = computed<Record<string, any>>(() => {
  const raw = props.content as any
  if (raw?.metadata && typeof raw.metadata === 'object') return raw.metadata
  return raw && typeof raw === 'object' ? raw : {}
})

const isStarted = computed(() => String(metadata.value.status || '').toLowerCase() === 'started')

const titleText = computed(() => isStarted.value ? '上下文压缩中' : '上下文已压缩')

const detailText = computed(() => {
  if (isStarted.value) return ''
  const summarized = Number(metadata.value.summarized_messages || 0)
  const truncated = Number(metadata.value.truncated_observations || 0)
  const parts = []
  if (summarized > 0) parts.push(`已整理 ${summarized} 条消息`)
  if (truncated > 0) parts.push(`压缩 ${truncated} 个工具结果`)
  return parts.join(' · ')
})
</script>

<style scoped>
.compression-separator {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  margin: 18px 0;
  color: #667085;
}

.compression-line {
  height: 1px;
  flex: 1 1 auto;
  min-width: 24px;
  background: #e5e7eb;
}

.compression-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #667085;
  font-size: 13px;
  line-height: 1.5;
  white-space: nowrap;
}

.compression-title {
  color: #667085;
  font-weight: 500;
}

.compression-detail {
  color: #98a2b3;
}

.compression-pulse {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #667085;
  animation: compression-pulse 900ms ease-in-out infinite;
}

@keyframes compression-pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.85);
  }

  50% {
    opacity: 1;
    transform: scale(1);
  }
}

@media (max-width: 520px) {
  .compression-label {
    white-space: normal;
  }
}
</style>
