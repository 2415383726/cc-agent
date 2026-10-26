import type { Message, ToolCall } from '@ag-ui/core'

export type NormalizedEvent = Record<string, any>

export interface PendingInterruptQuestion {
  id: string
  question: string
  purpose: string
  options: Array<{ label: string; value: string; description?: string }>
  fields: Record<string, unknown>[]
  allowCustomInput: boolean
  multiSelect: boolean
}

export interface AgentMessageState {
  messages: Message[]
  finishReason: string
  finalPayload: Record<string, any> | null
  pendingInterrupt: PendingInterruptQuestion | null
  messageIndexById: Record<string, number>
}

function nextMessageId(prefix: string) {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}:${crypto.randomUUID()}`
  }
  return `${prefix}:${Math.random().toString(36).slice(2, 10)}`
}

function cloneState(state: AgentMessageState): AgentMessageState {
  return {
    ...state,
    messages: state.messages.slice(),
    messageIndexById: { ...state.messageIndexById },
  }
}

function stringifyContent(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch (_) {
    return String(value)
  }
}

function upsertMessage(state: AgentMessageState, id: string, factory: () => Message, updater?: (message: Message) => Message) {
  const next = cloneState(state)
  const index = next.messageIndexById[id]
  if (typeof index === 'number') {
    const current = next.messages[index]
    next.messages[index] = updater ? updater(current) : current
    return next
  }

  const created = factory()
  next.messageIndexById[id] = next.messages.length
  next.messages.push(updater ? updater(created) : created)
  return next
}

function assistantTextId(sourceId?: string | null) {
  return `assistant:${sourceId || 'default'}`
}

function reasoningId(sourceId?: string | null) {
  return `reasoning:${sourceId || 'default'}`
}

function toolCallMessageId(toolCallId?: string | null) {
  return `toolcall:${toolCallId || 'unknown'}`
}

function toolResultMessageId(toolCallId?: string | null) {
  return `tool:${toolCallId || 'unknown'}`
}

function activityMessageId(label?: string | null, sourceId?: string | null) {
  return `activity:${sourceId || label || nextMessageId('activity')}`
}

function normalizeToolCall(event: Record<string, any>, existing?: ToolCall): ToolCall {
  const args =
    event.input == null
      ? existing?.function.arguments || ''
      : typeof event.input === 'string'
        ? event.input
        : stringifyContent(event.input)
  const eventToolName = String(event.toolName || '')
  const toolName = eventToolName && eventToolName !== 'unknown_tool'
    ? eventToolName
    : existing?.function.name || 'unknown_tool'

  return {
    id: event.toolCallId || existing?.id || nextMessageId('tool-call'),
    type: 'function',
    function: {
      name: toolName,
      arguments: args,
    },
  }
}

function extractPendingInterrupt(event: Record<string, any>) {
  const metadata = event?.payload?.execution_metadata
  if (!metadata || metadata.finish_reason !== 'awaiting_user') return null

  const source = metadata.question || {}
  const interrupt = event?.outcome?.interrupts?.[0] || {}
  const interruptMetadata = interrupt.metadata || {}
  const options = Array.isArray(source.options)
    ? source.options
        .map((option: any) => {
          if (typeof option === 'string') {
            return { label: option, value: option, description: '' }
          }
          const label = String(option?.label || option?.text || option?.value || '')
          if (!label) return null
          return {
            label,
            value: String(option?.value || label),
            description: String(option?.description || ''),
          }
        })
        .filter(Boolean)
    : []

  return {
    id: String(source.id || source.tool_call_id || interrupt.id || interrupt.toolCallId || ''),
    question: String(source.question || source.text || interrupt.message || ''),
    purpose: String(source.purpose || 'clarification'),
    options,
    fields: Array.isArray(source.fields)
      ? source.fields
      : Array.isArray(interruptMetadata.fields)
        ? interruptMetadata.fields
        : [],
    allowCustomInput:
      'allowCustomInput' in source ? Boolean(source.allowCustomInput) : options.length === 0,
    multiSelect: Boolean(source.multiSelect),
  }
}

export function createEmptyAgentState(): AgentMessageState {
  return {
    messages: [],
    finishReason: '',
    finalPayload: null,
    pendingInterrupt: null,
    messageIndexById: {},
  }
}

export function reduceNormalizedEvent(state: AgentMessageState, event: NormalizedEvent): AgentMessageState {
  if (!event || typeof event !== 'object') return state

  if (event.kind === 'thinking_delta') {
    return upsertMessage(
      state,
      reasoningId(event.messageId),
      () => ({
        id: reasoningId(event.messageId),
        role: 'reasoning',
        content: '',
      } as Message),
      (message) => ({
        ...message,
        content: `${message.content || ''}${String(event.text || '')}`,
      } as Message),
    )
  }

  if (event.kind === 'text_delta') {
    return upsertMessage(
      state,
      assistantTextId(event.messageId),
      () => ({
        id: assistantTextId(event.messageId),
        role: 'assistant',
        content: '',
      } as Message),
      (message) => ({
        ...message,
        content: `${message.content || ''}${String(event.text || '')}`,
      } as Message),
    )
  }

  if (event.kind === 'tool_event') {
    if (event.state === 'call') {
      return upsertMessage(
        state,
        toolCallMessageId(event.toolCallId),
        () => ({
          id: toolCallMessageId(event.toolCallId),
          role: 'assistant',
          content: '',
          toolCalls: [normalizeToolCall(event)],
        } as Message),
        (message) => {
          const existing = (message as any).toolCalls?.[0]
          return {
            ...message,
            toolCalls: [normalizeToolCall(event, existing)],
          } as Message
        },
      )
    }

    const content = String(event.observation || event.error?.message || stringifyContent(event.output))
    return upsertMessage(
      state,
      toolResultMessageId(event.toolCallId),
      () => ({
        id: toolResultMessageId(event.toolCallId),
        role: 'tool',
        toolCallId: event.toolCallId || '',
        content,
      } as Message),
      (message) => ({
        ...message,
        toolCallId: event.toolCallId || (message as any).toolCallId || '',
        content,
      } as Message),
    )
  }

  if (event.kind === 'generic_activity' || event.kind === 'skill_event' || event.kind === 'guard_event' || event.kind === 'compression_event') {
    const activityType =
      event.kind === 'generic_activity'
        ? String(event.label || 'activity')
        : event.kind === 'skill_event'
          ? 'cc_agent.skill_apply'
          : event.kind === 'guard_event'
            ? 'cc_agent.guard_triggered'
            : 'cc_agent.compression'

    const content =
      event.kind === 'generic_activity'
        ? event.data
        : event.kind === 'skill_event'
          ? {
              skillName: event.skillName,
              text: event.text,
              toolName: event.toolName,
              toolCallId: event.toolCallId,
            }
          : event.kind === 'guard_event'
            ? {
                toolName: event.toolName,
                toolCallId: event.toolCallId,
                observation: event.observation,
              }
            : event.metadata

    return upsertMessage(
      state,
      activityMessageId(activityType, event.messageId),
      () => ({
        id: activityMessageId(activityType, event.messageId),
        role: 'activity',
        activityType,
        content,
      } as Message),
      () => ({
        id: activityMessageId(activityType, event.messageId),
        role: 'activity',
        activityType,
        content,
      } as Message),
    )
  }

  if (event.kind === 'final_state') {
    const next = cloneState(state)
    next.finalPayload = event.payload || null
    next.finishReason = String(event?.payload?.execution_metadata?.finish_reason || '')
    next.pendingInterrupt = extractPendingInterrupt(event)
    return next
  }

  return state
}
