import { describe, expect, it } from 'vitest'
import {
  chatDistanceFromBottom,
  filterConversations,
  groupConversationsByDate,
  isChatNearBottom,
  selectRecentConversations,
} from './conversationView'
import type { DifyConversation } from './difyTransport'

function conversation(id: string, name: string, updatedAt: number): DifyConversation {
  return {
    id,
    name,
    status: 'normal',
    introduction: '',
    inputs: {},
    createdAt: updatedAt,
    updatedAt,
  }
}

describe('conversationView', () => {
  it('filters conversations by name and id using case-insensitive text', () => {
    const conversations = [
      conversation('conv_plan', 'Plan Review', 200),
      conversation('conv_notes', 'Meeting Notes', 100),
    ]

    expect(filterConversations(conversations, 'plan')).toEqual([conversations[0]])
    expect(filterConversations(conversations, 'NOTES')).toEqual([conversations[1]])
    expect(filterConversations(conversations, 'conv_')).toEqual(conversations)
  })

  it("detects whether the chat viewport should follow the latest message", () => {
    expect(chatDistanceFromBottom({ scrollTop: 600, scrollHeight: 1500, clientHeight: 800 })).toBe(100)
    expect(isChatNearBottom({ scrollTop: 604, scrollHeight: 1500, clientHeight: 800 })).toBe(true)
    expect(isChatNearBottom({ scrollTop: 400, scrollHeight: 1500, clientHeight: 800 })).toBe(false)
  })

  it('groups conversations into today, recent, and earlier buckets', () => {
    const now = Date.UTC(2026, 5, 6, 12, 0, 0) / 1000
    const conversations = [
      conversation('today', 'Today', now - 60),
      conversation('recent', 'Recent', now - 3 * 24 * 60 * 60),
      conversation('earlier', 'Earlier', now - 20 * 24 * 60 * 60),
    ]

    expect(groupConversationsByDate(conversations, now)).toEqual([
      { id: 'today', label: '今天', conversations: [conversations[0]] },
      { id: 'recent', label: '近 7 天', conversations: [conversations[1]] },
      { id: 'earlier', label: '更早', conversations: [conversations[2]] },
    ])
  })

  it('limits recent conversations to the first ten items', () => {
    const conversations = Array.from({ length: 12 }, (_, index) => {
      return conversation(`conv_${index + 1}`, `Conversation ${index + 1}`, 200 - index)
    })

    expect(selectRecentConversations(conversations).map((item) => item.id)).toEqual([
      'conv_1',
      'conv_2',
      'conv_3',
      'conv_4',
      'conv_5',
      'conv_6',
      'conv_7',
      'conv_8',
      'conv_9',
      'conv_10',
    ])
  })
})
