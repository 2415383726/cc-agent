<template>
  <div class="script-activity-card">
    <div class="script-title">{{ skillName }} / {{ scriptName }}</div>
    <div class="script-meta">{{ status }} · {{ duration }}ms</div>
    <pre v-if="stdout">{{ stdout }}</pre>
    <pre v-if="stderr" class="stderr">{{ stderr }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  content?: any
}>()

const skillName = computed(() => String(props.content?.skillName || 'skill'))
const scriptName = computed(() => String(props.content?.scriptName || 'script'))
const status = computed(() => String(props.content?.status || 'completed'))
const duration = computed(() => Number(props.content?.durationMs || 0))
const stdout = computed(() => String(props.content?.stdoutPreview || '').trim())
const stderr = computed(() => String(props.content?.stderrPreview || '').trim())
</script>

<style scoped>
.script-activity-card {
  border: 1px solid rgba(71, 85, 105, 0.22);
  border-radius: 8px;
  padding: 10px 12px;
  background: #ffffff;
  color: #172033;
}

.script-title {
  font-size: 13px;
  font-weight: 650;
}

.script-meta {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
}

pre {
  margin: 8px 0 0;
  max-height: 140px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 12px;
  background: #f8fafc;
  border-radius: 6px;
  padding: 8px;
}

.stderr {
  color: #9f1239;
}
</style>
