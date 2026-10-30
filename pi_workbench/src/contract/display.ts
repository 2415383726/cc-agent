export const SCHEMA = 'piagent.display.v1'
export const SCHEMA_VERSION = 1

export const TERMINAL_STATUSES = new Set([
  'completed',
  'awaiting_user',
  'awaiting_approval',
  'failed',
  'stopped',
  'budget_exhausted',
  'context_overflow',
  'context_too_large',
  'state_save_failed',
  'cancelled',
  'unknown',
])

export interface DisplayEvent {
  schema: typeof SCHEMA
  schema_version: number
  type: string
  run_id: string
  seq: number
  ts: number
  [key: string]: unknown
}

export interface EventParseResult {
  event: DisplayEvent | null
  problem?: 'not-an-object' | 'unsupported-version' | 'malformed'
}

export function parseDisplayEvent(value: unknown): EventParseResult {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return { event: null, problem: 'not-an-object' }
  }
  const candidate = value as Record<string, unknown>
  if (candidate.schema !== SCHEMA) return { event: null, problem: 'malformed' }
  if (candidate.schema_version !== SCHEMA_VERSION) {
    return { event: null, problem: 'unsupported-version' }
  }
  if (
    typeof candidate.type !== 'string' ||
    typeof candidate.run_id !== 'string' ||
    typeof candidate.seq !== 'number' ||
    !Number.isFinite(candidate.seq)
  ) {
    return { event: null, problem: 'malformed' }
  }
  return {
    event: {
      ...candidate,
      type: candidate.type,
      run_id: candidate.run_id,
      seq: candidate.seq,
      ts: typeof candidate.ts === 'number' ? candidate.ts : 0,
    } as DisplayEvent,
  }
}

/** Find a Pi display event inside a Dify log payload, wherever the SDK nested it. */
export function findPiEvent(value: unknown, depth = 0): EventParseResult | null {
  if (depth > 6 || value == null) return null
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text.startsWith('{') && !text.startsWith('[')) return null
    try {
      return findPiEvent(JSON.parse(text), depth + 1)
    } catch {
      return null
    }
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findPiEvent(item, depth + 1)
      if (found) return found
    }
    return null
  }
  if (typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  if (record.schema === SCHEMA) return parseDisplayEvent(record)
  if (typeof record.schema === 'string' && record.schema.startsWith('piagent.display.')) {
    return { event: null, problem: 'unsupported-version' }
  }
  for (const key of ['piagent', 'data', 'log', 'message', 'result', 'payload']) {
    if (key in record) {
      const found = findPiEvent(record[key], depth + 1)
      if (found) return found
    }
  }
  return null
}

export function normalizeAnswer(value: string): string {
  return String(value || '').replace(/\r\n/g, '\n').trim()
}

export function sameAnswer(left: string, right: string): boolean {
  return normalizeAnswer(left) === normalizeAnswer(right)
}

export function terminalStatus(value: unknown): string {
  const status = String(value || '')
  return TERMINAL_STATUSES.has(status) ? status : 'unknown'
}
