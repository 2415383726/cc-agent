<template>
  <div class="activity-card">
    <div class="activity-title">{{ displayTitle }}</div>
    <pre>{{ pretty }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  activityType: string
  content: unknown
}>()

const displayTitle = computed(() => {
  if (props.activityType === 'cc_agent.guard_triggered') return '执行保护'
  if (props.activityType === 'cc_agent.tool_error') return '工具异常'
  return '分析过程'
})

const pretty = computed(() => {
  try {
    return JSON.stringify(props.content, null, 2)
  } catch (_) {
    return String(props.content || '')
  }
})
</script>
