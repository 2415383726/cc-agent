export type AppActiveView = 'home' | 'conversation'

export interface NewConversationViewOptions {
  openConversation?: boolean
}

export function activeViewForNewConversation(options: NewConversationViewOptions = {}): AppActiveView {
  return options.openConversation ? 'conversation' : 'home'
}

export function shouldRestoreLastConversation() {
  return false
}

export type ConversationThreadKeyMap = Record<string, string>

export function draftThreadKey(id: string) {
  return `draft:${String(id || '').trim() || 'new'}`
}

export function conversationThreadKey(conversationId: string) {
  return `conversation:${String(conversationId || '').trim()}`
}

export function threadKeyForConversation(conversationId: string, mappedThreadKeys: ConversationThreadKeyMap) {
  const id = String(conversationId || '').trim()
  if (!id) return ''
  return mappedThreadKeys[id] || conversationThreadKey(id)
}

export function mapConversationToThreadKey(
  mappedThreadKeys: ConversationThreadKeyMap,
  conversationId: string,
  threadKey: string,
) {
  const id = String(conversationId || '').trim()
  const key = String(threadKey || '').trim()
  if (!id || !key) return mappedThreadKeys
  return {
    ...mappedThreadKeys,
    [id]: key,
  }
}

export function loadedConversationByThreadKey(
  loadedByThreadKey: ConversationThreadKeyMap,
  threadKey: string,
  conversationId: string,
) {
  const key = String(threadKey || '').trim()
  const id = String(conversationId || '').trim()
  if (!key || !id) return loadedByThreadKey
  return {
    ...loadedByThreadKey,
    [key]: id,
  }
}

export function runningConversationIdsForThreads(
  mappedThreadKeys: ConversationThreadKeyMap,
  runningThreadKeys: ReadonlySet<string>,
) {
  return Object.entries(mappedThreadKeys)
    .filter(([, threadKey]) => runningThreadKeys.has(threadKey))
    .map(([conversationId]) => conversationId)
}
