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
import { createConversationCoordinator } from '../../lib/conversationCoordinator'
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
const conversationsLoading = ref(false)
const conversationsError = ref('')
const conversationsHasMore = ref(false)
const conversationsLastId = ref('')
const conversations = ref<DifyConversation[]>([])
const conversationSearch = ref('')
const activityRenderers = createCcActivityRenderers()
const titleText = computed(() => props.title || '系统助手')
const resolvedCatalog = computed<AssistantCatalog>(() => resolveAssistantCatalog(props.catalog))
const assistantShellStyle = computed(() => assistantUiStyle(props.ui))
const difyConfig = computed(() => normalizeDifyAssistantConfig(props.dify || {}))
const coordinator = createConversationCoordinator(() => difyConfig.value.user)
const { activeView, currentConversationId, historyLoading, historyError, threadId: chatThreadId,
  pendingHistoryConversationId, pendingHistoryLoadId, runningConversationIds } = coordinator

const floatingDockKey = computed(() => assistantFloatingDockStorageKey(props.storageKeyPrefix))
const sendDisabledReason = computed(() => validateDifyAssistantConfig(difyConfig.value))

provide('difyBaseUrl', computed(() => difyConfig.value.baseUrl))

let conversationLoadSeq = 0

const agent = new DifyAgUiAgent(difyConfig.value, 'default', undefined, {
  onConversationIdChange: (change) => {
    coordinator.conversationChanged(change)
    if (change.conversationId) void refreshConversations()
  },
  onRunStatusChange: coordinator.runStatus,
})

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

async function refreshConversations(options: { append?: boolean } = {}) {
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

function handleHome() { coordinator.showHome() }
function handleNewConversation(_targetAgent?: any, options: { openConversation?: boolean } = {}) {
  coordinator.startNew(options)
}
function selectConversation(conversationId: string) { coordinator.select(conversationId) }
function handleHistoryLoaded(payload: { conversationId: string; threadId: string; requestId: number; result?: any }) {
  coordinator.historyLoaded(payload)
}
function handleHistoryLoadFailed(payload: { conversationId: string; threadId: string; requestId: number; message: string }) {
  coordinator.historyFailed(payload)
}

async function deleteConversationById(conversationId: string) {
  const id = String(conversationId || '').trim()
  if (!id) return
  if (typeof window !== 'undefined' && !window.confirm('删除这个会话？此操作会删除 Dify 中的历史消息。')) return
  conversationsError.value = ''
  try {
    await deleteConversation({ ...conversationRequest(), conversationId: id })
    conversations.value = conversations.value.filter((conversation) => conversation.id !== id)
    coordinator.remove(id)
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

watch(() => difyConfig.value.user, coordinator.registerActiveThread, { immediate: true })

watch(
  difyConfig,
  (nextConfig) => {
    agent.updateConfig(nextConfig)
    void refreshConversations()
  },
  { deep: true, immediate: true },
)

defineExpose({
  launchWithMessage,
})
</script>
