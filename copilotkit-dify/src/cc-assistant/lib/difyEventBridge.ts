import { EventType, type AGUIEvent } from '@ag-ui/core'

export type NormalizedDifyEvent =
  | { kind: 'agui_run_started'; protocol?: string; runId?: string; threadId?: string; raw?: any }
  | { kind: 'text_delta'; protocol?: string; text: string; messageId?: string; raw?: any }
  | { kind: 'thinking_delta'; protocol?: string; text: string; messageId?: string; raw?: any }
  | { kind: 'tool_event'; protocol?: string; state: 'call' | 'result' | 'error'; toolName?: string; toolCallId?: string | null; input?: any; output?: any; error?: any; observation?: any; raw?: any }
  | { kind: 'skill_event'; protocol?: string; text?: string; toolName?: string; toolCallId?: string | null; skillName?: string | null; messageId?: string; raw?: any }
  | { kind: 'guard_event'; protocol?: string; toolName?: string; toolCallId?: string | null; observation?: any; messageId?: string; raw?: any }
  | { kind: 'compression_event'; protocol?: string; metadata?: any; messageId?: string; raw?: any }
  | { kind: 'generic_activity'; protocol?: string; label?: string; data?: any; messageId?: string; raw?: any }
  | { kind: 'final_state'; protocol?: string; payload: any; outcome?: any; raw?: any }
  | { kind: 'error'; protocol?: string; message: string; raw?: any }

function parseMaybeJson(value: unknown): any {
  if (value == null) return null
  if (typeof value === 'object') return value
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  try {
    return JSON.parse(trimmed)
  } catch (_) {
    return null
  }
}

function get(obj: Record<string, any> | null | undefined, ...keys: string[]) {
  for (const key of keys) {
    if (obj && Object.prototype.hasOwnProperty.call(obj, key) && obj[key] != null) return obj[key]
  }
  return undefined
}

const AGUI_EVENT_TYPES = new Set(Object.values(EventType))

export function isAgUiEvent(value: any): value is AGUIEvent {
  return Boolean(value && typeof value === 'object' && AGUI_EVENT_TYPES.has(String(value.type || '') as EventType))
}

function pickPayload(event: Record<string, any>) {
  const candidates = [
    event?.data,
    event?.metadata?.data,
    event?.metadata?.raw,
    event?.observation,
    event?.thought,
    event?.message,
  ]

  for (const candidate of candidates) {
    const payload = parseMaybeJson(candidate) || candidate
    if (payload && typeof payload === 'object') return payload
  }
  return null
}

function unwrapAgentLogPayload(payload: any) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return payload
  const inner = parseMaybeJson((payload as Record<string, any>).data) ?? (payload as Record<string, any>).data
  return inner ?? payload
}

export function extractAgUiEvent(event: Record<string, any>): AGUIEvent | null {
  if (isAgUiEvent(event)) return event
  if (!event || typeof event !== 'object') return null
  if (event.event !== 'agent_thought' && event.event !== 'agent_log') return null
  let payload = pickPayload(event)
  if (isAgUiEvent(payload)) return payload
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    const inner = unwrapAgentLogPayload(payload)
    if (isAgUiEvent(inner)) return inner
  }
  return null
}

function findFinalPayload(value: any, depth = 0): any {
  if (!value || depth > 5) return null
  const parsed = parseMaybeJson(value) || value
  if (!parsed || typeof parsed !== 'object') return null

  if (parsed.event === 'agent_finished' || parsed.event === 'agent_failed') return parsed

  for (const key of ['metadata', 'outputs', 'output', 'data', 'json', 'json_object', 'payload', 'result']) {
    const found = findFinalPayload(parsed[key], depth + 1)
    if (found) return found
  }

  if (Array.isArray(parsed)) {
    for (const item of parsed) {
      const found = findFinalPayload(item, depth + 1)
      if (found) return found
    }
  }
  return null
}

function toolNameOf(data: Record<string, any>) {
  return String(get(data, 'tool_name', 'toolName', 'name') || 'unknown_tool')
}

function toolCallIdOf(data: Record<string, any>) {
  return get(data, 'tool_call_id', 'toolCallId', 'id') || null
}

