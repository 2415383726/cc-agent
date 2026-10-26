import { describe, expect, it } from 'vitest'
import { normalizeDifyEvent } from './difyEventBridge'

describe('normalizeDifyEvent', () => {
  it('unwraps stringified AG-UI RUN_FINISHED payload nested under agent_log.data.data', () => {
    const event = {
      event: 'agent_log',
      data: {
        data: JSON.stringify({
          type: 'RUN_FINISHED',
          result: {
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
                  allowCustomInput: true,
                  multiSelect: false,
                },
              },
            ],
          },
        }),
      },
    }

    const normalized = normalizeDifyEvent(event as any)

    expect(normalized).toHaveLength(1)
    expect(normalized[0]).toMatchObject({
      kind: 'final_state',
      outcome: {
        type: 'interrupt',
        interrupts: [{ id: 'call_1', toolCallId: 'call_1', message: 'Which account?' }],
      },
      payload: {
        answer: 'Which account?',
      },
    })
  })

  it('keeps a2ui-surface activities as generic activity payloads', () => {
    const event = {
      type: 'ACTIVITY_SNAPSHOT',
      messageId: 'activity_1',
      activityType: 'a2ui-surface',
      content: {
        a2ui_operations: [
          { type: 'create_surface', surfaceId: 'report-demo', catalogId: 'copilotkit://basic' },
        ],
      },
    }

    const normalized = normalizeDifyEvent(event as any)

    expect(normalized).toEqual([
      {
        kind: 'generic_activity',
        protocol: 'ag-ui',
        label: 'a2ui-surface',
        data: {
          a2ui_operations: [
            { type: 'create_surface', surfaceId: 'report-demo', catalogId: 'copilotkit://basic' },
          ],
        },
        messageId: 'activity_1',
        raw: event,
      },
    ])
  })

  it('keeps skill artifact activities as generic activity payloads', () => {
    const event = {
      type: 'ACTIVITY_SNAPSHOT',
      messageId: 'artifact_1',
      activityType: 'cc_agent.skill_artifact',
      content: {
        skillName: 'deck-writer',
        scriptName: 'scripts/build.py',
        message: 'Generated files were attached to this chat response.',
        files: [{ name: 'slides.pptx', size: 4096, status: 'attached' }],
      },
    }

    const normalized = normalizeDifyEvent(event as any)

    expect(normalized).toEqual([
      {
        kind: 'generic_activity',
        protocol: 'ag-ui',
        label: 'cc_agent.skill_artifact',
        data: {
          skillName: 'deck-writer',
          scriptName: 'scripts/build.py',
          message: 'Generated files were attached to this chat response.',
          files: [{ name: 'slides.pptx', size: 4096, status: 'attached' }],
        },
        messageId: 'artifact_1',
        raw: event,
      },
    ])
  })

})
