<template>
  <button ref="floatingButtonRef" v-if="!drawerOpen" class="drawer-fab"
    :class="{ 'drawer-fab--dragging': floatingDragActive }" :style="floatingDockStyle" type="button"
    :aria-label="`打开${titleText}`" @click="handleFloatingButtonClick" @pointerdown="handleFloatingPointerDown">
    <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
      <path d="M4 5.5h12" />
      <path d="M4 10h8" />
      <path d="M4 14.5h5" />
      <path d="M14.5 12.5 17 15l-2.5 2.5" />
    </svg>
  </button>

  <div v-if="drawerOpen" class="drawer-backdrop" @click="closeDrawer" />

  <aside ref="drawerElementRef" class="ai-drawer" :class="{ open: drawerOpen }" role="dialog" aria-modal="true"
    :aria-label="`${titleText}抽屉`" tabindex="-1" @keydown="handleDrawerKeydown">
    <header class="drawer-header">
      <div class="drawer-header__title">
        <div>
          <strong>{{ titleText }}</strong>
        </div>
      </div>
      <div class="drawer-header__actions">
        <button type="button" aria-label="关闭抽屉" title="关闭抽屉" @click="closeDrawer">
          <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
            <path d="M5.5 5.5 14.5 14.5" />
            <path d="M14.5 5.5 5.5 14.5" />
          </svg>
        </button>
      </div>
    </header>

    <div class="drawer-layout" :class="{ 'drawer-layout--sidebar-collapsed': sidebarCollapsed }">
      <ConversationSidebar :active-view="activeView" :active-conversation-id="activeConversationId"
        :conversations="conversations" :loading="conversationsLoading" :has-more="conversationsHasMore"
        :search="conversationSearch" :collapsed="sidebarCollapsed" :running-conversation-ids="runningConversationIds"
        @home="emit('home')" @new-conversation="handleNewConversation" @select="handleConversationSelect"
        @delete-conversation="conversationId => emit('deleteConversation', conversationId)"
        @rename-conversation="conversation => emit('renameConversation', conversation)"
        @load-more="emit('loadMoreConversations')" @update:search="value => emit('update:conversationSearch', value)"
        @toggle-collapsed="sidebarCollapsed = !sidebarCollapsed" />

      <main class="drawer-main">
        <div v-if="conversationsError" class="drawer-history-status" role="status" aria-live="polite">
          {{ conversationsError }}
        </div>
        <div v-if="executionNotice && activeView !== 'home'" class="drawer-history-status" role="status" aria-live="polite">
          {{ executionNotice }}
        </div>

        <div v-if="activeView === 'home'" class="drawer-home">
          <div class="drawer-home__content">
            <HomeCatalogPanel :catalog="catalog" compact variant="cards" show-suggested-questions
              @select-skill="skill => selectLauncherSkill(skill, 'drawer')"
              @select-question="question => selectLauncherQuestion(question.message, 'drawer')" />
          </div>
          <div class="drawer-home__bottom">
            <form class="drawer-home-composer" @submit.prevent="handleLauncherSubmit">
              <AssistantComposer ref="drawerHomeComposerRef" v-model="launcherText" :selected-skill="launcherSkill"
                :catalog="catalog" :disabled="isSubmitting" :show-add-button="true" :hint="launcherHint"
                placeholder="直接提问，或选择常用能力" @submit="sendFromHome" @command="sendFromHome"
                @select-skill="skill => selectLauncherSkill(skill, 'drawer')" @clear-skill="launcherSkill = null"
                @add-file="fileInput?.click()" />
              <div v-if="pendingFiles.length" class="launcher-files">
                <span v-for="file in pendingFiles" :key="file.name" class="launcher-file">
                  {{ file.name }}
                  <button type="button" aria-label="移除文件" @click="removePendingFile(file.name)">
                    <svg viewBox="0 0 16 16" fill="none" focusable="false" aria-hidden="true">
                      <path d="M4.5 4.5 11.5 11.5" />
                      <path d="M11.5 4.5 4.5 11.5" />
                    </svg>
                  </button>
                </span>
              </div>
              <span v-if="submitError" class="launcher-error">{{ submitError }}</span>
            </form>
          </div>
        </div>

        <div v-else ref="chatWrapRef" class="drawer-chat-wrap">
          <div v-if="historyLoading || historyError" class="drawer-history-status" role="status" aria-live="polite">
            <span v-if="historyLoading" class="drawer-history-spinner" aria-hidden="true" />
            <span>{{ historyLoading ? '正在加载历史对话' : historyError }}</span>
          </div>

          <CopilotChat agent-id="default" class="drawer-chat" :welcome-screen="false" :attachments="chatAttachments"
            :input-value="chatInputValue" @input-change="value => chatInputValue = value">
            <template #message-view="slotProps">
              <RunProcessMessageView :messages="slotProps.messages" :is-running="slotProps.isRunning"
                :interrupt-state="interruptSlotProps" @ui-intent="handleStructuredIntent" />
            </template>

            <template #input="slotProps">
              <AssistantComposer ref="chatComposerRef" :model-value="slotProps.modelValue"
                :selected-skill="chatInputSkill" :catalog="catalog"
                :disabled="Boolean(disabledReason) || slotProps.inputMode !== 'input'" :is-running="slotProps.isRunning"
                :show-add-button="true" :hint="chatHint" placeholder="直接提问，或选择常用能力"
                @update:model-value="slotProps.onUpdateModelValue"
                @submit="value => submitChatComposer(value, slotProps)"
                @command="value => submitChatComposer(value, slotProps)"
                @select-skill="skill => selectChatSkill(skill, slotProps)" @clear-skill="chatInputSkill = null"
                @add-file="slotProps.onAddFile" @stop="() => stopChatRun(slotProps)" />
            </template>
          </CopilotChat>
        </div>
      </main>
    </div>
    <input ref="fileInput" class="launcher-file-input" type="file" multiple aria-label="选择附件" tabindex="-1"
      @change="handleFileSelect" />
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { CopilotChat, useAgent, useCopilotKit, useDefaultRenderTool, useInterrupt, useRenderTool } from '@copilotkit/vue/v2'
import { z } from 'zod'
import AssistantComposer from '../chat/AssistantComposer.vue'
import ConversationSidebar from '../conversation/ConversationSidebar.vue'
import HomeCatalogPanel from '../conversation/HomeCatalogPanel.vue'
import RunProcessMessageView from '../chat/RunProcessMessageView.vue'
import DefaultToolCallCard from '../tool-cards/DefaultToolCallCard.vue'
import ReadFileToolCard from '../tool-cards/ReadFileToolCard.vue'
import SearchToolCard from '../tool-cards/SearchToolCard.vue'
import WriteFileToolCard from '../tool-cards/WriteFileToolCard.vue'
import { buildDifyAttachmentUploadResult } from '../../lib/difyAttachments'
import { copilotDifyDebug } from '../../lib/debugLog'
import { loadPendingHistory, waitForVisibleAgent } from '../../lib/conversationCoordinator'
import type { AssistantCatalog, AssistantSkill } from '../../lib/assistantCatalog'
import { defaultAssistantCatalog } from '../../lib/assistantCatalog'
import type { DifyConversation } from '../../lib/difyTransport'
import type { LaunchWithMessageOptions } from '../../lib/assistantLauncher'
import {
  defaultFloatingDock,
  floatingDockStorageKey as defaultFloatingDockStorageKey,
  floatingDockFromPointer,
  isFloatingDockDrag,
  loadFloatingDock,
  saveFloatingDock,
  type FloatingDockPoint,
} from '../../lib/floatingDock'
import { submitLauncherMessage } from '../../lib/homeLauncher'
import { normalizeInterruptQuestion } from '../../lib/question'
import { isChatNearBottom } from '../../lib/conversationView'

