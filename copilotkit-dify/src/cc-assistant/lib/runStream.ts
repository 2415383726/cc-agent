import type { BaseEvent } from '@ag-ui/core'
import { extractAgUiEvent, normalizeDifyEvent, type NormalizedDifyEvent } from './difyEventBridge'
import { createDifyBlobAccumulator, isDifyBlobEvent } from './difyBlob'
import type { InterruptQuestion } from './question'
import { runStatusFromMetadata, type RunStatus } from './runStatus'

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

function interruptFromResult(payload: any = {}, outcome: any = null): InterruptQuestion | null {
  outcome = outcome || payload.outcome || null
  const metadata = payload.executionMetadata || payload.execution_metadata || {}

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

function createDifyRunEmitter(observer: EventObserver, context: DifyRunEmitterContext) {
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


export interface RunStreamContext extends DifyRunEmitterContext {
  uploadedFiles?: BaseEvent
  onConversationId?: (id: string) => void
  onTaskId?: (id: string) => void
  onInterrupt?: (question: InterruptQuestion | null) => void
  onRunStatus?: (status: RunStatus, identity: { runId: string }) => void
}

/** Interpret one complete Dify stream, retaining native events and real fallback behavior. */
export function createRunStream(observer: EventObserver, context: RunStreamContext) {
  let started = false
  let nativeSeen = false
  let uploaded = false
  let terminal = false
  let finished = false
  let activeRunId = context.runId
  const pending: BaseEvent[] = []
  const blobs = createDifyBlobAccumulator()
  const emitUploaded = () => {
    if (uploaded || !context.uploadedFiles) return
    uploaded = true
    observer.next(context.uploadedFiles)
  }
  const emit = (event: BaseEvent) => {
    if (!started && event.type !== 'RUN_STARTED') {
      pending.push(event)
      return
    }
    if (event.type === 'RUN_FINISHED' || event.type === 'RUN_ERROR') {
      terminal = true
      const final = event as any
      const payload = final.result || {}
      const ref = payload.state_ref || payload.stateRef || {}
      const conversationId = String(ref.conversation_id || ref.conversationId || '').trim()
      if (conversationId) context.onConversationId?.(conversationId)
      const question = event.type === 'RUN_FINISHED' ? interruptFromResult(payload, final.outcome) : null
      context.onInterrupt?.(question)
      if (question) observer.next({ type: 'CUSTOM', name: 'on_interrupt', value: question } as BaseEvent)
      const metadata = payload.execution_metadata || payload.executionMetadata || {}
      context.onRunStatus?.(event.type === 'RUN_ERROR' ? 'failed' : question ? 'awaiting_user' :
        runStatusFromMetadata(metadata), { runId: String(final.runId || metadata.run_id || activeRunId) })
    }
    observer.next(event)
    if (event.type === 'RUN_STARTED') {
      activeRunId = String((event as any).runId || context.runId)
      terminal = false
      started = true
      emitUploaded()
      for (const queued of pending.splice(0)) emit(queued)
    }
  }
  const fallback = createDifyRunEmitter({ next: emit }, context)
  const ensureStarted = () => { if (!started) fallback.emitRunStarted() }
  return {
    ingest(raw: Record<string, any>) {
      if (raw?.task_id) context.onTaskId?.(String(raw.task_id))
      if (raw?.conversation_id) context.onConversationId?.(String(raw.conversation_id))
      const blob = blobs.ingest(raw)
      if (isDifyBlobEvent(raw)) {
        if (blob) {
          emit({ type: 'ACTIVITY_SNAPSHOT', messageId: blob.messageId,
            activityType: blob.activityType, content: blob.content } as BaseEvent)
        }
        return
      }
      const native = extractAgUiEvent(raw)
      if (native) {
        if (!nativeSeen) {
          fallback.closeOpenMessages()
          if (started && native.type === 'RUN_STARTED') {
            // Finish a live fallback segment before starting the native run.
            // The SDK rejects a second RUN_STARTED while the first is active.
            fallback.emitNormalized({ kind: 'final_state', payload: {} })
          }
        }
        nativeSeen = true
        if (!started && native.type !== 'RUN_STARTED') ensureStarted()
        emit(native as BaseEvent)
        return
      }
      if (nativeSeen && raw?.event !== 'error') return
      const normalized = normalizeDifyEvent(raw)
      if (!normalized.length) return
      for (const event of normalized) {
        if (!['generic_activity', 'skill_event', 'guard_event', 'compression_event'].includes(event.kind)) ensureStarted()
        if (event.kind === 'error') throw new Error(event.message || 'Dify event error')
        fallback.emitNormalized(event)
      }
    },
    finish() {
      if (finished) return
      finished = true
      if (pending.length) ensureStarted()
      fallback.closeOpenMessages()
      if (!terminal) context.onRunStatus?.('unknown', { runId: activeRunId })
    },
  }
}
