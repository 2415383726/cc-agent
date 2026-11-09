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

it('restores each complete platform answer beside its own run, preserving activity and terminal facts', async () => {
  const { restoreHistory } = await import('../src/projection/history')
  const records = ['first', 'second'].map((name, index) => ({
    id: `platform-${name}`, query: name, answer: `${name} full ${'x'.repeat(17000)}`,
    agent_thoughts: [
      { data: { piagent: event('run.start', { run_id: name, seq: 1 }) } },
      { data: { piagent: event('message.start', { run_id: name, seq: 2, message_id: `${name}-a` }) } },
      { data: { piagent: event('message.end', { run_id: name, seq: 3, message_id: `${name}-a`, text: `${name} clipped` }) } },
      { data: { piagent: event('tool.end', { run_id: name, seq: 4, tool_call_id: `${name}-tool`, name: 'lookup', result: name }) } },
      { data: { piagent: event('run.state', { run_id: name, seq: 5, status: index ? 'failed' : 'completed', answer: `${name} clipped` }) } },
    ],
  }))
  const view = newView()
  restoreHistory(view, records)
  const answers = view.entries.filter((entry: any) => entry.role === 'assistant') as any[]
  expect(answers.map((entry) => entry.text)).toEqual(records.map((record) => record.answer))
  expect(answers.map((entry) => [entry.platformMessageId, entry.answerComplete, entry.runStatus])).toEqual([
    ['platform-first', true, 'completed'], ['platform-second', true, 'failed'],
  ])
  expect(view.entries.filter((entry) => entry.kind === 'tool')).toHaveLength(2)
  expect(view.entries.filter((entry) => entry.kind === 'terminal').map((entry: any) => entry.terminal.status)).toEqual(['completed', 'failed'])
})

it('binds recorded real Pi events to both native answers without merging the long first answer into the second', async () => {
  const { restoreHistory } = await import('../src/projection/history')
  const fixture = await import('../fixtures/recorded-native-history.json')
  const view = newView()
  restoreHistory(view, fixture.records)
  const answers = view.entries.filter((entry: any) => entry.role === 'assistant') as any[]
  expect(answers).toHaveLength(2)
  expect(answers[0].text.length).toBeGreaterThan(16000)
  expect(answers.map((entry) => entry.text)).toEqual(fixture.records.map((record) => record.answer))
  expect(answers.map((entry) => entry.runStatus)).toEqual(['completed', 'completed'])
  expect(new Set(answers.map((entry) => entry.platformMessageId)).size).toBe(2)
})
