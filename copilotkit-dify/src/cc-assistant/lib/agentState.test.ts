import { describe, expect, it } from 'vitest'
import { createEmptyAgentState, reduceNormalizedEvent } from './agentState'

describe('agentState reducer', () => {
  it('builds assistant and reasoning messages from streaming deltas', () => {
    let state = createEmptyAgentState()
    state = reduceNormalizedEvent(state, {
      kind: 'thinking_delta',
      text: 'thinking',
      messageId: 'reason_1',
    })
    state = reduceNormalizedEvent(state, {
      kind: 'text_delta',
      text: 'answer',
      messageId: 'msg_1',
    })

    expect(state.messages).toHaveLength(2)
    expect(state.messages[0].role).toBe('reasoning')
    expect(state.messages[0].content).toBe('thinking')
    expect(state.messages[1].role).toBe('assistant')
    expect(state.messages[1].content).toBe('answer')
  })

  it('builds tool call and tool result messages from tool events', () => {
    let state = createEmptyAgentState()
    state = reduceNormalizedEvent(state, {
      kind: 'tool_event',
      state: 'call',
      toolName: 'current_time',
      toolCallId: 'call_1',
      input: { timezone: 'Asia/Shanghai' },
    })
    state = reduceNormalizedEvent(state, {
      kind: 'tool_event',
      state: 'result',
      toolName: 'current_time',
      toolCallId: 'call_1',
      observation: '2026-05-25 12:00:00',
      output: { value: '2026-05-25 12:00:00' },
    })

    expect(state.messages).toHaveLength(2)
    expect(state.messages[0].role).toBe('assistant')
    expect((state.messages[0] as any).toolCalls?.[0].function.name).toBe('current_time')
    expect(state.messages[1].role).toBe('tool')
    expect(state.messages[1].content).toBe('2026-05-25 12:00:00')
  })

  it('turns activity-like events into activity messages', () => {
    let state = createEmptyAgentState()
    state = reduceNormalizedEvent(state, {
      kind: 'generic_activity',
      label: 'cc_agent.skill_apply',
      data: { skillName: 'meeting-notes' },
      messageId: 'activity_1',
    })

    expect(state.messages).toHaveLength(1)
    expect(state.messages[0].role).toBe('activity')
    expect((state.messages[0] as any).activityType).toBe('cc_agent.skill_apply')
  })

  it('updates compression activity with the same message id instead of appending a duplicate', () => {
    let state = createEmptyAgentState()
    state = reduceNormalizedEvent(state, {
      kind: 'compression_event',
      metadata: {
        status: 'started',
        trigger: 'auto',
        compressionId: 'compression:auto:1',
      },
      messageId: 'compression:auto:1',
    })
    state = reduceNormalizedEvent(state, {
      kind: 'compression_event',
      metadata: {
        status: 'completed',
        trigger: 'auto',
        compressionId: 'compression:auto:1',
        summarized_messages: 12,
      },
      messageId: 'compression:auto:1',
    })

    expect(state.messages).toHaveLength(1)
    expect((state.messages[0] as any).activityType).toBe('cc_agent.compression')
    expect((state.messages[0] as any).content.status).toBe('completed')
    expect((state.messages[0] as any).content.summarized_messages).toBe(12)
  })

  it('captures awaiting-user final state as interrupt payload', () => {
    let state = createEmptyAgentState()
    state = reduceNormalizedEvent(state, {
      kind: 'final_state',
      payload: {
        event: 'agent_finished',
        execution_metadata: {
          finish_reason: 'awaiting_user',
          question: {
            id: 'call_1',
            question: 'Which account?',
            purpose: 'clarification',
            options: [{ label: 'Personal', value: 'personal' }],
            fields: [{ name: 'effective_date', label: 'Effective date', type: 'date' }],
            allowCustomInput: true,
          },
        },
      },
      outcome: {
        type: 'interrupt',
        interrupts: [{ id: 'call_1', toolCallId: 'call_1', message: 'Which account?' }],
      },
    })

    expect(state.pendingInterrupt).toMatchObject({
      id: 'call_1',
      question: 'Which account?',
      purpose: 'clarification',
      fields: [{ name: 'effective_date', label: 'Effective date', type: 'date' }],
    })
    expect(state.finishReason).toBe('awaiting_user')
  })
})
