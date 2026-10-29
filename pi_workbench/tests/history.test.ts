import { describe, expect, it } from 'vitest'
import { SCHEMA } from '../src/contract/display'
import { eventsFromHistory } from '../src/projection/history'

function event(type: string, fields: Record<string, unknown> = {}) {
  return {
    schema: SCHEMA,
    schema_version: 1,
    type,
    run_id: 'run_h',
    seq: 0,
    ts: 0,
    ...fields,
  }
}

describe('history reconstruction', () => {
  it('finds nested Pi events and preserves record order', () => {
    const result = eventsFromHistory([
      {
        id: 'm1',
        query: 'first',
        answer: 'answer one',
        agent_thoughts: [
          { data: { piagent: event('message.user', { text: 'first' }) } },
          { data: { data: JSON.stringify({ piagent: event('message.end', { text: 'answer one' }) }) } },
        ],
      },
      {
        id: 'm2',
        query: 'second',
        answer: 'answer two',
        agent_thoughts: [],
      },
    ])
    expect(result.events.map((item) => item.type)).toEqual([
      'message.user',
      'message.end',
      'message.user',
      'message.end',
    ])
    expect(result.events[3].text).toBe('answer two')
  })

  it('falls back to query/answer when no Pi events were stored', () => {
    const result = eventsFromHistory([{ id: 'm1', query: 'hello', answer: 'hi' }])
    expect(result.events).toHaveLength(2)
    expect(result.events[0].type).toBe('message.user')
    expect(result.events[1].type).toBe('message.end')
  })

  it('deduplicates the same run and sequence', () => {
    const duplicate = event('message.user', { text: 'x' })
    const result = eventsFromHistory([
      { id: 'm1', agent_thoughts: [{ data: { piagent: duplicate } }, { data: { piagent: duplicate } }] },
    ])
    expect(result.events).toHaveLength(1)
  })
})
