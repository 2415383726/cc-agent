import { describe, expect, it, vi } from 'vitest'
import type { BaseEvent } from '@ag-ui/core'
import { createDifyRunEmitter } from './difyRunAdapter'

function recorder() {
  const events: BaseEvent[] = []
  return {
    events,
    observer: {
      next: (event: BaseEvent) => {
        events.push(event)
      },
      error: vi.fn(),
      complete: vi.fn(),
    },
  }
}

describe('difyRunAdapter', () => {
  it('hides UserPrompt tool events and emits interrupt before RUN_FINISHED', () => {
    const { events, observer } = recorder()
    const emitter = createDifyRunEmitter(observer as any, {
      runId: 'run_1',
      threadId: 'thread_1',
    })

    emitter.emitNormalized({
      kind: 'tool_event',
      state: 'call',
      toolName: 'UserPrompt',
      toolCallId: 'call_1',
      input: { question: 'Which account?' },
      raw: {},
    })

    emitter.emitNormalized({
      kind: 'tool_event',
      state: 'result',
      toolName: 'UserPrompt',
      toolCallId: 'call_1',
      observation: 'pending',
      raw: {},
    })

    emitter.emitNormalized({
      kind: 'final_state',
      payload: {
        answer: 'Which account?',
        executionMetadata: {
          finishReason: 'awaiting_user',
        },
      },
      outcome: {
        type: 'interrupt',
        interrupts: [
          {
            id: 'call_1',
            toolCallId: 'call_1',
            message: 'Which account?',
            metadata: {
              purpose: 'clarification',
              options: [{ label: 'A', value: 'a', description: '' }],
              fields: [{ name: 'amount', label: 'Amount', type: 'number' }],
              allowCustomInput: true,
              multiSelect: false,
            },
          },
        ],
      },
      raw: {},
    })

    expect(events.map(event => event.type)).toEqual([
      'CUSTOM',
      'RUN_FINISHED',
    ])
    expect(events[0]).toMatchObject({
      type: 'CUSTOM',
      name: 'on_interrupt',
      value: {
        id: 'call_1',
        question: 'Which account?',
        fields: [{ name: 'amount', label: 'Amount', type: 'number' }],
      },
    })
  })

  it('keeps normal tool lifecycle for non-interrupt tools', () => {
    const { events, observer } = recorder()
    const emitter = createDifyRunEmitter(observer as any, {
      runId: 'run_1',
      threadId: 'thread_1',
    })

    emitter.emitNormalized({
      kind: 'tool_event',
      state: 'call',
      toolName: 'current_time',
      toolCallId: 'call_1',
      input: { timezone: 'Asia/Shanghai' },
      raw: {},
    })

    emitter.emitNormalized({
      kind: 'tool_event',
      state: 'result',
      toolName: 'current_time',
      toolCallId: 'call_1',
      observation: '2026-05-26 12:00:00',
      output: { value: '2026-05-26 12:00:00' },
      raw: {},
    })

    expect(events).toMatchObject([
      { type: 'TOOL_CALL_START', toolCallId: 'call_1', toolCallName: 'current_time' },
      { type: 'TOOL_CALL_ARGS', toolCallId: 'call_1' },
      { type: 'TOOL_CALL_RESULT', toolCallId: 'call_1', content: '2026-05-26 12:00:00' },
      { type: 'TOOL_CALL_END', toolCallId: 'call_1' },
    ])
  })

  it('ignores trailing events after RUN_FINISHED', () => {
    const { events, observer } = recorder()
    const emitter = createDifyRunEmitter(observer as any, {
      runId: 'run_1',
      threadId: 'thread_1',
    })

    emitter.emitNormalized({
      kind: 'final_state',
      payload: {
        answer: 'done',
        executionMetadata: {
          finishReason: 'stop',
        },
      },
      raw: {},
    })

    emitter.emitNormalized({
      kind: 'text_delta',
      text: 'should be ignored',
      raw: {},
    })

    expect(events.map(event => event.type)).toEqual([
      'RUN_FINISHED',
    ])
  })

  it('emits a2ui-surface as activity snapshot content', () => {
    const { events, observer } = recorder()
    const emitter = createDifyRunEmitter(observer as any, {
      runId: 'run_1',
      threadId: 'thread_1',
    })

    emitter.emitNormalized({
      kind: 'generic_activity',
      label: 'a2ui-surface',
      data: {
        a2ui_operations: [
          { type: 'create_surface', surfaceId: 'report-demo', catalogId: 'copilotkit://basic' },
        ],
      },
      raw: {},
    })

    expect(events).toMatchObject([
      {
        type: 'ACTIVITY_SNAPSHOT',
        activityType: 'a2ui-surface',
        content: {
          a2ui_operations: [
            { type: 'create_surface', surfaceId: 'report-demo', catalogId: 'copilotkit://basic' },
          ],
        },
      },
    ])
  })

  it('emits skill application as a cc_agent.skill_apply activity snapshot', () => {
    const { events, observer } = recorder()
    const emitter = createDifyRunEmitter(observer as any, {
      runId: 'run_1',
      threadId: 'thread_1',
    })

    emitter.emitNormalized({
      kind: 'skill_event',
      toolName: 'Skill',
      toolCallId: 'call_skill',
      skillName: 'meeting-notes',
      text: '[Skill: meeting-notes]\nsecret prompt body',
      raw: {},
    })

    expect(events).toMatchObject([
      {
        type: 'ACTIVITY_SNAPSHOT',
        activityType: 'cc_agent.skill_apply',
        content: {
          toolName: 'Skill',
          toolCallId: 'call_skill',
          skillName: 'meeting-notes',
          text: '[Skill: meeting-notes]\nsecret prompt body',
        },
      },
    ])
  })

  it('hides internal Skill tool lifecycle while keeping skill activity visible', () => {
    const { events, observer } = recorder()
    const emitter = createDifyRunEmitter(observer as any, {
      runId: 'run_1',
      threadId: 'thread_1',
    })

    emitter.emitNormalized({
      kind: 'tool_event',
      state: 'call',
      toolName: 'Skill',
      toolCallId: 'call_skill',
      input: { name: 'meeting-notes' },
      raw: {},
    })

    emitter.emitNormalized({
      kind: 'tool_event',
      state: 'result',
      toolName: 'Skill',
      toolCallId: 'call_skill',
      observation: 'internal skill applied',
      raw: {},
    })

    emitter.emitNormalized({
      kind: 'skill_event',
      toolName: 'Skill',
      toolCallId: 'call_skill',
      skillName: 'meeting-notes',
      text: '[Skill: meeting-notes]\nsecret prompt body',
      raw: {},
    })

    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({
      type: 'ACTIVITY_SNAPSHOT',
      activityType: 'cc_agent.skill_apply',
      content: {
        skillName: 'meeting-notes',
      },
    })
  })
})
