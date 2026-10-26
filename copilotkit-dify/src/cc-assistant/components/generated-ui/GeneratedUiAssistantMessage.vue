<template>
  <CopilotChatAssistantMessage
    v-if="!contentParts.length"
    :message="message as any"
    :messages="messages"
    :is-running="isRunning"
  />

  <div v-else class="generated-ui-assistant-message" data-testid="generated-ui-assistant-message">
    <template v-for="(part, index) in contentParts" :key="partKey(part, index)">
      <CopilotChatAssistantMessage
        v-if="part.type === 'markdown'"
        v-memo="[part.content, isRunning]"
        :message="buildFragmentMessage(index, part.content) as any"
        :messages="messages"
        :is-running="isRunning"
      />
      <RecordSurface v-else-if="part.type === 'record'" v-memo="[part.spec, isRunning]" :spec="part.spec" :is-running="isRunning" @intent="emit('intent', $event)" />
      <TableSurface v-else-if="part.type === 'table'" v-memo="[part.spec, isRunning]" :spec="part.spec" :is-running="isRunning" @intent="emit('intent', $event)" />
      <CompareSurface v-else-if="part.type === 'compare'" v-memo="[part.spec, isRunning]" :spec="part.spec" :is-running="isRunning" @intent="emit('intent', $event)" />
      <TimelineSurface v-else-if="part.type === 'timeline'" v-memo="[part.spec, isRunning]" :spec="part.spec" :is-running="isRunning" @intent="emit('intent', $event)" />
      <BusinessSurfacePending v-else-if="part.type === 'surface-pending'" :surface="part.surface" />
      <AnswerChartSkeleton v-else-if="part.type === 'chart-pending'" />
      <LazyBlock v-else-if="part.type === 'chart'" :min-height="suggestedMinHeight(part)" root-margin="1200px 0px">
        <AnswerChart
          :spec="part.spec"
          :is-running="isRunning"
        />
      </LazyBlock>
      <CcMermaidBlock
        v-else
        :code="part.code"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, shallowRef, watch } from 'vue'
import type { AssistantMessage, Message } from '@ag-ui/core'
import { CopilotChatAssistantMessage } from '@copilotkit/vue/v2'
import AnswerChart from './AnswerChart.vue'
import AnswerChartSkeleton from './AnswerChartSkeleton.vue'
import CcMermaidBlock from './CcMermaidBlock.vue'
import RecordSurface from './RecordSurface.vue'
import TableSurface from './TableSurface.vue'
import CompareSurface from './CompareSurface.vue'
import TimelineSurface from './TimelineSurface.vue'
import BusinessSurfacePending from './BusinessSurfacePending.vue'
import LazyBlock from './LazyBlock.vue'
import { parseStructuredContentParts, type StructuredContentPart } from '../../lib/structuredContent'

const props = withDefaults(defineProps<{
  message: AssistantMessage
  messages?: Message[]
  isRunning?: boolean
}>(), {
  messages: () => [],
  isRunning: false,
})

const emit = defineEmits<{
  intent: [value: string]
}>()

const contentParts = shallowRef(parseStructuredContentParts(props.message.content))
let parseFrame: number | null = null

function parseLatestContent() {
  contentParts.value = parseStructuredContentParts(props.message.content)
}

function cancelScheduledParse() {
  if (parseFrame === null || typeof cancelAnimationFrame === 'undefined') return
  cancelAnimationFrame(parseFrame)
  parseFrame = null
}

function containsStructuredMarker(content: unknown) {
  return typeof content === 'string'
    && /```[ \t]*(?:cc-record|cc-table|cc-compare|cc-timeline|cc-chart|mermaid)(?:[ \t]*\r?\n|[ \t]*$)/i.test(content)
}

watch(
  () => [props.message.content, props.isRunning] as const,
  ([nextContent], previous) => {
    if (!props.isRunning || typeof requestAnimationFrame === 'undefined') {
      cancelScheduledParse()
      parseLatestContent()
      return
    }

    if (!contentParts.value.length && !containsStructuredMarker(props.message.content)) return
    const lastPart = contentParts.value[contentParts.value.length - 1]
    const previousContent = previous?.[0]
    if (
      lastPart?.type === 'surface-pending'
      && isAppendWithoutFenceClosure(nextContent, previousContent)
    ) return
    if (parseFrame !== null) return
    parseFrame = requestAnimationFrame(() => {
      parseFrame = null
      parseLatestContent()
    })
  },
  { flush: 'sync' },
)

function isAppendWithoutFenceClosure(nextContent: unknown, previousContent: unknown) {
  if (typeof nextContent !== 'string' || typeof previousContent !== 'string') return false
  if (!nextContent.startsWith(previousContent)) return false
  const changedTail = nextContent.slice(Math.max(0, previousContent.length - 2))
  return !changedTail.includes('```')
}

onBeforeUnmount(cancelScheduledParse)

function buildFragmentMessage(index: number, content: string): AssistantMessage {
  const message = {
    ...props.message,
    id: `${props.message.id}:structured-markdown-${index}`,
    content,
  } as AssistantMessage
  delete (message as any).toolCalls
  return message
}

function partKey(part: StructuredContentPart, index: number): string {
  if (part.type === 'markdown') return `markdown:${index}`
  if (part.type === 'record' || part.type === 'table' || part.type === 'compare' || part.type === 'timeline') return `${part.type}:${index}:${part.spec.meta.title}`
  if (part.type === 'chart') return `chart:${index}:${part.spec.chartType}:${part.spec.meta.title}`
  if (part.type === 'chart-pending') return `chart-pending:${index}`
  if (part.type === 'surface-pending') return `${part.surface}-pending:${index}`
  return `mermaid:${index}`
}

function suggestedMinHeight(part: StructuredContentPart): number {
  if (part.type !== 'chart') return 200
  const spec = part.spec
  if (spec.chartType === 'bar' && spec.orientation === 'horizontal') return Math.max(320, spec.data.length * 54 + 80)
  if (spec.chartType === 'pie' || spec.chartType === 'radar') return 390
  return 360
}
</script>

<style scoped>
.generated-ui-assistant-message {
  display: flex;
  flex-direction: column;
}
</style>
