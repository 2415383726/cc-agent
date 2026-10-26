import { describe, expect, it, vi } from 'vitest'
import { clearConversationId, conversationSessionKey, loadConversationId, saveConversationId } from './conversationSession'

describe('conversationSession', () => {
  it('scopes saved conversation ids by base url and user while migrating legacy state scoped keys', () => {
    const storage = new Map<string, string>()
    const localStorage = {
      getItem: vi.fn((key: string) => storage.get(key) || null),
      setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
      removeItem: vi.fn((key: string) => storage.delete(key)),
    }

    const config = {
      baseUrl: 'http://localhost/v1/',
      user: 'tester',
      stateId: 'state-1',
    }
    const key = conversationSessionKey(config)

    saveConversationId(localStorage as any, config, 'conv_1')

    expect(key).toBe('copilotkit-dify-session:http://localhost/v1:tester')
    expect(loadConversationId(localStorage as any, config)).toBe('conv_1')
    expect(loadConversationId(localStorage as any, { ...config, stateId: 'state-2' })).toBe('conv_1')

    clearConversationId(localStorage as any, config)
    expect(loadConversationId(localStorage as any, config)).toBe('')
  })

  it('migrates the old state id scoped localStorage entry on read', () => {
    const storage = new Map<string, string>([
      ['copilotkit-dify-session:http://localhost/v1:tester:legacy-state', 'conv_legacy'],
    ])
    const localStorage = {
      getItem: vi.fn((key: string) => storage.get(key) || null),
      setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
      removeItem: vi.fn((key: string) => storage.delete(key)),
    }

    const loaded = loadConversationId(localStorage as any, {
      baseUrl: 'http://localhost/v1',
      user: 'tester',
      stateId: 'legacy-state',
    })

    expect(loaded).toBe('conv_legacy')
    expect(storage.get('copilotkit-dify-session:http://localhost/v1:tester')).toBe('conv_legacy')
  })
})
