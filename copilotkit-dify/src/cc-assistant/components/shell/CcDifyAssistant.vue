<template>
  <CopilotKitProvider
    :self-managed-agents="{ default: agent }"
    :a2ui="{ theme: {} }"
    :render-activity-messages="activityRenderers"
    :show-dev-console="false"
    :on-error="(err: any) => console.error('[CopilotKit Error]', err)"
  >
    <CopilotChatConfigurationProvider
      agent-id="default"
      :thread-id="chatThreadId"
      :has-explicit-thread-id="true"
    >
      <div class="cc-dify-assistant-shell" :style="assistantShellStyle">
        <DrawerExperience
          ref="drawerRef"
          v-model:conversation-search="conversationSearch"
          :title="titleText"
          :catalog="resolvedCatalog"
          :active-view="activeView"
          :active-conversation-id="currentConversationId"
          :conversations="conversations"
          :conversations-loading="conversationsLoading"
          :conversations-error="conversationsError"
          :conversations-has-more="conversationsHasMore"
          :disabled-reason="sendDisabledReason"
          :history-loading="historyLoading"
          :history-error="historyError"
          :expected-thread-id="chatThreadId"
          :pending-history-conversation-id="pendingHistoryConversationId"
          :pending-history-load-id="pendingHistoryLoadId"
          :running-conversation-ids="runningConversationIds"
          :floating-dock-storage-key="floatingDockKey"
          :default-sidebar-collapsed="props.ui?.defaultSidebarCollapsed ?? true"
          @home="handleHome"
          @new-conversation="handleNewConversation"
          @select-conversation="selectConversation"
          @history-loaded="handleHistoryLoaded"
          @history-load-failed="handleHistoryLoadFailed"
          @delete-conversation="deleteConversationById"
          @rename-conversation="renameConversationByRecord"
          @load-more-conversations="loadMoreConversations"
          @conversation-updated="refreshConversations"
        />
      </div>
    </CopilotChatConfigurationProvider>
  </CopilotKitProvider>
</template>

<script setup lang="ts">
import { computed, nextTick, provide, ref, watch } from 'vue'
import { CopilotChatConfigurationProvider, CopilotKitProvider } from '@copilotkit/vue/v2'
import DrawerExperience from './DrawerExperience.vue'
import {
  DEFAULT_ASSISTANT_STORAGE_KEY_PREFIX,
  assistantFloatingDockStorageKey,
  assistantUiStyle,
  normalizeDifyAssistantConfig,
  validateDifyAssistantConfig,
  type CcDifyAssistantProps,
} from '../../lib/assistantConfig'
import { resolveAssistantCatalog, type AssistantCatalog } from '../../lib/assistantCatalog'
import type { LaunchWithMessageOptions } from '../../lib/assistantLauncher'
import { createCcActivityRenderers } from '../../lib/activityRenderers'
import {
  activeViewForNewConversation,
  draftThreadKey,
  loadedConversationByThreadKey,
  mapConversationToThreadKey,
  runningConversationIdsForThreads,
  shouldRestoreLastConversation,
  threadKeyForConversation,
  type ConversationThreadKeyMap,
} from '../../lib/appViewState'
import { chatThreadIdForDifySession } from '../../lib/chatThread'
import { clearConversationId, saveConversationId } from '../../lib/conversationSession'
import { copilotDifyDebug } from '../../lib/debugLog'
import { DifyAgUiAgent } from '../../lib/DifyAgUiAgent'
import {
  deleteConversation,
  listConversations,
  renameConversation,
  type DifyConversation,
} from '../../lib/difyTransport'

type DrawerExperienceHandle = {
  openDrawer: () => void
  closeDrawer: () => void
  prepareFreshConversation: () => Promise<any>
  launchWithMessage: (text: string, options?: LaunchWithMessageOptions) => Promise<boolean>
}

const props = withDefaults(defineProps<CcDifyAssistantProps>(), {
  title: '系统助手',
  storageKeyPrefix: DEFAULT_ASSISTANT_STORAGE_KEY_PREFIX,
})