const props = defineProps<{
  catalog?: AssistantCatalog
  title?: string
  activeView: 'home' | 'conversation'
  activeConversationId?: string
  conversations: DifyConversation[]
  conversationsLoading?: boolean
  conversationsError?: string
  conversationsHasMore?: boolean
  conversationSearch?: string
  disabledReason?: string
  historyLoading?: boolean
  historyError?: string
  expectedThreadId?: string
  pendingHistoryConversationId?: string
  pendingHistoryLoadId?: number
  defaultSidebarCollapsed?: boolean
  runningConversationIds?: string[]
  floatingDockStorageKey?: string
}>()

const emit = defineEmits<{
  home: []
  newConversation: [agent?: unknown, options?: { openConversation?: boolean }]
  selectConversation: [conversationId: string, agent?: unknown]
  deleteConversation: [conversationId: string]
  renameConversation: [conversation: DifyConversation]
  loadMoreConversations: []
  conversationUpdated: []
  historyLoaded: [payload: { conversationId: string; threadId: string; requestId: number; result?: any }]
  historyLoadFailed: [payload: { conversationId: string; threadId: string; requestId: number; message: string }]
  'update:conversationSearch': [value: string]
}>()

const drawerOpen = ref(false)
const sidebarCollapsed = ref(props.defaultSidebarCollapsed ?? true)
const launcherText = ref('')
const launcherSkill = ref<AssistantSkill | null>(null)
const chatInputValue = ref('')
const chatInputSkill = ref<AssistantSkill | null>(null)
const drawerHomeComposerRef = ref<{ focus: () => void } | null>(null)
const chatComposerRef = ref<{ focus: () => void } | null>(null)
const isSubmitting = ref(false)
const inlineIntentRunning = ref(false)
const submitError = ref('')
const floatingButtonRef = ref<HTMLButtonElement | null>(null)
const drawerElementRef = ref<HTMLElement | null>(null)
const chatWrapRef = ref<HTMLElement | null>(null)
const showJumpToLatest = ref(false)
const isChatFollowingLatest = ref(true)
const pendingFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const { agent } = useAgent({ agentId: 'default' })
const { copilotkit } = useCopilotKit()
const agentRecoveryState = ref<Record<string, any>>({})
watch(agent, (current, _previous, onCleanup) => {
  agentRecoveryState.value = current?.state || {}
  const subscription = current?.subscribe?.({ onStateChanged: ({ state }) => {
    agentRecoveryState.value = state || {}
  } })
  onCleanup(() => subscription?.unsubscribe())
}, { immediate: true })
const executionNotice = computed(() => agentRecoveryState.value.execution?.message ||
  (agentRecoveryState.value.recoveryAvailable === false ? '历史已加载，待处理交互状态暂时无法读取。' : ''))

