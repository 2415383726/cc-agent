import { describe, expect, it } from 'vitest'
import { SCHEMA } from '../src/contract/display'
import { eventsFromHistory } from '../src/projection/history'
import { applyEvent, newView } from '../src/projection/transcript'

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
    const view = newView()
    result.events.forEach((item) => applyEvent(view, item))
    expect(view.entries.filter((item) => item.kind === 'message')
      .map((item: any) => item.text)).toEqual(['first', 'answer one', 'second', 'answer two'])
  })

  it('falls back to query/answer when no Pi events were stored', () => {
    const result = eventsFromHistory([{ id: 'm1', query: 'hello', answer: 'hi' }])
    const view = newView()
    result.events.forEach((item) => applyEvent(view, item))
    expect(view.entries.filter((item) => item.kind === 'message')
      .map((item: any) => item.text)).toEqual(['hello', 'hi'])
  })

  it('deduplicates the same run and sequence', () => {
    const duplicate = event('message.user', { text: 'x' })
    const result = eventsFromHistory([
      { id: 'm1', agent_thoughts: [{ data: { piagent: duplicate } }, { data: { piagent: duplicate } }] },
    ])
    expect(result.events).toHaveLength(1)
  })
})
