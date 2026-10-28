import { normalizeInterruptQuestion, type InterruptQuestion } from './question'
import { runStatusFromMetadata, type RunStatus } from './runStatus'

export interface ConversationRecovery {
  revision: number
  runId: string
  status: RunStatus
  question: InterruptQuestion | null
}

const PREFIX = 'ccagent-state:v1:gzip-base64:'
const MAX_STATE_BYTES = 1_000_000

/** Decode Dify's saved state into the small view needed to continue an interaction. */
export async function decodeConversationRecovery(value: unknown): Promise<ConversationRecovery> {
  if (typeof value !== 'string' || !value.startsWith(PREFIX) || value.length > 190_000) {
    throw new Error('Invalid conversation recovery state')
  }
  const bytes = Uint8Array.from(atob(value.slice(PREFIX.length)), char => char.charCodeAt(0))
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')).getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    for (;;) {
      const part = await reader.read()
      if (part.done) break
      size += part.value.byteLength
      if (size > MAX_STATE_BYTES) throw new Error('Conversation recovery state is too large')
      chunks.push(part.value)
    }
  } finally {
    await reader.cancel().catch(() => undefined)
  }
  const inflated = new Uint8Array(size)
  let offset = 0
  for (const part of chunks) { inflated.set(part, offset); offset += part.byteLength }
  const state = JSON.parse(new TextDecoder().decode(inflated))
  if (!state || typeof state !== 'object' || !Number.isInteger(state.revision)) {
    throw new Error('Invalid conversation recovery payload')
  }
  const metadata = state.last_execution_metadata || {}
  const waiting = metadata.finish_reason === 'awaiting_user'
  const question = waiting ? normalizeInterruptQuestion(metadata.question) : null
  if (waiting && (!question?.id || !question.question)) throw new Error('Incomplete pending interaction')
  return {
    revision: state.revision,
    runId: typeof metadata.run_id === 'string' ? metadata.run_id : '',
    status: runStatusFromMetadata(metadata),
    question,
  }
}
