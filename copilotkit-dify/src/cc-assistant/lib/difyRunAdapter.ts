import type { BaseEvent } from '@ag-ui/core'
import type { NormalizedDifyEvent } from './difyEventBridge'

interface DifyRunEmitterContext {
  runId: string
  threadId: string
}

interface EventObserver {
  next: (event: BaseEvent) => void
}

let messageSeq = 0
function nextMessageId(prefix: string) {
  return `${prefix}_${++messageSeq}_${Math.random().toString(36).slice(2, 8)}`
}

function interruptValueFromFinalState(event: Extract<NormalizedDifyEvent, { kind: 'final_state' }>) {
  const payload = event.payload || {}
  const metadata = payload.executionMetadata || payload.execution_metadata || {}
  const outcome = event.outcome || null

  if (!(outcome?.type === 'interrupt' || metadata.finishReason === 'awaiting_user' || metadata.finish_reason === 'awaiting_user')) {
    return null
  }

  if (outcome?.interrupts?.[0]) {
    const intr = outcome.interrupts[0]
    return {
      id: intr.id || intr.toolCallId || '',
      question: intr.message || intr.reason || '',
      purpose: intr.metadata?.purpose || 'clarification',
      options: intr.metadata?.options || [],
      fields: intr.metadata?.fields || [],
      allowCustomInput: intr.metadata?.allowCustomInput ?? true,
      multiSelect: intr.metadata?.multiSelect ?? false,
    }
  }

  const question = metadata.question || {}
  return {
    id: question.id || question.toolCallId || question.tool_call_id || '',
    question: question.question || question.text || '',
    purpose: question.purpose || 'clarification',
    options: question.options || [],
    fields: question.fields || [],
    allowCustomInput: question.allowCustomInput ?? true,
    multiSelect: question.multiSelect ?? false,
  }
}

function activityContentFromEvent(event: Extract<NormalizedDifyEvent, { kind: 'generic_activity' | 'skill_event' | 'guard_event' | 'compression_event' }>) {
  if (event.kind === 'generic_activity') return event.data || {}
  if (event.kind === 'skill_event') {
    return {
      toolName: event.toolName,
      toolCallId: event.toolCallId,
      skillName: event.skillName,
      text: event.text,
    }
  }
  if (event.kind === 'guard_event') {
    return {
      toolName: event.toolName,
      toolCallId: event.toolCallId,
      observation: event.observation,
    }
  }
  return {
    metadata: event.metadata,
  }
}

const INTERNAL_TOOL_NAMES = new Set(['UserPrompt', 'Skill'])

export function createDifyRunEmitter(observer: EventObserver, context: DifyRunEmitterContext) {
  let textMessageId = ''
  let reasoningMessageId = ''
  let textOpen = false
  let reasoningOpen = false
  let runFinished = false
  const seenToolCalls = new Set<string>()
  const internalToolCallIds = new Set<string>()

  const closeReasoning = () => {
    if (!reasoningOpen) return
    observer.next({ type: 'REASONING_MESSAGE_END', messageId: reasoningMessageId } as BaseEvent)
    reasoningOpen = false
  }

  const closeText = () => {
    if (!textOpen) return
    observer.next({ type: 'TEXT_MESSAGE_END', messageId: textMessageId } as BaseEvent)
    textOpen = false
  }

  return {
    emitRunStarted() {
      observer.next({ type: 'RUN_STARTED', threadId: context.threadId, runId: context.runId } as BaseEvent)
    },

    closeOpenMessages() {
      closeReasoning()
      closeText()
    },

    emitNormalized(event: NormalizedDifyEvent) {
      if (event.kind === 'error') return
      if (runFinished) return

      if (event.kind === 'thinking_delta') {
        if (!reasoningOpen) {
          reasoningOpen = true
          reasoningMessageId = nextMessageId('reasoning')
          observer.next({ type: 'REASONING_MESSAGE_START', messageId: reasoningMessageId, role: 'reasoning' } as BaseEvent)
        }
        observer.next({ type: 'REASONING_MESSAGE_CONTENT', messageId: reasoningMessageId, delta: String(event.text || '') } as BaseEvent)
        return
      }

      if (event.kind === 'text_delta') {
        closeReasoning()
        if (!textOpen) {
          textOpen = true
          textMessageId = nextMessageId('assistant')
          observer.next({ type: 'TEXT_MESSAGE_START', messageId: textMessageId, role: 'assistant' } as BaseEvent)
        }
        observer.next({ type: 'TEXT_MESSAGE_CONTENT', messageId: textMessageId, delta: String(event.text || '') } as BaseEvent)
        return
      }

      if (event.kind === 'tool_event') {
        const tcId = event.toolCallId || nextMessageId('toolcall')
        if (event.state === 'call' && INTERNAL_TOOL_NAMES.has(String(event.toolName || ''))) {
          internalToolCallIds.add(tcId)
          return
        }
        if (internalToolCallIds.has(tcId)) return

        closeReasoning()
        closeText()

        if (event.state === 'call' && !seenToolCalls.has(tcId)) {
          seenToolCalls.add(tcId)
          observer.next({ type: 'TOOL_CALL_START', toolCallId: tcId, toolCallName: event.toolName || 'unknown_tool' } as BaseEvent)
          if (event.input != null) {
            const args = typeof event.input === 'string' ? event.input : JSON.stringify(event.input)
            observer.next({ type: 'TOOL_CALL_ARGS', toolCallId: tcId, delta: args } as BaseEvent)
          }
          return
        }

        if (event.state === 'call') {
          if (event.input != null) {
            const args = typeof event.input === 'string' ? event.input : JSON.stringify(event.input)
            observer.next({ type: 'TOOL_CALL_ARGS', toolCallId: tcId, delta: args } as BaseEvent)
          }
          return
        }

        const content = event.observation ?? event.output ?? ''
        observer.next({ type: 'TOOL_CALL_RESULT', toolCallId: tcId, content: String(content), role: 'tool' } as BaseEvent)
        observer.next({ type: 'TOOL_CALL_END', toolCallId: tcId } as BaseEvent)
        return
      }

      if (event.kind === 'final_state') {
        closeReasoning()
        closeText()

        const interruptValue = interruptValueFromFinalState(event)
        if (interruptValue) {
          observer.next({
            type: 'CUSTOM',
            name: 'on_interrupt',
            value: interruptValue,
          } as BaseEvent)
        }

        observer.next({
          type: 'RUN_FINISHED',
          threadId: context.threadId,
          runId: context.runId,
          result: event.payload || {},
          ...(event.outcome ? { outcome: event.outcome } : {}),
        } as BaseEvent)
        runFinished = true
        return
      }

      if (event.kind === 'generic_activity' || event.kind === 'skill_event' || event.kind === 'guard_event' || event.kind === 'compression_event') {
        const activityType = event.kind === 'generic_activity'
          ? event.label || 'activity'
          : event.kind === 'skill_event'
            ? 'cc_agent.skill_apply'
            : 'cc_agent.' + event.kind.replace('_event', '')
        observer.next({
          type: 'ACTIVITY_SNAPSHOT',
          messageId: nextMessageId('activity'),
          activityType,
          content: activityContentFromEvent(event),
        } as BaseEvent)
      }
    },
  }
}