const catalog = computed(() => props.catalog || defaultAssistantCatalog)
const titleText = computed(() => props.title || '系统助手')
const disabledReason = computed(() => props.disabledReason || '')
const historyLoading = computed(() => Boolean(props.historyLoading))
const historyError = computed(() => props.historyError || '')
const conversationsLoading = computed(() => Boolean(props.conversationsLoading))
const conversationsError = computed(() => props.conversationsError || '')
const conversationsHasMore = computed(() => Boolean(props.conversationsHasMore))
const conversations = computed(() => props.conversations || [])
const activeView = computed(() => props.activeView || 'home')
const activeConversationId = computed(() => props.activeConversationId || '')
const conversationSearch = computed(() => props.conversationSearch || '')
const expectedThreadId = computed(() => props.expectedThreadId || '')
const pendingHistoryConversationId = computed(() => props.pendingHistoryConversationId || '')
const pendingHistoryLoadId = computed(() => Number(props.pendingHistoryLoadId || 0))
const runningConversationIds = computed(() => props.runningConversationIds || [])
const launcherHint = computed(() => '')
const chatHint = computed(() => '')
const floatingDock = ref(defaultFloatingDock(0))
const floatingDragActive = ref(false)
const suppressFloatingClick = ref(false)
const floatingPointerStart = ref<FloatingDockPoint | null>(null)
const floatingStorageKey = computed(() => props.floatingDockStorageKey || defaultFloatingDockStorageKey())
const floatingDockStyle = computed(() => ({
  top: `${floatingDock.value.y}px`,
  bottom: 'auto',
  left: floatingDock.value.side === 'left' ? '16px' : 'auto',
  right: floatingDock.value.side === 'right' ? '16px' : 'auto',
}))

