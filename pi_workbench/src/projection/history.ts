import { DisplayEvent, SCHEMA, findPiEvent, parseDisplayEvent } from '../contract/display'

export interface HistoryRecord {
  id?: string
  query?: string
  answer?: string
  created_at?: number
  message_files?: Array<Record<string, unknown>>
  agent_thoughts?: Array<Record<string, unknown>>
}

export interface HistoryProjection {
  events: DisplayEvent[]
  records: HistoryRecord[]
}

export function eventsFromHistory(records: HistoryRecord[]): HistoryProjection {
  const events: DisplayEvent[] = []
  const seen = new Set<string>()
  const push = (event: DisplayEvent | null) => {
    if (!event) return
    const key = `${event.run_id}:${event.seq}`
    if (seen.has(key)) return
    seen.add(key)
    events.push(event)
  }
  for (const record of Array.isArray(records) ? records : []) {
    const id = String(record.id || record.created_at || events.length)
    const collected: DisplayEvent[] = []
    for (const thought of record.agent_thoughts || []) {
      const found = findPiEvent(thought)
      if (found?.event) collected.push(found.event)
    }
    collected.sort((left, right) => left.seq - right.seq)
    const hasUserEvent = collected.some((event) => event.type === 'message.user')
    if (!hasUserEvent && record.query) {
      push(syntheticUser(id, record))
    }
    for (const event of collected) push(event)
    if (!collected.some((event) => event.type === 'run.state' || event.type === 'run.done')) {
      if (record.answer) {
        push(syntheticAssistant(id, record))
      }
    }
  }
  return { events, records: Array.isArray(records) ? records : [] }
}

export function findPiEventsInMessage(record: Record<string, unknown>): DisplayEvent[] {
  const events: DisplayEvent[] = []
  const visit = (value: unknown, depth: number) => {
    if (depth > 7 || value == null) return
    if (typeof value === 'string') {
      const text = value.trim()
      if (!text.startsWith('{') && !text.startsWith('[')) return
      try {
        visit(JSON.parse(text), depth + 1)
      } catch {
        /* ignore */
      }
      return
    }
    if (Array.isArray(value)) {
      for (const item of value) visit(item, depth + 1)
      return
    }
    if (typeof value !== 'object') return
    const item = value as Record<string, unknown>
    if (item.schema === SCHEMA) {
      const parsed = parseDisplayEvent(item)
      if (parsed.event) events.push(parsed.event)
      return
    }
    for (const key of Object.keys(item)) {
      visit(item[key], depth + 1)
    }
  }
  visit(record, 0)
  return events
}

function syntheticUser(id: string, record: HistoryRecord): DisplayEvent {
  return {
    schema: SCHEMA,
    schema_version: 1,
    type: 'message.user',
    run_id: `history:${id}`,
    seq: 0,
    ts: Number(record.created_at || 0),
    text: String(record.query || ''),
    files: Array.isArray(record.message_files) ? record.message_files : undefined,
    message_id: `history:${id}:user`,
  } as DisplayEvent
}

function syntheticAssistant(id: string, record: HistoryRecord): DisplayEvent {
  return {
    schema: SCHEMA,
    schema_version: 1,
    type: 'message.end',
    run_id: `history:${id}`,
    seq: 1,
    ts: Number(record.created_at || 0),
    text: String(record.answer || ''),
    message_id: `history:${id}:assistant`,
  } as DisplayEvent
}
