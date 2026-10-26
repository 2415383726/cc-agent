import type { DifyConversation } from './difyTransport'

export interface ConversationGroup {
  id: 'today' | 'recent' | 'earlier'
  label: string
  conversations: DifyConversation[]
}

export const RECENT_CONVERSATION_LIMIT = 10
export const CHAT_BOTTOM_THRESHOLD = 96

export interface ChatScrollMetrics {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

export function chatDistanceFromBottom(metrics: ChatScrollMetrics) {
  return Math.max(0, metrics.scrollHeight - metrics.clientHeight - metrics.scrollTop)
}

export function isChatNearBottom(
  metrics: ChatScrollMetrics,
  threshold = CHAT_BOTTOM_THRESHOLD,
) {
  return chatDistanceFromBottom(metrics) <= threshold
}

export function filterConversations(conversations: DifyConversation[], search: string) {
  const query = String(search || '').trim().toLowerCase()
  if (!query) return conversations
  return conversations.filter((conversation) => {
    return (
      conversation.name.toLowerCase().includes(query) ||
      conversation.id.toLowerCase().includes(query)
    )
  })
}

export function selectRecentConversations(conversations: DifyConversation[]) {
  return conversations.slice(0, RECENT_CONVERSATION_LIMIT)
}

export function groupConversationsByDate(conversations: DifyConversation[], nowSeconds = Date.now() / 1000): ConversationGroup[] {
  const startOfToday = new Date(nowSeconds * 1000)
  startOfToday.setHours(0, 0, 0, 0)
  const todaySeconds = startOfToday.getTime() / 1000
  const recentSeconds = nowSeconds - 7 * 24 * 60 * 60
  const buckets: ConversationGroup[] = [
    { id: 'today', label: '今天', conversations: [] },
    { id: 'recent', label: '近 7 天', conversations: [] },
    { id: 'earlier', label: '更早', conversations: [] },
  ]

  for (const conversation of conversations) {
    const updatedAt = Number(conversation.updatedAt || conversation.createdAt || 0)
    if (updatedAt >= todaySeconds) {
      buckets[0].conversations.push(conversation)
    } else if (updatedAt >= recentSeconds) {
      buckets[1].conversations.push(conversation)
    } else {
      buckets[2].conversations.push(conversation)
    }
  }

  return buckets.filter((bucket) => bucket.conversations.length > 0)
}