let lastFocusedElement: HTMLElement | null = null
let previousBodyOverflow = ''
let chatScrollElement: HTMLElement | null = null
let chatMutationObserver: MutationObserver | null = null
let chatScrollFrame = 0


watch(
  () => ({
    activeView: activeView.value,
    activeConversationId: activeConversationId.value,
    historyLoading: historyLoading.value,
    messageCount: Array.isArray((agent.value as any)?.messages) ? (agent.value as any).messages.length : -1,
  }),
  () => {
    const currentAgent = agent.value as any
    const messages = Array.isArray(currentAgent?.messages) ? currentAgent.messages : []
    copilotDifyDebug('drawer.visible-agent.messages', {
      activeView: activeView.value,
      activeConversationId: activeConversationId.value,
      historyLoading: historyLoading.value,
      threadId: currentAgent?.threadId,
      agentId: currentAgent?.id || currentAgent?.agentId,
      messageCount: messages.length,
    })
  },
  { deep: true },
)

onMounted(() => {
  floatingDock.value = loadFloatingDock(
    typeof window === 'undefined' ? null : window.localStorage,
    floatingStorageKey.value,
    typeof window === 'undefined' ? 0 : window.innerHeight,
  )
  if (activeView.value === 'conversation') {
    void connectChatScroll(true)
  }
})

onUnmounted(() => {
  removeFloatingDragListeners()
  disconnectChatScroll()
  restoreBodyScroll()
})

const chatAttachments = computed(() => ({
  enabled: !Boolean(disabledReason.value),
  accept: '*/*',
  onUpload: uploadChatAttachment,
  onUploadFailed: (error: any) => {
    submitError.value = error?.message || 'File upload failed'
  },
}))

async function visibleAgentForEmit() {
  return waitForVisibleAgent(() => agent.value as any, () => expectedThreadId.value, nextTick)
}

