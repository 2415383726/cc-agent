<template>
  <div class="skill-activity-card" aria-label="skill activity">
    <span class="skill-activity-icon" aria-hidden="true">✓</span>
    <span class="skill-activity-name">{{ model.label }}</span>
    <span class="skill-activity-status">{{ model.status }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { skillActivityViewModel } from '../../lib/skillActivity'

const props = defineProps<{
  content?: unknown
}>()

const model = computed(() =>
  skillActivityViewModel(
    props.content && typeof props.content === 'object' && !Array.isArray(props.content)
      ? props.content as Record<string, unknown>
      : {},
  ),
)
</script>