function toolInputOf(data: Record<string, any>) {
  return get(data, 'arguments', 'input', 'tool_input', 'parameters') ?? null
}

function normalizeAgUiEvent(event: Record<string, any>): NormalizedDifyEvent[] {
  const type = String(event.type || '')
  if (type === EventType.RUN_STARTED) {
    return [{ kind: 'agui_run_started', protocol: 'ag-ui', runId: event.runId, threadId: event.threadId, raw: event }]
  }
  if (type === EventType.TEXT_MESSAGE_CONTENT || type === EventType.TEXT_MESSAGE_CHUNK) {
    const text = String(get(event, 'delta') || '')
    return text ? [{ kind: 'text_delta', protocol: 'ag-ui', text, messageId: event.messageId, raw: event }] : []
  }
  if (type === EventType.REASONING_MESSAGE_CONTENT || type === EventType.REASONING_MESSAGE_CHUNK) {
    const text = String(get(event, 'delta') || '')
    return text ? [{ kind: 'thinking_delta', protocol: 'ag-ui', text, messageId: event.messageId, raw: event }] : []
  }
  if (type === EventType.TOOL_CALL_START) {
    return [{
      kind: 'tool_event',
      protocol: 'ag-ui',
      state: 'call',
      toolName: String(event.toolCallName || 'unknown_tool'),
      toolCallId: event.toolCallId || null,
      input: null,
      output: null,
      error: null,
      observation: null,
      raw: event,
    }]
  }
  if (type === EventType.TOOL_CALL_ARGS) {
    return [{
      kind: 'tool_event',
      protocol: 'ag-ui',
      state: 'call',
      toolName: 'unknown_tool',
      toolCallId: event.toolCallId || null,
      input: parseMaybeJson(event.delta) ?? event.delta,
      output: undefined,
      error: undefined,
      observation: undefined,
      raw: event,
    }]
  }
  if (type === EventType.TOOL_CALL_RESULT) {
    const content = get(event, 'content')
    const parsed = parseMaybeJson(content)
    const observation = typeof content === 'string' ? content : (content == null ? '' : JSON.stringify(content))
    return [{
      kind: 'tool_event',
      protocol: 'ag-ui',
      state: 'result',
      toolName: get(event, 'toolCallName', 'toolName') || 'unknown_tool',
      toolCallId: get(event, 'toolCallId', 'tool_call_id') || null,
      input: undefined,
      output: parsed ?? (observation ? { value: observation } : undefined),
      error: null,
      observation: observation || undefined,
      raw: event,
    }]
  }
  if (type === EventType.ACTIVITY_SNAPSHOT) {
    const content = event.content && typeof event.content === 'object' && !Array.isArray(event.content) ? event.content : {}
    if (event.activityType === 'cc_agent.skill_apply') {
      return [{
        kind: 'skill_event',
        protocol: 'ag-ui',
        text: String(content.text || ''),
        toolName: String(content.toolName || 'Skill'),
        toolCallId: content.toolCallId || null,
        skillName: content.skillName || null,
        messageId: event.messageId,
        raw: event,
      }]
    }
    if (event.activityType === 'cc_agent.guard_triggered') {
      return [{
        kind: 'guard_event',
        protocol: 'ag-ui',
        toolName: String(content.toolName || 'unknown_tool'),
        toolCallId: content.toolCallId || null,
        observation: content.observation || content.message || content.summary || '',
        messageId: event.messageId,
        raw: event,
      }]
    }
    if (event.activityType === 'cc_agent.compression') {
      return [{
        kind: 'compression_event',
        protocol: 'ag-ui',
        metadata: content,
        messageId: event.messageId,
        raw: event,
      }]
    }
    return [{
      kind: 'generic_activity',
      protocol: 'ag-ui',
      label: event.activityType || 'ACTIVITY_SNAPSHOT',
      data: content,
      messageId: event.messageId,
      raw: event,
    }]
  }
  if (type === EventType.CUSTOM && event.name === 'cc_agent.ui_card') {
    const value = event.value || {}
    return [{
      kind: 'tool_event',
      protocol: 'ag-ui',
      state: 'result',
      toolName: String(value.toolName || 'unknown_tool'),
      toolCallId: value.toolCallId || value.id || null,
      input: value.input ?? null,
      output: value.output ?? null,
      error: value.error ?? null,
      observation: value.observation ?? null,
      raw: event,
    }]
  }
  if (type === EventType.RUN_FINISHED) {
    return [{
      kind: 'final_state',
      protocol: 'ag-ui',
      payload: event.result || { event: 'agent_finished' },
      outcome: event.outcome,
      raw: event,
    }]
  }
  if (type === EventType.RUN_ERROR) {
    return [{ kind: 'error', protocol: 'ag-ui', message: String(event.message || event.code || 'AG-UI run error'), raw: event }]
  }
  return []
}