const drawerRef = ref<DrawerExperienceHandle | null>(null)
const historyLoading = ref(false)
const historyError = ref('')
const conversationsLoading = ref(false)
const conversationsError = ref('')
const conversationsHasMore = ref(false)
const conversationsLastId = ref('')
const conversations = ref<DifyConversation[]>([])
const conversationSearch = ref('')
const activeView = ref<'home' | 'conversation'>('home')
const currentConversationId = ref('')
const activeThreadKey = ref(createDraftThreadKey())
const conversationThreadKeys = ref<ConversationThreadKeyMap>({})
const loadedConversationsByThreadKey = ref<ConversationThreadKeyMap>({})
const runningThreadKeys = ref<Set<string>>(new Set())
const threadKeysByThreadId = ref<Record<string, string>>({})
const pendingHistoryLoad = ref<{ conversationId: string; threadKey: string; requestId: number } | null>(null)
const activityRenderers = createCcActivityRenderers()
const titleText = computed(() => props.title || '系统助手')
const resolvedCatalog = computed<AssistantCatalog>(() => resolveAssistantCatalog(props.catalog))
const assistantShellStyle = computed(() => assistantUiStyle(props.ui))
const difyConfig = computed(() => normalizeDifyAssistantConfig(props.dify || {}))
const floatingDockKey = computed(() => assistantFloatingDockStorageKey(props.storageKeyPrefix))
const chatThreadId = computed(() => chatThreadIdForDifySession({
  user: difyConfig.value.user,
  threadKey: activeThreadKey.value,
}))
const pendingHistoryConversationId = computed(() => pendingHistoryLoad.value?.conversationId || '')
const pendingHistoryLoadId = computed(() => pendingHistoryLoad.value?.requestId || 0)
const runningConversationIds = computed(() => runningConversationIdsForThreads(conversationThreadKeys.value, runningThreadKeys.value))
const sendDisabledReason = computed(() => validateDifyAssistantConfig(difyConfig.value))

provide('difyBaseUrl', computed(() => difyConfig.value.baseUrl))

let historyLoadSeq = 0
let conversationLoadSeq = 0

function createDraftThreadKey() {
  const id = globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2, 10)
  return draftThreadKey(id)
}

function threadIdForKey(threadKey: string) {
  return chatThreadIdForDifySession({
    user: difyConfig.value.user,
    threadKey,
  })
}

function registerThreadKey(threadKey: string) {
  const key = String(threadKey || '').trim()
  if (!key) return
  threadKeysByThreadId.value = {
    ...threadKeysByThreadId.value,
    [threadIdForKey(key)]: key,
  }
}

function threadKeyFromThreadId(threadId: string) {
  const id = String(threadId || '').trim()
  if (!id) return activeThreadKey.value
  if (threadKeysByThreadId.value[id]) return threadKeysByThreadId.value[id]
  if (id === threadIdForKey(activeThreadKey.value)) return activeThreadKey.value
  for (const key of Object.values(conversationThreadKeys.value)) {
    if (id === threadIdForKey(key)) return key
  }
  return ''
}

function setThreadRunning(threadKey: string, running: boolean) {
  const key = String(threadKey || '').trim()
  if (!key) return
  const next = new Set(runningThreadKeys.value)
  if (running) next.add(key)
  else next.delete(key)
  runningThreadKeys.value = next
}

function removeConversationThreadState(conversationId: string) {
  const id = String(conversationId || '').trim()
  if (!id) return
  const threadKey = conversationThreadKeys.value[id]
  const { [id]: _removedConversation, ...remainingConversationThreads } = conversationThreadKeys.value
  conversationThreadKeys.value = remainingConversationThreads
  if (threadKey) {
    const { [threadKey]: _removedLoaded, ...remainingLoaded } = loadedConversationsByThreadKey.value
    loadedConversationsByThreadKey.value = remainingLoaded
    setThreadRunning(threadKey, false)
  }
}

