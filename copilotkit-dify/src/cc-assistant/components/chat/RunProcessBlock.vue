<template>
  <section class="run-process-shell" :data-mode="mode" data-align="assistant">
    <details
      data-testid="run-process-summary"
      :open="expanded"
      class="run-process-summary"
      @toggle="handleSummaryToggle"
    >
      <summary class="run-process-summary__row">
        <span class="run-process-summary__chevron" aria-hidden="true" />
        <span class="run-process-summary__title">{{ summaryText }}</span>
        <span v-if="activeStatusLabel" class="run-process-summary__status">{{ activeStatusLabel }}</span>
      </summary>
    </details>

    <div v-if="expanded" data-testid="run-process-content" class="run-process-content">
      <slot />

      <div v-if="isPermissionInterrupt" class="run-process-permission">
        <div class="run-process-permission__title">操作授权</div>
        <p>{{ permissionDetailText }}</p>
        <div class="run-process-permission__actions">
          <button
            v-for="action in permissionActions"
            :key="action.value"
            type="button"
            :value="action.value"
            :class="{ danger: action.value === 'deny' }"
            @click="resolvePermission(action.value, action.label)"
          >
            {{ action.label }}
          </button>
        </div>
      </div>

      <InterruptCard
        v-else-if="isGenericInterrupt"
        class="run-process-interrupt"
        :question="interruptQuestion!"
        :resolve="resolveGenericInterrupt"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import InterruptCard from './InterruptCard.vue'
import type { InterruptQuestion } from '../../lib/question'
import { buildInterruptResumePayload } from '../../lib/question'
import type { RunProcessDisplayMode, RunProcessInterruptState } from '../../lib/runProcess'

const props = withDefaults(defineProps<{
  mode?: RunProcessDisplayMode
  summary?: string
  defaultExpanded?: boolean
  interruptState?: RunProcessInterruptState | null
}>(), {
  mode: 'expanded',
  summary: '',
  defaultExpanded: false,
  interruptState: null,
})

const expanded = ref(props.defaultExpanded)

watch(
  () => [props.defaultExpanded, props.mode],
  () => {
    expanded.value = props.defaultExpanded
  },
)

const interruptQuestion = computed<InterruptQuestion | null>(() => props.interruptState?.result || null)
const summaryText = computed(() => props.summary || (props.mode === 'collapsed' ? '分析已完成' : '分析过程'))
const activeStatusLabel = computed(() => {
  if (interruptQuestion.value) return '等待确认'
  if (props.mode === 'expanded') return '进行中'
  return ''
})
const isPermissionInterrupt = computed(() => interruptQuestion.value?.purpose === 'permission')
const isGenericInterrupt = computed(() => Boolean(interruptQuestion.value) && !isPermissionInterrupt.value)
const permissionDetailText = computed(() => {
  const target = permissionTarget(interruptQuestion.value)
  return target ? `将要执行：${target}` : '将要执行一个需要授权的操作'
})

const permissionActions = [
  { label: '允许一次', value: 'allow_once' },
  { label: '本会话允许', value: 'allow_conversation' },
  { label: '拒绝', value: 'deny' },
]

function handleSummaryToggle(event: Event) {
  expanded.value = Boolean((event.target as HTMLDetailsElement).open)
}

function resolvePermission(value: string, label: string) {
  const question = interruptQuestion.value
  if (!question || !props.interruptState?.resolve) return
  const payload = buildInterruptResumePayload(question, [value], '')
  if (!payload) return
  props.interruptState.resolve({
    ...payload,
    selectedValues: [value],
    selectedLabels: [label],
    answer: label,
  })
}

function resolveGenericInterrupt(payload: unknown) {
  props.interruptState?.resolve?.(payload)
}

function permissionTarget(question: InterruptQuestion | null) {
  if (!question) return ''
  const source = question as any
  const direct = String(source.tool_name || source.toolName || source.scriptName || source.skillName || '').trim()
  if (direct) return direct
  const match = String(question.question || '').match(/Tool:\s*([^\n]+)/i)
  return match?.[1]?.trim() || ''
}
</script>

<style scoped>
.run-process-shell {
  width: 100%;
  margin: 8px 0 4px;
}

.run-process-summary {
  border: 1px solid var(--cc-agent-line);
  border-radius: var(--cc-agent-card-radius);
  background: var(--cc-agent-surface);
}

.run-process-summary__row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 5px 9px;
  color: var(--cc-agent-muted);
  cursor: pointer;
  list-style: none;
}

.run-process-summary__row::-webkit-details-marker {
  display: none;
}

.run-process-summary__chevron {
  width: 7px;
  height: 7px;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: rotate(-45deg);
  transition: transform 160ms ease;
}

.run-process-summary[open] .run-process-summary__chevron {
  transform: rotate(45deg);
}

.run-process-summary__title {
  min-width: 0;
  flex: 1;
  font-size: 12px;
  line-height: 1.45;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-process-summary__status {
  flex: 0 0 auto;
  border: 1px solid var(--cc-agent-line);
  border-radius: var(--cc-agent-card-radius);
  padding: 1px 6px;
  background: var(--cc-agent-surface-alt);
  color: var(--cc-agent-primary);
  font-size: 11px;
  line-height: 1.4;
}

.run-process-content {
  display: grid;
  gap: 6px;
  margin-left: 8px;
  border-left: 2px solid var(--cc-agent-primary-border);
  padding: 10px 0 4px 16px;
}

.run-process-permission {
  display: grid;
  gap: 9px;
  border: 1px solid var(--cc-agent-line);
  border-radius: var(--cc-agent-card-radius);
  background: var(--cc-agent-surface);
  padding: 12px;
}

.run-process-permission__title {
  color: var(--cc-agent-text);
  font-size: 13px;
  font-weight: 700;
}

.run-process-permission p {
  margin: 0;
  color: var(--cc-agent-muted);
  font-size: 13px;
  line-height: 1.5;
}

.run-process-permission__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.run-process-permission__actions button {
  border: 1px solid var(--cc-agent-primary);

  border-radius: 8px;
  background: var(--cc-agent-primary);
  padding: 8px 11px;
  color: #ffffff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}

.run-process-permission__actions button.danger {
  border-color: var(--cc-agent-line);
  background: #ffffff;
  color: #b42318;
}

.run-process-interrupt {
  margin: 0;
}

.run-process-summary__row:focus-visible,
.run-process-permission__actions button:focus-visible {
  outline: 2px solid var(--cc-agent-focus);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .run-process-summary__chevron {
    transition: none;
  }
}

@media (max-width: 760px) {
  .run-process-shell {
    width: 100%;
  }
}
</style>
