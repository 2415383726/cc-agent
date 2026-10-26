<template>
  <div class="permission-activity-card">
    <div class="permission-title">{{ label }}</div>
    <div class="permission-detail">{{ target }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  content?: any
}>()

const label = computed(() => {
  const decision = String(props.content?.decision || '')
  if (decision === 'allow_conversation') return '当前会话已允许'
  if (decision === 'allow_once') return '已允许本次执行'
  if (decision === 'deny') return '已拒绝执行'
  return '权限已更新'
})
const target = computed(() => String(props.content?.scriptName || props.content?.skillName || props.content?.toolName || 'operation'))
</script>

<style scoped>
.permission-activity-card {
  border: 1px solid rgba(71, 85, 105, 0.22);
  border-radius: 8px;
  padding: 10px 12px;
  background: #ffffff;
  color: #172033;
}

.permission-title {
  font-size: 13px;
  font-weight: 650;
}

.permission-detail {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
}
</style>