const agent = new DifyAgUiAgent(difyConfig.value, 'default', undefined, {
  onConversationIdChange: ({ conversationId, threadId }) => {
    if (typeof window === 'undefined') return
    const threadKey = threadKeyFromThreadId(threadId)
    if (conversationId && threadKey) {
      conversationThreadKeys.value = mapConversationToThreadKey(conversationThreadKeys.value, conversationId, threadKey)
      loadedConversationsByThreadKey.value = loadedConversationByThreadKey(loadedConversationsByThreadKey.value, threadKey, conversationId)
    }
    if (threadKey && threadKey !== activeThreadKey.value) {
      if (conversationId) void refreshConversations()
      return
    }
    currentConversationId.value = conversationId
    if (conversationId) {
      activeView.value = 'conversation'
      saveConversationId(window.localStorage, difyConfig.value, conversationId)
      void refreshConversations()
    } else {
      clearConversationId(window.localStorage, difyConfig.value)
    }
  },
  onRunStatusChange: ({ conversationId, threadId, running }) => {
    const threadKey = threadKeyFromThreadId(threadId)
    if (!threadKey) return
    if (conversationId) {
      conversationThreadKeys.value = mapConversationToThreadKey(conversationThreadKeys.value, conversationId, threadKey)
    }
    setThreadRunning(threadKey, running)
  },
})

function debugMessageSample(messages: any[] = []) {
  return (messages || []).slice(0, 6).map((message: any) => ({
    id: message?.id,
    role: message?.role,
    content: typeof message?.content === 'string' ? message.content.slice(0, 300) : message?.content,
    contentJson: JSON.stringify(message?.content ?? ''),
    activityType: message?.activityType,
    metadata: message?.metadata,
  }))
}

function conversationRequest() {
  return {
    baseUrl: difyConfig.value.baseUrl,
    apiKey: difyConfig.value.apiKey,
    user: difyConfig.value.user,
  }
}

function upsertConversation(next: DifyConversation) {
  const index = conversations.value.findIndex((conversation) => conversation.id === next.id)
  if (index === -1) {
    conversations.value = [next, ...conversations.value]
  } else {
    conversations.value = conversations.value.map((conversation) => conversation.id === next.id ? next : conversation)
  }
}

async function refreshConversations(options: { append?: boolean; restoreLast?: boolean } = {}) {
  const seq = ++conversationLoadSeq
  conversationsError.value = ''
  if (sendDisabledReason.value) {
    conversations.value = []
    conversationsHasMore.value = false
    conversationsLastId.value = ''
    return
  }

  conversationsLoading.value = true
  try {
    const result = await listConversations({
      ...conversationRequest(),
      limit: 20,
      lastId: options.append ? conversationsLastId.value : '',
      sortBy: '-updated_at',
    })
    if (seq !== conversationLoadSeq) return
    conversations.value = options.append
      ? [...conversations.value, ...result.conversations.filter((next) => !conversations.value.some((current) => current.id === next.id))]
      : result.conversations
    conversationsHasMore.value = result.hasMore
    conversationsLastId.value = result.lastId
  } catch (error: any) {
    if (seq !== conversationLoadSeq) return
    conversationsError.value = error?.message || '会话列表加载失败'
  } finally {
    if (seq === conversationLoadSeq) conversationsLoading.value = false
  }
}

function loadMoreConversations() {
  if (!conversationsHasMore.value || conversationsLoading.value) return
  void refreshConversations({ append: true })
}

function handleHome() {
  activeView.value = 'home'
}

function handleNewConversation(_targetAgent?: any, options: { openConversation?: boolean } = {}) {
  const nextThreadKey = createDraftThreadKey()
  registerThreadKey(nextThreadKey)
  activeThreadKey.value = nextThreadKey
  activeView.value = activeViewForNewConversation(options)
  currentConversationId.value = ''
  pendingHistoryLoad.value = null
  historyLoading.value = false
  historyError.value = ''
  if (typeof window !== 'undefined') clearConversationId(window.localStorage, difyConfig.value)
}

