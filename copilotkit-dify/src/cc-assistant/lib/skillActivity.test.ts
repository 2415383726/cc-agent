import { describe, expect, it } from 'vitest'
import { skillActivityViewModel } from './skillActivity'

describe('skillActivityViewModel', () => {
  it('shows only the skill name and status', () => {
    const model = skillActivityViewModel({
      toolName: 'Skill',
      toolCallId: 'call_secret',
      skillName: 'meeting-notes',
      text: '[Skill: meeting-notes]\nDo not leak this prompt body.',
      metadata: {
        injected_message: 'secret injected text',
        prompt: 'secret prompt',
      },
    })

    expect(model).toEqual({
      name: 'meeting-notes',
      status: '已启用',
      label: '已启用 skill: meeting-notes',
    })

    const serialized = JSON.stringify(model)
    expect(serialized).not.toContain('call_secret')
    expect(serialized).not.toContain('Do not leak')
    expect(serialized).not.toContain('secret')
    expect(serialized).not.toContain('prompt')
  })

  it('falls back to a generic skill name without exposing tool details', () => {
    const model = skillActivityViewModel({
      toolName: 'Skill',
      toolCallId: 'call_1',
      text: 'internal text',
    })

    expect(model).toEqual({
      name: 'skill',
      status: '已启用',
      label: '已启用 skill: skill',
    })
  })
})
