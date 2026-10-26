import { describe, expect, it } from 'vitest'
import { extractAgUiEvent, normalizeDifyEvent } from './difyEventBridge'

describe('Dify stream extraction', () => {
  it('unwraps native events without interpreting or dropping extension fields', () => {
    const native = { type: 'RUN_FINISHED', result: { answer: 'done' }, outcome: { type: 'interrupt' }, extension: { value: 1 } }
    expect(extractAgUiEvent({ event: 'agent_log', data: { data: JSON.stringify(native) } })).toEqual(native)
  })
  it('interprets a real Dify final result and legacy tool event', () => {
    const payload = { event: 'agent_finished', answer: 'done', execution_metadata: { finish_reason: 'final' } }
    expect(normalizeDifyEvent({ event: 'workflow_finished', data: { outputs: { result: payload } } })).toMatchObject([{ kind: 'final_state', payload }])
    expect(normalizeDifyEvent({ event: 'agent_log', data: { type: 'tool_call', name: 'Search', tool_call_id: 't' } })).toMatchObject([{ kind: 'tool_event', toolName: 'Search', toolCallId: 't' }])
  })
})