function openDrawer() {
  if (!drawerOpen.value && typeof document !== 'undefined') {
    lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  drawerOpen.value = true
  void nextTick(() => drawerElementRef.value?.focus({ preventScroll: true }))
}

function closeDrawer() {
  if (!drawerOpen.value) return
  drawerOpen.value = false
  restoreBodyScroll()
  const target = lastFocusedElement?.isConnected ? lastFocusedElement : floatingButtonRef.value
  lastFocusedElement = null
  void nextTick(() => target?.focus({ preventScroll: true }))
}

function restoreBodyScroll() {
  if (typeof document === 'undefined') return
  document.body.style.overflow = previousBodyOverflow
}

function handleDrawerKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeDrawer()
    return
  }
  if (event.key !== 'Tab') return
  const focusable = drawerFocusableElements()
  if (!focusable.length) {
    event.preventDefault()
    drawerElementRef.value?.focus({ preventScroll: true })
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement
  if (event.shiftKey && (active === first || active === drawerElementRef.value)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

function drawerFocusableElements() {
  const drawer = drawerElementRef.value
  if (!drawer || typeof window === 'undefined') return []
  return Array.from(drawer.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]):not([tabindex="-1"]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => element.getClientRects().length > 0)
}

function chatScrollMetrics(element: HTMLElement) {
  return { scrollTop: element.scrollTop, scrollHeight: element.scrollHeight, clientHeight: element.clientHeight }
}

function updateChatFollowState() {
  if (!chatScrollElement) {
    showJumpToLatest.value = false
    return
  }
  const nearBottom = isChatNearBottom(chatScrollMetrics(chatScrollElement))
  isChatFollowingLatest.value = nearBottom
  showJumpToLatest.value = !nearBottom && chatScrollElement.scrollHeight > chatScrollElement.clientHeight
}

function handleChatScroll() {
  updateChatFollowState()
}

function scrollToLatest(smooth = false) {
  if (!chatScrollElement || typeof window === 'undefined') return
  isChatFollowingLatest.value = true
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  chatScrollElement.scrollTo({
    top: chatScrollElement.scrollHeight,
    behavior: smooth && !reducedMotion ? 'smooth' : 'auto',
  })
  showJumpToLatest.value = false
}

function scheduleScrollToLatest(force = false) {
  if (force) isChatFollowingLatest.value = true
  if (!isChatFollowingLatest.value || typeof window === 'undefined') return
  if (chatScrollFrame) window.cancelAnimationFrame(chatScrollFrame)
  chatScrollFrame = window.requestAnimationFrame(() => {
    chatScrollFrame = 0
    scrollToLatest(false)
  })
}

async function connectChatScroll(forceLatest = false) {
  if (typeof window === 'undefined') return
  await nextTick()
  window.requestAnimationFrame(() => {
    const nextElement = chatWrapRef.value?.querySelector<HTMLElement>('[data-testid="copilot-chat-view-scroll"]') || null
    if (!nextElement) return
    if (chatScrollElement !== nextElement) {
      disconnectChatScroll()
      chatScrollElement = nextElement
      chatScrollElement.addEventListener('scroll', handleChatScroll, { passive: true })
      chatMutationObserver = new MutationObserver(() => {
        if (isChatFollowingLatest.value) scheduleScrollToLatest()
        else updateChatFollowState()
      })
      chatMutationObserver.observe(chatScrollElement, { childList: true, subtree: true, characterData: true })
    }
    if (forceLatest) scrollToLatest(false)
    else updateChatFollowState()
  })
}

function disconnectChatScroll() {
  if (chatScrollFrame && typeof window !== 'undefined') {
    window.cancelAnimationFrame(chatScrollFrame)
    chatScrollFrame = 0
  }
  chatMutationObserver?.disconnect()
  chatMutationObserver = null
  chatScrollElement?.removeEventListener('scroll', handleChatScroll)
  chatScrollElement = null
  showJumpToLatest.value = false
}

watch(
  () => [drawerOpen.value, activeView.value, activeConversationId.value, historyLoading.value] as const,
  ([open, view]) => {
    if (!open || view !== 'conversation') {
      disconnectChatScroll()
      return
    }
    isChatFollowingLatest.value = true
    void connectChatScroll(true)
  },
)


let handledHistoryLoadKey = ''
watch(
  () => ({
    activeView: activeView.value,
    conversationId: pendingHistoryConversationId.value,
    requestId: pendingHistoryLoadId.value,
    threadId: expectedThreadId.value,
  }),
  async (pending) => {
    if (pending.activeView !== 'conversation' || !pending.conversationId || !pending.requestId) return
    const loadKey = `${pending.requestId}:${pending.conversationId}:${pending.threadId}`
    if (handledHistoryLoadKey === loadKey) return
    handledHistoryLoadKey = loadKey
    const targetThreadId = pending.threadId
    try {
      const ticket = { conversationId: pending.conversationId, requestId: pending.requestId, threadId: targetThreadId }
      const loaded = await loadPendingHistory(ticket, () =>
        activeView.value === 'conversation' && pendingHistoryConversationId.value && pendingHistoryLoadId.value
          ? { conversationId: pendingHistoryConversationId.value, requestId: pendingHistoryLoadId.value, threadId: expectedThreadId.value }
          : null, visibleAgentForEmit)
      if (loaded) emit('historyLoaded', { ...ticket, result: loaded.result })
    } catch (error: any) {
      emit('historyLoadFailed', {
        conversationId: pending.conversationId,
        threadId: targetThreadId,
        requestId: pending.requestId,
        message: error?.message || '历史对话加载失败',
      })
    }
  },
  { immediate: true },
)

async function prepareFreshConversation() {
  openDrawer()
  emit('newConversation', undefined, { openConversation: true })
  chatInputValue.value = ''
  chatInputSkill.value = null
  await nextTick()
  return visibleAgentForEmit()
}

async function handleConversationSelect(conversationId: string) {
  chatInputValue.value = ''
  chatInputSkill.value = null
  emit('selectConversation', conversationId)
}

async function handleNewConversation() {
  chatInputValue.value = ''
  chatInputSkill.value = null
  emit('newConversation')
  await focusHomeInputSoon()
}

useDefaultRenderTool({
  render: DefaultToolCallCard as any,
})
useRenderTool({
  name: 'read_file',
  parameters: z.any(),
  render: ReadFileToolCard as any,
})
useRenderTool({
  name: 'write_file',
  parameters: z.any(),
  render: WriteFileToolCard as any,
})
useRenderTool({
  name: 'search',
  parameters: z.any(),
  render: SearchToolCard as any,
})

const interruptState = useInterrupt({
  agentId: 'default',
  renderInChat: false,
  handler: ({ event }) => normalizeInterruptQuestion(event.value),
})
const interruptSlotProps = computed(() => {
  const question = agentRecoveryState.value.recovery?.question
  const live = interruptState.slotProps.value
  if (!question) return agentRecoveryState.value.recoveryAvailable !== undefined ||
    agentRecoveryState.value.execution ? null : live
  if (live?.result?.id === question.id) return live
  return {
    result: normalizeInterruptQuestion(question),
    resolve: (payload: unknown) => {
      const current = agent.value
      if (!current || current.isRunning) return
      void copilotkit.value.runAgent({ agent: current,
        forwardedProps: { command: { resume: payload, interruptEvent: question } },
      }).catch(() => { submitError.value = '本轮交互未能继续，请重新加载会话后重试。' })
    },
  }
})

function selectLauncherSkill(skill: AssistantSkill, source: 'drawer' = 'drawer') {
  launcherSkill.value = skill
  launcherText.value = ''
  void nextTick(() => {
    if (source === 'drawer') drawerHomeComposerRef.value?.focus()
  })
}

function selectLauncherQuestion(message: string, source: 'drawer' = 'drawer') {
  launcherSkill.value = null
  launcherText.value = message
  void nextTick(() => {
    if (source === 'drawer') drawerHomeComposerRef.value?.focus()
  })
}

function selectChatSkill(skill: AssistantSkill, slotProps: any) {
  chatInputSkill.value = skill
  slotProps.onUpdateModelValue('')
  chatInputValue.value = ''
  void nextTick(() => chatComposerRef.value?.focus())
}

async function sendFromHome(text: string) {
  submitError.value = ''
  isSubmitting.value = true
  try {
    const files = await uploadPendingFiles()
    const submitted = await submitLauncherMessage({
      text,
      selectedSkill: launcherSkill.value,
      agent: agent.value,
      runAgent: ({ agent: currentAgent }) => copilotkit.value.runAgent({ agent: currentAgent }),
      openDrawer,
      disabledReason: disabledReason.value,
      files,
      prepareConversation: prepareFreshConversation,
    })
    if (submitted) {
      launcherText.value = ''
      launcherSkill.value = null
      pendingFiles.value = []
      emit('conversationUpdated')
      scheduleScrollToLatest(true)
    } else if (disabledReason.value) {
      scheduleScrollToLatest(true)
    }
  } catch (error: any) {
    submitError.value = error?.message || '发送失败'
  } finally {
    isSubmitting.value = false
  }
}

function handleLauncherSubmit() {
  void sendFromHome(launcherText.value)
}

function submitChatComposer(value: string, slotProps: any) {
  if (!value.trim()) return
  chatInputSkill.value = null
  chatInputValue.value = ''
  slotProps.onSubmitMessage(value)
  scheduleScrollToLatest(true)
}

function stopChatRun(slotProps: any) {
  const currentAgent = agent.value as any
  currentAgent?.abortRun?.()
  slotProps.onStop?.()
}

async function handleStructuredIntent(value: string) {
  const text = String(value || '').trim()
  if (!text || inlineIntentRunning.value || disabledReason.value) return
  inlineIntentRunning.value = true
  submitError.value = ''
  try {
    const currentAgent = await visibleAgentForEmit()
    if (!currentAgent) return
    currentAgent?.addMessage?.({
      id: globalThis.crypto?.randomUUID?.() || `structured-intent-${Date.now()}`,
      role: 'user',
      content: text,
    })
    await copilotkit.value.runAgent({ agent: currentAgent })
    emit('conversationUpdated')
    scheduleScrollToLatest(true)
  } catch (error: any) {
    submitError.value = error?.message || '发送失败'
  } finally {
    inlineIntentRunning.value = false
  }
}

async function focusHomeInputSoon() {
  openDrawer()
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await nextTick()
    if (drawerHomeComposerRef.value) {
      drawerHomeComposerRef.value.focus()
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 16))
  }
}

