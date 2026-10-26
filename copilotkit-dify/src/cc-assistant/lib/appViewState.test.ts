import { describe, expect, it } from 'vitest'
import {
  activeViewForNewConversation,
  conversationThreadKey,
  draftThreadKey,
  loadedConversationByThreadKey,
  mapConversationToThreadKey,
  runningConversationIdsForThreads,
  shouldRestoreLastConversation,
  threadKeyForConversation,
} from './appViewState'

describe('app view state', () => {
  it('keeps ordinary new chat on the home view but opens conversation view for homepage submits', () => {
    expect(activeViewForNewConversation()).toBe('home')
    expect(activeViewForNewConversation({ openConversation: true })).toBe('conversation')
  })

  it('does not restore the last conversation during startup or config refresh', () => {
    expect(shouldRestoreLastConversation()).toBe(false)
  })

  it('uses stable draft and conversation thread keys', () => {
    expect(draftThreadKey('abc')).toBe('draft:abc')
    expect(conversationThreadKey('conv_1')).toBe('conversation:conv_1')
  })

  it('keeps a draft thread when Dify later assigns a real conversation id', () => {
    const mapped = mapConversationToThreadKey({}, 'conv_1', 'draft:abc')

    expect(mapped).toEqual({ conv_1: 'draft:abc' })
    expect(threadKeyForConversation('conv_1', mapped)).toBe('draft:abc')
    expect(threadKeyForConversation('conv_2', mapped)).toBe('conversation:conv_2')
  })

  it('marks a thread as loaded for its assigned Dify conversation without changing the thread key', () => {
    expect(loadedConversationByThreadKey({}, 'draft:abc', 'conv_1')).toEqual({
      'draft:abc': 'conv_1',
    })
  })

  it('derives running conversation ids from running thread keys', () => {
    const conversationsByThread = {
      conv_a: 'draft:a',
      conv_b: 'conversation:conv_b',
    }

    expect(runningConversationIdsForThreads(conversationsByThread, new Set(['draft:a']))).toEqual(['conv_a'])
  })
})
