import { describe, expect, it } from 'vitest'
import { chatThreadIdForDifySession } from './chatThread'

describe('chatThreadIdForDifySession', () => {
  it('keeps one explicit CopilotKit thread per local conversation thread key', () => {
    const first = chatThreadIdForDifySession({ user: 'tester', threadKey: 'conversation:conv_1' })
    const second = chatThreadIdForDifySession({ user: 'tester', threadKey: 'conversation:conv_2' })

    expect(first).toBe('copilotkit-dify:tester:conversation:conv_1')
    expect(second).toBe('copilotkit-dify:tester:conversation:conv_2')
    expect(second).not.toBe(first)
  })

  it('sanitizes user and thread key values for thread ids', () => {
    expect(chatThreadIdForDifySession({ user: 'team user/01', threadKey: 'draft:hello world/01' })).toBe('copilotkit-dify:team_user_01:draft:hello_world_01')
  })
})
