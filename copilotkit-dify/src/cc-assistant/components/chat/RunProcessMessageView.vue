<template>
  <div class="run-process-message-view">
    <template v-for="group in groups" :key="group.id">
      <CopilotChatUserMessage
        v-for="message in group.userMessages"
        :key="message.id"
        :message="message as any"
      />

      <RunProcessBlock
        v-if="group.processMessages.length || group.hasActiveInterrupt"
        :mode="group.processDisplay"
        :summary="group.summary"
        :default-expanded="group.defaultExpanded"
        :interrupt-state="group.hasActiveInterrupt ? interruptState : null"
      >
        <CopilotChatMessageView
          :messages="[...group.processMessages, ...group.toolResultMessages]"
          :is-running="group.isRunning"
        >
          <template #assistant-message="slotProps">
            <GeneratedUiAssistantMessage
              :message="slotProps.message"
              :messages="slotProps.messages"
              :is-running="slotProps.isRunning"
              @intent="value => emit('uiIntent', value)"
            />
          </template>

          <template #reasoning-message="slotProps">
            <CopilotChatReasoningMessage
              :message="slotProps.message"
              :messages="slotProps.messages"
              :is-running="slotProps.isRunning"
            >
              <template #header="{ isOpen, hasContent, isStreaming, onClick }">
                <button
                  type="button"
                  class="run-process-reasoning-header"
                  :class="{ interactive: hasContent }"
                  :aria-expanded="hasContent ? isOpen : undefined"
                  @click="hasContent ? onClick?.() : undefined"
                >
                  <span>{{ group.isRunning || isStreaming ? '分析中' : '分析过程' }}</span>
                  <span v-if="(group.isRunning || isStreaming) && !hasContent" class="run-process-reasoning-pulse" aria-hidden="true" />
                  <span
                    v-if="hasContent"
                    class="run-process-reasoning-chevron"
                    :class="{ open: isOpen }"
                    aria-hidden="true"
                  />
                </button>
              </template>
            </CopilotChatReasoningMessage>
          </template>
        </CopilotChatMessageView>
      </RunProcessBlock>

      <GeneratedUiAssistantMessage
        v-for="message in group.finalAssistantMessages"
        :key="message.id"
        :message="message as any"
        :messages="messages"
        :is-running="isRunning"
        @intent="value => emit('uiIntent', value)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Message } from '@ag-ui/core'
import {
  CopilotChatMessageView,
  CopilotChatReasoningMessage,
  CopilotChatUserMessage,
} from '@copilotkit/vue/v2'
import GeneratedUiAssistantMessage from '../generated-ui/GeneratedUiAssistantMessage.vue'
import RunProcessBlock from './RunProcessBlock.vue'
import { buildRunProcessGroups, type RunProcessInterruptState } from '../../lib/runProcess'

const props = withDefaults(defineProps<{
  messages: Message[]
  isRunning?: boolean
  interruptState?: RunProcessInterruptState | null
}>(), {
  messages: () => [],
  isRunning: false,
  interruptState: null,
})

const emit = defineEmits<{
  uiIntent: [value: string]
}>()

const groupStartedAtById = ref<Record<string, number>>({})
const groupDurationMsById = ref<Record<string, number>>({})

const rawGroups = computed(() => buildRunProcessGroups(
  props.messages,
  props.isRunning,
  props.interruptState,
))

watch(
  rawGroups,
  (nextGroups) => {
    const now = Date.now()
    let nextStartedAtById = groupStartedAtById.value
    let nextDurationMsById = groupDurationMsById.value

    for (const group of nextGroups) {
      const hasProcess = group.processMessages.length > 0 || group.hasActiveInterrupt
      if (!hasProcess) continue

      if ((group.isRunning || group.processDisplay === 'expanded') && !nextStartedAtById[group.id]) {
        nextStartedAtById = {
          ...nextStartedAtById,
          [group.id]: now,
        }
      }

      if (group.isComplete && !nextDurationMsById[group.id]) {
        const startedAt = nextStartedAtById[group.id]
        if (startedAt) {
          nextDurationMsById = {
            ...nextDurationMsById,
            [group.id]: Math.max(1000, now - startedAt),
          }
        }
      }
    }

    if (nextStartedAtById !== groupStartedAtById.value) {
      groupStartedAtById.value = nextStartedAtById
    }
    if (nextDurationMsById !== groupDurationMsById.value) {
      groupDurationMsById.value = nextDurationMsById
    }
  },
  { immediate: true },
)

const groups = computed(() => buildRunProcessGroups(
  props.messages,
  props.isRunning,
  props.interruptState,
  {
    durationMsByGroupId: groupDurationMsById.value,
  },
))
</script>

<style scoped>
.run-process-message-view {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 100%;
  padding: 0 0 12px;
}

.run-process-message-view :deep([data-testid="copilot-assistant-message"]) {
  width: 100%;
  max-width: 100%;
}

.run-process-message-view :deep(.big-tool-card),
.run-process-message-view :deep(.tool-call-card),
.run-process-message-view :deep(.search-tool-card),
.run-process-message-view :deep(.activity-card),
.run-process-message-view :deep(.skill-activity-card),
.run-process-message-view :deep(.permission-activity-card),
.run-process-message-view :deep(.script-activity-card),
.run-process-message-view :deep(.uploaded-files-container),
.run-process-message-view :deep(.generated-file-container) {
  box-sizing: border-box;
  width: 100%;
  max-width: none;
}

.run-process-reasoning-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  padding: 4px 0;
  color: var(--cc-agent-muted);
  font: inherit;
  font-size: 14px;
  line-height: 1.4;
  font-weight: 500;
  cursor: default;
}

.run-process-reasoning-header.interactive {
  cursor: pointer;
}

.run-process-reasoning-header.interactive:hover {
  color: var(--cc-agent-primary-strong);
}

.run-process-reasoning-pulse {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
  animation: run-process-reasoning-pulse 1.2s ease-in-out infinite;
}

.run-process-reasoning-chevron {
  width: 8px;
  height: 8px;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: rotate(-45deg);
  transition: transform 160ms ease;
}

.run-process-reasoning-header.interactive:focus-visible {
  outline: 2px solid var(--cc-agent-focus);
  outline-offset: 3px;
  border-radius: 4px;
}

@media (prefers-reduced-motion: reduce) {
  .run-process-reasoning-pulse {
    animation: none;
  }

  .run-process-reasoning-chevron {
    transition: none;
  }
}

.run-process-reasoning-chevron.open {
  transform: rotate(45deg);
}

@keyframes run-process-reasoning-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.35;
  }
}
</style>