function normalizeLogPayload(data: Record<string, any>, raw: Record<string, any>): NormalizedDifyEvent[] {
  if (isAgUiEvent(data)) return normalizeAgUiEvent(data)
  const type = String(data?.type || data?.event || '').trim()
  const finalPayload = findFinalPayload(data)
  if (finalPayload) return [{ kind: 'final_state', payload: finalPayload, raw }]

  if (type === 'thinking_delta') {
    return [{ kind: 'thinking_delta', text: String(get(data, 'text', 'delta', 'content', 'thought') || ''), raw }]
  }
  if (type === 'tool_call' || type === 'tool_start') {
    return [{
      kind: 'tool_event',
      state: 'call',
      toolName: toolNameOf(data),
      toolCallId: toolCallIdOf(data),
      input: toolInputOf(data),
      output: null,
      error: null,
      observation: get(data, 'observation') ?? null,
      raw,
    }]
  }
  if (type === 'tool_end') {
    const observation = get(data, 'observation', 'output', 'result')
    return [{
      kind: 'tool_event',
      state: 'result',
      toolName: toolNameOf(data),
      toolCallId: toolCallIdOf(data),
      input: toolInputOf(data),
      output: get(data, 'output', 'result') ?? (observation ? { value: observation } : null),
      error: null,
      observation: observation ?? null,
      raw,
    }]
  }
  if (type === 'tool_error') {
    const message = String(get(data, 'error', 'observation', 'message') || 'tool call failed')
    return [{
      kind: 'tool_event',
      state: 'error',
      toolName: toolNameOf(data),
      toolCallId: toolCallIdOf(data),
      input: toolInputOf(data),
      output: null,
      error: typeof data.error === 'object' ? data.error : { message },
      observation: get(data, 'observation') ?? message,
      raw,
    }]
  }
  return [{ kind: 'generic_activity', label: raw?.label || raw?.event || type || 'activity', data, raw }]
}

export function normalizeDifyEvent(event: Record<string, any>): NormalizedDifyEvent[] {
  if (!event || typeof event !== 'object') return []
  if (isAgUiEvent(event)) return normalizeAgUiEvent(event)
  if ((event.event === 'message' || event.event === 'agent_message') && event.answer) {
    return [{ kind: 'text_delta', text: String(event.answer), raw: event }]
  }
  if (event.event === 'message' || event.event === 'agent_message') return []

  // agent_log must be handled BEFORE findFinalPayload so that RUN_FINISHED
  // events go through normalizeAgUiEvent which preserves the outcome field.
  if (event.event === 'agent_thought' || event.event === 'agent_log') {
    let payload = pickPayload(event)
    if (!isAgUiEvent(payload) && payload && typeof payload === 'object' && !Array.isArray(payload)) {
      // Dify Workflow SSE wraps the real AG-UI event inside an extra data.data layer.
      const inner = unwrapAgentLogPayload(payload)
      if (isAgUiEvent(inner)) {
        payload = inner
      }
    }
    if (isAgUiEvent(payload)) return normalizeAgUiEvent(payload)
    if (payload) return normalizeLogPayload(payload, event)
  }

  const finalPayload = findFinalPayload(event)
  if (finalPayload) return [{ kind: 'final_state', payload: finalPayload, raw: event }]

  if (event.event === 'error') {
    return [{ kind: 'error', message: String(event.message || event.code || 'SSE error'), raw: event }]
  }

  return []
}