async function launchWithMessage(text: string, options: LaunchWithMessageOptions = {}) {
  submitError.value = ''
  isSubmitting.value = true
  try {
    const files = await uploadLaunchFiles(options.files || [])
    const submitted = await submitLauncherMessage({
      text,
      selectedSkill: options.selectedSkill || null,
      agent: agent.value,
      runAgent: ({ agent: currentAgent }) => copilotkit.value.runAgent({ agent: currentAgent }),
      openDrawer,
      disabledReason: disabledReason.value,
      files,
      prepareConversation: prepareFreshConversation,
    })
    if (submitted) {
      launcherText.value = ''
      launcherSkill.value = null
      pendingFiles.value = []
      emit('conversationUpdated')
    } else if (disabledReason.value) {
      submitError.value = disabledReason.value
    }
    return submitted
  } catch (error: any) {
    submitError.value = error?.message || '发送失败'
    return false
  } finally {
    isSubmitting.value = false
  }
}

function handleFloatingButtonClick() {
  if (suppressFloatingClick.value) {
    suppressFloatingClick.value = false
    return
  }
  openDrawer()
}

function handleFloatingPointerDown(event: PointerEvent) {
  if (event.button !== 0 || typeof window === 'undefined') return
  floatingPointerStart.value = { x: event.clientX, y: event.clientY }
  floatingDragActive.value = false
  window.addEventListener('pointermove', handleFloatingPointerMove)
  window.addEventListener('pointerup', handleFloatingPointerUp, { once: true })
}

