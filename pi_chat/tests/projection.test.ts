import { describe, expect, it } from 'vitest'
import { SCHEMA } from '../src/contract/display'
import {
  applyEvent,
  mergeFinalAnswer,
  newView,
} from '../src/projection/transcript'

let seq = 0
function event(type: string, fields: Record<string, unknown> = {}) {
  seq += 1
  return {
    schema: SCHEMA,
    schema_version: 1,
    type,
    run_id: 'run_test',
    seq,
    ts: seq,
    ...fields,
  } as any
}

describe('transcript projection', () => {
  it('merges deltas and lets the final message override temporary text', () => {
    const view = newView()
    applyEvent(view, event('message.start', { message_id: 'a1' }))
    applyEvent(view, event('message.delta', { message_id: 'a1', delta: 'Hel' }))
    applyEvent(view, event('message.delta', { message_id: 'a1', delta: 'lo' }))
    applyEvent(view, event('message.end', { message_id: 'a1', text: 'Hello final' }))
    const assistant = view.entries.find((entry) => entry.kind === 'message' && entry.role === 'assistant') as any
    expect(assistant.text).toBe('Hello final')
    expect(assistant.streaming).toBe(false)
  })

  it('deduplicates tool end into the same execution card', () => {
    const view = newView()
    applyEvent(view, event('tool.start', { tool_call_id: 'c1', name: 'lookup', arguments: { id: 1 } }))
    applyEvent(view, event('tool.end', { tool_call_id: 'c1', name: 'lookup', status: 'ok', result: 'found' }))
    const tools = view.entries.filter((entry) => entry.kind === 'tool')
    expect(tools).toHaveLength(1)
    expect((tools[0] as any).status).toBe('ok')
    expect((tools[0] as any).result).toBe('found')
  })

  it('hides internal ask/skill tools and shows the real activity cards', () => {
    const view = newView()
    applyEvent(view, event('tool.start', { tool_call_id: 'c1', name: 'ask_user', arguments: {} }))
    applyEvent(view, event('skill.activate', { tool_call_id: 'c2', skill: 'policy', source: 'app' }))
    expect(view.entries.some((entry) => entry.kind === 'tool')).toBe(false)
    expect(view.entries.filter((entry) => entry.kind === 'skill')).toHaveLength(1)
  })

  it('marks questions answered and approvals resolved', () => {
    const view = newView()
    const questionnaire = {
      id: 'q1',
      pending_id: 'q1',
      questions: [{ id: 'a', question: 'Q', type: 'text', options: [] }],
    }
    applyEvent(view, event('question.asked', { questionnaire }))
    applyEvent(view, event('question.answered', { pending_id: 'q1', answers: { a: 'yes' } }))
    const question = view.entries.find((entry) => entry.kind === 'question') as any
    expect(question.status).toBe('answered')
    expect(question.answers.a).toBe('yes')

    applyEvent(view, event('approval.requested', {
      approval: { pending_id: 'p1', tool_call_id: 'c9', tool: 'write', arguments: {} },
    }))
    applyEvent(view, event('approval.resolved', { tool_call_id: 'c9', decision: 'rejected' }))
    const approval = view.entries.find((entry) => entry.kind === 'approval') as any
    expect(approval.status).toBe('rejected')
  })

  it('does not duplicate a matching Dify final answer', () => {
    const view = newView()
    applyEvent(view, event('message.start', { message_id: 'a1' }))
    applyEvent(view, event('message.end', { message_id: 'a1', text: 'The answer' }))
    mergeFinalAnswer(view, 'The answer')
    mergeFinalAnswer(view, '  The answer  ')
    const assistants = view.entries.filter((entry) => entry.kind === 'message' && entry.role === 'assistant')
    expect(assistants).toHaveLength(1)
    expect((assistants[0] as any).platformConfirmed).toBe(true)
  })

  it('adds a platform answer only when Pi produced no text', () => {
    const view = newView()
    mergeFinalAnswer(view, 'Only platform text')
    const assistants = view.entries.filter((entry) => entry.kind === 'message' && entry.role === 'assistant')
    expect(assistants).toHaveLength(1)
    expect((assistants[0] as any).text).toBe('Only platform text')
  })

  it('ignores duplicate run:seq events and records ignored unknown types', () => {
    const view = newView()
    const first = event('message.user', { message_id: 'u1', text: 'hello' })
    applyEvent(view, first)
    applyEvent(view, first)
    expect(view.entries.filter((entry) => entry.kind === 'message')).toHaveLength(1)
    applyEvent(view, event('some.future.event', {}))
    expect(view.ignored).toBe(1)
  })

  it('keeps completion states distinguishable', () => {
    const view = newView()
    applyEvent(view, event('run.state', { status: 'awaiting_user', answer: 'waiting' }))
    expect(view.terminal?.status).toBe('awaiting_user')
    applyEvent(view, event('run.state', { status: 'state_save_failed', answer: 'save failed' }))
    expect(view.terminal?.status).toBe('state_save_failed')
  })
})
