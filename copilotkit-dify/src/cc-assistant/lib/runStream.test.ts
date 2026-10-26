import { describe, expect, it } from 'vitest'
import { createRunStream } from './runStream'

describe('complete run stream', () => {
  it.each(['native', 'fallback'])('retains interruption fields and conversation identity from %s', (protocol) => {
    const events: any[] = []
    const questions: any[] = []
    const conversations: string[] = []
    const stream = createRunStream({ next: event => events.push(event) }, {
      runId: 'r', threadId: 't', onInterrupt: question => questions.push(question),
      onConversationId: id => conversations.push(id),
    })
    const question = { id: 'call', question: 'Which?', purpose: 'permission',
      fields: [{ name: 'amount', type: 'number' }], options: [{ label: 'Allow', value: 'allow_once' }],
      allowCustomInput: false, multiSelect: false }
    const payload = { event: 'agent_finished', state_ref: { conversation_id: 'conversation' },
      execution_metadata: { finish_reason: 'awaiting_user', question } }
    const native = { type: 'RUN_FINISHED', runId: 'r', threadId: 't', result: payload, extension: { value: [1, 2] } }
    stream.ingest(protocol === 'native' ? native : { event: 'workflow_finished', data: { outputs: { result: payload } } })
    expect(questions).toEqual([question])
    expect(conversations).toEqual(['conversation'])
    expect(events.filter(event => event.type === 'CUSTOM')[0].value.fields).toEqual(question.fields)
    if (protocol === 'native') expect(events[events.length - 1]).toEqual(native)
  })

  it('closes fallback messages once and ignores trailing text after the final state', () => {
    const events: any[] = []
    const stream = createRunStream({ next: event => events.push(event) }, { runId: 'r', threadId: 't' })
    stream.ingest({ event: 'message', answer: 'before' })
    stream.ingest({ event: 'workflow_finished', data: { outputs: { event: 'agent_finished', answer: 'before' } } })
    stream.ingest({ event: 'message', answer: 'late' })
    stream.finish(); stream.finish()
    expect(events.filter(event => event.type === 'TEXT_MESSAGE_CONTENT').map(event => event.delta)).toEqual(['before'])
    expect(events.filter(event => event.type === 'TEXT_MESSAGE_END')).toHaveLength(1)
    expect(events.filter(event => event.type === 'RUN_FINISHED')).toHaveLength(1)
  })

  it('preserves real tool lifecycles and hides internal tool plumbing', () => {
    const events: any[] = []
    const stream = createRunStream({ next: event => events.push(event) }, { runId: 'r', threadId: 't' })
    for (const [id, name] of [['internal', 'UserPrompt'], ['external', 'Search']]) {
      stream.ingest({ event: 'agent_log', data: { type: 'tool_call', tool_call_id: id, name, arguments: { q: 'x' } } })
      stream.ingest({ event: 'agent_log', data: { type: 'tool_end', tool_call_id: id, name, observation: 'found' } })
    }
    expect(events.filter(event => event.type.startsWith('TOOL_CALL')).map(event => event.toolCallId)).toEqual(['external', 'external', 'external', 'external'])
  })

  it('starts once when metadata precedes native events and retains native activities', () => {
    const events: any[] = []
    const stream = createRunStream({ next: event => events.push(event) }, { runId: 'r', threadId: 't' })
    stream.ingest({ event: 'agent_log', data: { type: 'metadata', count: 1 } })
    stream.ingest({ type: 'RUN_STARTED', runId: 'r', threadId: 't' })
    const activity = { type: 'ACTIVITY_SNAPSHOT', messageId: 'a', activityType: 'custom', content: { untouched: true } }
    stream.ingest(activity)
    expect(events.filter(event => event.type === 'RUN_STARTED')).toHaveLength(1)
    expect(events[events.length - 1]).toEqual(activity)
  })
})