function handleFloatingPointerMove(event: PointerEvent) {
  const start = floatingPointerStart.value
  if (!start || typeof window === 'undefined') return
  const current = { x: event.clientX, y: event.clientY }
  if (!floatingDragActive.value && !isFloatingDockDrag(start, current)) return
  floatingDragActive.value = true
  floatingDock.value = floatingDockFromPointer({
    x: event.clientX,
    y: event.clientY,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
  })
  event.preventDefault()
}

function handleFloatingPointerUp(event: PointerEvent) {
  if (floatingDragActive.value && typeof window !== 'undefined') {
    suppressFloatingClick.value = true
    saveFloatingDock(window.localStorage, floatingStorageKey.value, floatingDock.value, window.innerHeight)
    event.preventDefault()
    window.setTimeout(() => {
      suppressFloatingClick.value = false
    }, 0)
  }
  floatingPointerStart.value = null
  floatingDragActive.value = false
  removeFloatingDragListeners()
}

function removeFloatingDragListeners() {
  if (typeof window === 'undefined') return
  window.removeEventListener('pointermove', handleFloatingPointerMove)
  window.removeEventListener('pointerup', handleFloatingPointerUp)
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || [])
  const filesByName = new Map(pendingFiles.value.map((file) => [file.name, file]))
  for (const file of selected) filesByName.set(file.name, file)
  pendingFiles.value = Array.from(filesByName.values())
  input.value = ''
}

function removePendingFile(name: string) {
  pendingFiles.value = pendingFiles.value.filter((file) => file.name !== name)
}

async function uploadPendingFiles() {
  if (!pendingFiles.value.length) return []
  const currentAgent = agent.value as any
  if (!currentAgent?.uploadFile) throw new Error('当前 Agent 不支持文件上传')
  return Promise.all(pendingFiles.value.map((file) => currentAgent.uploadFile(file)))
}

async function uploadLaunchFiles(files: any[]) {
  if (!files.length) return []
  const currentAgent = agent.value as any
  return Promise.all(files.map((file) => {
    if (file && typeof file === 'object' && 'id' in file) return file
    if (!currentAgent?.uploadFile) throw new Error('当前 Agent 不支持文件上传')
    return currentAgent.uploadFile(file)
  }))
}

async function uploadChatAttachment(file: File) {
  return buildDifyAttachmentUploadResult(agent.value as any, file)
}

defineExpose({
  openDrawer,
  closeDrawer,
  prepareFreshConversation,
  launchWithMessage,
})
</script>
