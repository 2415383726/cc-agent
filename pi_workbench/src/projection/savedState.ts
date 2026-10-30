import { DisplayEvent, SCHEMA, terminalStatus } from '../contract/display'

const PREFIX = 'piagent-state:v1:gzip-base64:'
const MAX_PAYLOAD = 4 * 1024 * 1024

/** Only display facts are selected. Answers/approvals remain server-validated. */
export async function eventsFromSavedState(value: string, conversationId: string): Promise<DisplayEvent[]> {
  if (!value.startsWith(PREFIX) || value.length > 190_000 + PREFIX.length) throw new Error('无效的 Pi 状态')
  const bytes = Uint8Array.from(atob(value.slice(PREFIX.length)), (char) => char.charCodeAt(0))
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')).getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const { done, value: chunk } = await reader.read()
      if (done) break
      size += chunk.byteLength
      if (size > MAX_PAYLOAD) throw new Error('Pi 状态超过读取限制')
      chunks.push(chunk)
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
  const raw = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { raw.set(chunk, offset); offset += chunk.byteLength }
  const state = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw))
  if (state?.schema_version !== 1 || (state.session_id && state.session_id !== conversationId)) {
    throw new Error('Pi 状态不属于当前会话')
  }
  const events: DisplayEvent[] = []
  const emit = (type: string, fields: Record<string, unknown>) => events.push({
    schema: SCHEMA, schema_version: 1, run_id: `restored:${state.run_id}:${state.revision}`,
    seq: events.length, ts: Date.now(), type, ...fields,
  })
  const pending = state.pending
  if (pending?.kind === 'ask_user' && Array.isArray(pending.questionnaire?.questions)) {
    emit('question.asked', { questionnaire: {
      ...pending.questionnaire, pending_id: pending.id,
      created_at: pending.created_at, expires_at: pending.expires_at,
    } })
  } else if (pending?.kind === 'approval') {
    emit('approval.requested', { approval: {
      pending_id: pending.id, tool_call_id: pending.tool_call_id, tool: pending.tool_name,
      arguments: pending.arguments, source: pending.source,
      scope_options: pending.scope_options,
    } })
  }
  emit('run.state', {
    status: terminalStatus(state.last_status), answer: String(state.last_answer || ''),
    stats: state.stats, pending: undefined,
  })
  return events
}
