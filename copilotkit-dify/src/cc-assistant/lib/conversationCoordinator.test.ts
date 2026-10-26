import { describe, expect, it } from 'vitest'
import { createConversationCoordinator, loadPendingHistory, waitForVisibleAgent } from './conversationCoordinator'

describe('conversation coordination', () => {
  it('keeps background conversation callbacks on their original thread', () => {
    let seq = 0
    const sessions = createConversationCoordinator(() => 'user', () => String(++seq))
    const a = sessions.threadId.value
    sessions.runStatus({ conversationId: '', threadId: a, running: true })
    sessions.startNew({ openConversation: true })
    const b = sessions.threadId.value
    sessions.conversationChanged({ conversationId: 'conversation-a', threadId: a })
    expect(sessions.threadId.value).toBe(b)
    expect(sessions.currentConversationId.value).toBe('')
    expect(sessions.runningConversationIds.value).toEqual(['conversation-a'])
    sessions.select('conversation-a')
    expect(sessions.threadId.value).toBe(a)
    expect(sessions.historyLoading.value).toBe(false)
  })
  it.each([false, true])('ignores stale history completion and errors (failure=%s)', async (failure) => {
    const sessions = createConversationCoordinator(() => 'user')
    sessions.select('a')
    const a = sessions.currentTicket()!
    let resolve!: (value: string) => void
    let reject!: (error: Error) => void
    const response = new Promise<string>((yes, no) => { resolve = yes; reject = no })
    const loading = loadPendingHistory(a, sessions.currentTicket, async () => ({
      threadId: a.threadId, selectConversation: () => response,
    }))
    await Promise.resolve()
    sessions.select('b')
    const b = sessions.currentTicket()!
    if (failure) reject(new Error('old failure')); else resolve('old messages')
    expect(await loading).toBeNull()
    expect(sessions.historyLoaded(a)).toBe(false)
    expect(sessions.historyFailed({ ...a, message: 'old failure' })).toBe(false)
    expect(sessions.currentConversationId.value).toBe('b')
    expect(sessions.historyLoading.value).toBe(true)
    expect(sessions.historyError.value).toBe('')
    expect(sessions.historyLoaded(b)).toBe(true)
    sessions.select('b')
    expect(sessions.currentTicket()).toBeNull()
  })

  it('does not pick a different clone if the user switches while waiting', async () => {
    let thread = 'a'
    const clone = { threadId: 'a' }
    const visible = await waitForVisibleAgent(() => clone, () => thread, async () => {
      thread = 'b'
      clone.threadId = 'b'
    })
    expect(visible).toBeUndefined()
  })

  it('invalidates pending history before loading a clone from a newer selection', async () => {
    const sessions = createConversationCoordinator(() => 'user')
    sessions.select('a')
    const a = sessions.currentTicket()!
    let invoked = false
    const result = await loadPendingHistory(a, sessions.currentTicket, async () => {
      sessions.select('b')
      return { threadId: a.threadId, selectConversation: async () => { invoked = true } }
    })
    expect(result).toBeNull()
    expect(invoked).toBe(false)
    expect(sessions.currentConversationId.value).toBe('b')
  })

  it('clears identity and pending history when the configured user changes', () => {
    let user = 'alice'
    const sessions = createConversationCoordinator(() => user)
    sessions.select('a')
    const old = sessions.currentTicket()!
    user = 'bob'
    sessions.registerActiveThread()
    sessions.conversationChanged({ conversationId: 'a', threadId: old.threadId })
    expect(sessions.currentConversationId.value).toBe('')
    expect(sessions.currentTicket()).toBeNull()
    expect(sessions.activeView.value).toBe('home')
    expect(sessions.threadId.value).toContain('bob')
  })

  it('removes background running state and opens a new draft after active deletion', () => {
    const sessions = createConversationCoordinator(() => 'user')
    const original = sessions.threadId.value
    sessions.conversationChanged({ conversationId: 'a', threadId: original })
    sessions.runStatus({ conversationId: 'a', threadId: original, running: true })
    sessions.startNew()
    sessions.remove('a')
    expect(sessions.runningConversationIds.value).toEqual([])
    sessions.select('b')
    sessions.remove('b')
    expect(sessions.activeView.value).toBe('home')
    expect(sessions.currentConversationId.value).toBe('')
  })

})