async function selectConversation(conversationId: string, _targetAgent?: any) {
  const id = String(conversationId || '').trim()
  if (!id) return
  const seq = ++historyLoadSeq
  const threadKey = threadKeyForConversation(id, conversationThreadKeys.value)
  registerThreadKey(threadKey)
  activeThreadKey.value = threadKey
  currentConversationId.value = id
  activeView.value = 'conversation'
  historyError.value = ''
  if (loadedConversationsByThreadKey.value[threadKey] === id) {
    historyLoading.value = false
    pendingHistoryLoad.value = null
  } else {
    historyLoading.value = true
    pendingHistoryLoad.value = { conversationId: id, threadKey, requestId: seq }
  }
  if (typeof window !== 'undefined') saveConversationId(window.localStorage, difyConfig.value, id)
  copilotDifyDebug('history.select.start', {
    conversationId: id,
    seq,
    activeView: activeView.value,
    currentConversationId: currentConversationId.value,
    chatThreadId: chatThreadId.value,
    threadKey,
    pending: pendingHistoryLoad.value,
    sourceMessages: agent.messages.length,
  })
}

function handleHistoryLoaded(payload: { conversationId: string; threadId: string; requestId: number; result?: any }) {
  const pending = pendingHistoryLoad.value
  if (!pending || pending.requestId !== payload.requestId) return
  const threadKey = threadKeyFromThreadId(payload.threadId) || pending.threadKey
  conversationThreadKeys.value = mapConversationToThreadKey(conversationThreadKeys.value, payload.conversationId, threadKey)
  loadedConversationsByThreadKey.value = loadedConversationByThreadKey(loadedConversationsByThreadKey.value, threadKey, payload.conversationId)
  pendingHistoryLoad.value = null
  historyLoading.value = false
  historyError.value = ''
  copilotDifyDebug('history.select.done', {
    conversationId: payload.conversationId,
    requestId: payload.requestId,
    result: payload.result,
    activeView: activeView.value,
    currentConversationId: currentConversationId.value,
    chatThreadId: chatThreadId.value,
    threadKey,
    sourceMessages: agent.messages.length,
    sourceSample: debugMessageSample(agent.messages as any[]),
  })
}

function handleHistoryLoadFailed(payload: { conversationId: string; threadId: string; requestId: number; message: string }) {
  const pending = pendingHistoryLoad.value
  if (!pending || pending.requestId !== payload.requestId) return
  pendingHistoryLoad.value = null
  historyLoading.value = false
  historyError.value = payload.message || '历史对话加载失败'
}

async function deleteConversationById(conversationId: string) {
  const id = String(conversationId || '').trim()
  if (!id) return
  if (typeof window !== 'undefined' && !window.confirm('删除这个会话？此操作会删除 Dify 中的历史消息。')) return
  conversationsError.value = ''
  try {
    await deleteConversation({ ...conversationRequest(), conversationId: id })
    conversations.value = conversations.value.filter((conversation) => conversation.id !== id)
    removeConversationThreadState(id)
    if (currentConversationId.value === id) {
      const nextThreadKey = createDraftThreadKey()
      registerThreadKey(nextThreadKey)
      activeThreadKey.value = nextThreadKey
      activeView.value = 'home'
      currentConversationId.value = ''
      pendingHistoryLoad.value = null
      historyLoading.value = false
      historyError.value = ''
      if (typeof window !== 'undefined') clearConversationId(window.localStorage, difyConfig.value)
    }
  } catch (error: any) {
    conversationsError.value = error?.message || '会话删除失败'
  }
}

async function renameConversationByRecord(conversation: DifyConversation) {
  if (typeof window === 'undefined') return
  const name = window.prompt('重命名会话', conversation.name || '新会话')?.trim()
  if (!name || name === conversation.name) return
  conversationsError.value = ''
  try {
    const renamed = await renameConversation({
      ...conversationRequest(),
      conversationId: conversation.id,
      name,
    })
    upsertConversation(renamed)
  } catch (error: any) {
    conversationsError.value = error?.message || '会话重命名失败'
  }
}

async function launchWithMessage(text: string, options: LaunchWithMessageOptions = {}) {
  await nextTick()
  return drawerRef.value?.launchWithMessage(text, options) || false
}

watch(
  [activeThreadKey, () => difyConfig.value.user],
  () => registerThreadKey(activeThreadKey.value),
  { immediate: true },
)

watch(
  difyConfig,
  (nextConfig) => {
    agent.updateConfig(nextConfig)
    void refreshConversations({ restoreLast: shouldRestoreLastConversation() })
  },
  { deep: true, immediate: true },
)

defineExpose({
  launchWithMessage,
})
</script>
