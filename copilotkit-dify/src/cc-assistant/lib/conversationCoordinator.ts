import { computed, readonly, ref } from 'vue'
import { chatThreadIdForDifySession } from './chatThread'

export interface HistoryTicket {
  conversationId: string
  threadId: string
  requestId: number
}
interface ConversationChange { conversationId: string; threadId: string }
interface HistoryResult extends HistoryTicket { result?: unknown; message?: string }

/** Own conversation identity, loaded history and stale-result rules for the assistant. */
export function createConversationCoordinator(
  getUser: () => string,
  createId: () => string = () => globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2, 10),
) {
  const activeView = ref<'home' | 'conversation'>('home')
  const currentConversationId = ref('')
  const activeKey = ref('')
  const historyLoading = ref(false)
  const historyError = ref('')
  const pending = ref<(HistoryTicket & { threadKey: string }) | null>(null)
  const conversationKeys = new Map<string, string>()
  const loaded = new Map<string, string>()
  const keysByThreadId = new Map<string, string>()
  const running = ref(new Set<string>())
  const mappingRevision = ref(0)
  let sequence = 0
  let user = getUser()
  const idForKey = (key: string) => chatThreadIdForDifySession({ user: getUser(), threadKey: key })
  const register = (key: string) => keysByThreadId.set(idForKey(key), key)
  const keyForId = (id: string) => id ? keysByThreadId.get(id) || '' : activeKey.value
  const clearLoad = () => { pending.value = null; historyLoading.value = false; historyError.value = '' }
  const associate = (id: string, key: string, historyLoaded = false) => {
    if (!id || !key) return
    conversationKeys.set(id, key)
    if (historyLoaded) loaded.set(key, id)
    mappingRevision.value += 1
  }
  function startNew(options: { openConversation?: boolean } = {}) {
    sequence += 1
    activeKey.value = `draft:${createId()}`
    register(activeKey.value)
    activeView.value = options.openConversation ? 'conversation' : 'home'
    currentConversationId.value = ''
    clearLoad()
  }
  function registerActiveThread() {
    if (user !== getUser()) {
      user = getUser()
      conversationKeys.clear(); loaded.clear(); keysByThreadId.clear()
      running.value = new Set(); mappingRevision.value += 1
      startNew()
    }
    register(activeKey.value)
  }
  function select(conversationId: string) {
    const id = String(conversationId || '').trim()
    if (!id) return
    registerActiveThread()
    const key = conversationKeys.get(id) || `conversation:${id}`
    register(key)
    activeKey.value = key
    currentConversationId.value = id
    activeView.value = 'conversation'
    clearLoad()
    const requestId = ++sequence
    if (loaded.get(key) !== id) {
      historyLoading.value = true
      pending.value = { conversationId: id, threadKey: key, threadId: idForKey(key), requestId }
    }
  }
  function currentTicket(): HistoryTicket | null {
    const ticket = pending.value
    return ticket && activeView.value === 'conversation'
      ? { conversationId: ticket.conversationId, threadId: ticket.threadId, requestId: ticket.requestId }
      : null
  }
  const matches = (result: HistoryTicket) => sameTicket(currentTicket(), result)
  function historyLoaded(result: HistoryResult) {
    if (!matches(result) || !pending.value) return false
    associate(result.conversationId, pending.value.threadKey, true)
    clearLoad()
    return true
  }
  function historyFailed(result: HistoryResult) {
    if (!matches(result)) return false
    pending.value = null; historyLoading.value = false
    historyError.value = result.message || '历史对话加载失败'
    return true
  }
  function conversationChanged(change: ConversationChange) {
    registerActiveThread()
    const key = keyForId(change.threadId)
    if (!key) return false
    associate(change.conversationId, key, true)
    if (key !== activeKey.value) return false
    currentConversationId.value = change.conversationId
    if (change.conversationId) activeView.value = 'conversation'
    return true
  }
  function runStatus(change: ConversationChange & { running: boolean }) {
    registerActiveThread()
    const key = keyForId(change.threadId)
    if (!key) return
    associate(change.conversationId, key)
    const next = new Set(running.value)
    if (change.running) next.add(key); else next.delete(key)
    running.value = next
  }
  function remove(conversationId: string) {
    const key = conversationKeys.get(conversationId)
    conversationKeys.delete(conversationId)
    if (key) {
      loaded.delete(key)
      running.value = new Set([...running.value].filter(value => value !== key))
      keysByThreadId.delete(idForKey(key))
    }
    mappingRevision.value += 1
    if (currentConversationId.value === conversationId) startNew()
  }
  startNew()
  return {
    activeView: readonly(activeView), currentConversationId: readonly(currentConversationId),
    historyLoading: readonly(historyLoading), historyError: readonly(historyError),
    threadId: computed(() => idForKey(activeKey.value)),
    pendingHistoryConversationId: computed(() => pending.value?.conversationId || ''),
    pendingHistoryLoadId: computed(() => pending.value?.requestId || 0),
    runningConversationIds: computed(() => {
      void mappingRevision.value
      return [...conversationKeys].filter(([, key]) => running.value.has(key)).map(([id]) => id)
    }),
    startNew, select, currentTicket, historyLoaded, historyFailed,
    conversationChanged, runStatus, remove, registerActiveThread,
    showHome() { activeView.value = 'home'; clearLoad() },
  }
}

function sameTicket(current: HistoryTicket | null, expected: HistoryTicket) {
  return Boolean(current && current.requestId === expected.requestId && current.conversationId === expected.conversationId && current.threadId === expected.threadId)
}

export async function waitForVisibleAgent<T extends { threadId?: string }>(
  getAgent: () => T | undefined,
  getThreadId: () => string,
  settle: () => Promise<unknown>,
): Promise<T | undefined> {
  const target = getThreadId()
  for (let attempt = 0; attempt < 8; attempt += 1) {
    await settle()
    if (getThreadId() !== target) return undefined
    const agent = getAgent()
    if (agent && (!target || agent.threadId === target)) return agent
    await new Promise(resolve => setTimeout(resolve, 0))
  }
  return undefined
}

/** A history result belongs to its original ticket, including errors after a switch. */
export async function loadPendingHistory(
  ticket: HistoryTicket,
  currentTicket: () => HistoryTicket | null,
  visibleAgent: () => Promise<{ threadId?: string; selectConversation?: (id: string, canApply?: () => boolean) => Promise<unknown> } | undefined>,
): Promise<{ result: unknown } | null> {
  if (!sameTicket(currentTicket(), ticket)) return null
  try {
    const agent = await visibleAgent()
    if (!sameTicket(currentTicket(), ticket)) return null
    if (!agent?.selectConversation) throw new Error('当前 Agent 不支持加载历史会话')
    if (agent.threadId !== ticket.threadId) return null
    const result = await agent.selectConversation(ticket.conversationId, () => sameTicket(currentTicket(), ticket))
    return sameTicket(currentTicket(), ticket) ? { result } : null
  } catch (error) {
    if (!sameTicket(currentTicket(), ticket)) return null
    throw error
  }
}
