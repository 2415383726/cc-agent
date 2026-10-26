<template>
  <section
    class="business-surface-pending"
    :data-surface="`${surface}-pending`"
    data-testid="business-surface-pending"
    aria-busy="true"
    :aria-label="label"
  >
    <div class="business-surface-pending__header">
      <span class="business-surface-pending__dot" aria-hidden="true" />
      <span>{{ label }}</span>
    </div>
    <div class="business-surface-pending__body" aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BusinessSurfaceType } from '../../lib/structuredContent'

const props = defineProps<{ surface: BusinessSurfaceType }>()

const labels: Record<BusinessSurfaceType, string> = {
  record: '正在整理业务档案',
  table: '正在整理业务表格',
  compare: '正在整理对比结果',
  timeline: '正在整理时间记录',
}

const label = computed(() => labels[props.surface])
</script>

<style scoped>
.business-surface-pending {
  contain: layout paint style;
  box-sizing: border-box;
  width: 100%;
  min-height: 116px;
  margin: 12px 0 16px;
  border: 1px solid var(--cc-agent-line);
  border-radius: var(--cc-agent-card-radius);
  background: var(--cc-agent-surface);
  overflow: hidden;
}

.business-surface-pending__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 13px 16px;
  border-bottom: 1px solid var(--cc-agent-muted-line);
  box-shadow: inset 3px 0 0 var(--cc-agent-primary);
  color: var(--cc-agent-muted);
  font-size: 13px;
  font-weight: 650;
}

.business-surface-pending__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cc-agent-primary);
}

.business-surface-pending__body {
  display: grid;
  grid-template-columns: 1.3fr 1fr 0.7fr;
  gap: 18px;
  padding: 18px 16px 20px;
}

.business-surface-pending__body span {
  height: 10px;
  border-radius: 3px;
  background: var(--cc-agent-surface-alt);
}

@media (max-width: 560px) {
  .business-surface-pending__body {
    grid-template-columns: 1fr;
    gap: 10px;
  }
}
</style>
