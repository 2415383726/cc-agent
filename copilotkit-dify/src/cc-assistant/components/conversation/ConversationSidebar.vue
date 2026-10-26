<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { filterConversations, groupConversationsByDate, selectRecentConversations } from '../../lib/conversationView'
import type { DifyConversation } from '../../lib/difyTransport'

const props = defineProps<{
  activeView: 'home' | 'conversation'
  activeConversationId?: string
  conversations: DifyConversation[]
  loading?: boolean
  hasMore?: boolean
  search?: string
  collapsed?: boolean
  runningConversationIds?: string[]
}>()

const emit = defineEmits<{
  home: []
  'new-conversation': []
  select: [conversationId: string]
  'delete-conversation': [conversationId: string]
  'rename-conversation': [conversation: DifyConversation]
  'load-more': []
  'update:search': [value: string]
  'toggle-collapsed': []
}>()

const filteredConversations = computed(() => {
  return filterConversations(props.conversations || [], props.search || '')
})
const groupedConversations = computed(() => groupConversationsByDate(filteredConversations.value))
const recentConversations = computed(() => selectRecentConversations(filteredConversations.value))
const runningConversationIdSet = computed(() => new Set(props.runningConversationIds || []))
const openMenuId = ref('')
const searchPopoverOpen = ref(false)
const recentPopoverOpen = ref(false)

function formatTime(timestamp: number) {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function requestDelete(conversationId: string) {
  openMenuId.value = ''
  emit('delete-conversation', conversationId)
}

function requestRename(conversation: DifyConversation) {
  openMenuId.value = ''
  emit('rename-conversation', conversation)
}

function toggleMenu(conversationId: string) {
  openMenuId.value = openMenuId.value === conversationId ? '' : conversationId
}

function closeMenu() {
  openMenuId.value = ''
}

function closeCollapsedPopovers() {
  searchPopoverOpen.value = false
  recentPopoverOpen.value = false
}

function handleDocumentPointerDown() {
  closeMenu()
  closeCollapsedPopovers()
}

function handleDocumentKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  closeMenu()
  closeCollapsedPopovers()
}

function toggleSearchPopover() {
  searchPopoverOpen.value = !searchPopoverOpen.value
  if (searchPopoverOpen.value) recentPopoverOpen.value = false
}

function toggleRecentPopover() {
  recentPopoverOpen.value = !recentPopoverOpen.value
  if (recentPopoverOpen.value) searchPopoverOpen.value = false
}

function selectFromCollapsed(conversationId: string) {
  closeCollapsedPopovers()
  emit('select', conversationId)
}

function isRunningConversation(conversationId: string) {
  return runningConversationIdSet.value.has(conversationId)
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>

<template>
  <nav
    class="conversation-sidebar"
    :class="{ 'conversation-sidebar--collapsed': collapsed }"
    aria-label="咨询记录导航"
  >
    <template v-if="collapsed">
      <div class="conversation-sidebar__rail" @pointerdown.stop>
        <button
          type="button"
          class="conversation-sidebar__rail-button"
          aria-label="打开侧边栏"
          title="打开侧边栏"
          @click="emit('toggle-collapsed')"
        >
          <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
            <rect x="3.5" y="4" width="13" height="12" rx="2" />
            <path d="M8 4v12" />
          </svg>
        </button>

        <button
          type="button"
          class="conversation-sidebar__rail-button"
          aria-label="新聊天"
          title="新聊天"
          @click="emit('new-conversation')"
        >
          <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
            <path d="M10 4.5v11" />
            <path d="M4.5 10h11" />
          </svg>
        </button>

        <div class="conversation-sidebar__rail-popover-wrap">
          <button
            type="button"
            class="conversation-sidebar__rail-button"
            :class="{ active: searchPopoverOpen }"
            aria-label="搜索聊天"
            title="搜索聊天"
            :aria-expanded="searchPopoverOpen"
            @click="toggleSearchPopover"
          >
            <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
              <circle cx="9" cy="9" r="4.5" />
              <path d="m12.5 12.5 3 3" />
            </svg>
          </button>
          <div
            v-if="searchPopoverOpen"
            class="conversation-sidebar__rail-popover conversation-sidebar__rail-popover--search"
            @pointerdown.stop
          >
            <label class="conversation-sidebar__search">
              <span class="conversation-sidebar__search-icon" aria-hidden="true">
                <svg viewBox="0 0 20 20" fill="none" focusable="false">
                  <circle cx="9" cy="9" r="4.5" />
                  <path d="m12.5 12.5 3 3" />
                </svg>
              </span>
              <input
                name="collapsed-conversation-search"
                aria-label="搜索聊天"
                autocomplete="off"
                :value="search"
                placeholder="搜索聊天"
                @input="emit('update:search', ($event.target as HTMLInputElement).value)"
              />
            </label>
            <div class="conversation-sidebar__rail-results">
              <button
                v-for="conversation in recentConversations"
                :key="conversation.id"
                type="button"
                class="conversation-sidebar__rail-result"
                @click="selectFromCollapsed(conversation.id)"
              >
                <span>{{ conversation.name || '新聊天' }}</span>
                <span
                  v-if="isRunningConversation(conversation.id)"
                  class="conversation-sidebar__running-spinner conversation-sidebar__running-spinner--rail"
                  role="status"
                  aria-label="正在回复"
                />
                <small>{{ formatTime(conversation.updatedAt) }}</small>
              </button>
              <div v-if="!recentConversations.length" class="conversation-sidebar__rail-empty">
                {{ search ? '没有匹配的聊天' : '输入关键词搜索聊天' }}
              </div>
            </div>
          </div>
        </div>

        <div class="conversation-sidebar__rail-popover-wrap">
          <button
            type="button"
            class="conversation-sidebar__rail-button"
            :class="{ active: recentPopoverOpen }"
            aria-label="最近聊天"
            title="最近聊天"
            :aria-expanded="recentPopoverOpen"
            @click="toggleRecentPopover"
          >
            <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
              <path d="M5 5.5h10" />
              <path d="M5 10h8" />
              <path d="M5 14.5h6" />
            </svg>
          </button>
          <div v-if="recentPopoverOpen" class="conversation-sidebar__rail-popover" @pointerdown.stop>
            <h3>最近聊天</h3>
            <div class="conversation-sidebar__rail-results">
              <button
                v-for="conversation in recentConversations"
                :key="conversation.id"
                type="button"
                class="conversation-sidebar__rail-result"
                @click="selectFromCollapsed(conversation.id)"
              >
                <span>{{ conversation.name || '新聊天' }}</span>
                <span
                  v-if="isRunningConversation(conversation.id)"
                  class="conversation-sidebar__running-spinner conversation-sidebar__running-spinner--rail"
                  role="status"
                  aria-label="正在回复"
                />
                <small>{{ formatTime(conversation.updatedAt) }}</small>
              </button>
              <div v-if="loading && !recentConversations.length" class="conversation-sidebar__rail-empty">
                正在加载聊天…
              </div>
              <div v-else-if="!recentConversations.length" class="conversation-sidebar__rail-empty">
                暂无聊天
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="conversation-sidebar__brand">
        <div>
          <strong>聊天记录</strong>
          <span>按时间查看历史咨询</span>
        </div>
        <button
          type="button"
          class="conversation-sidebar__collapse-button"
          aria-label="折叠侧边栏"
          title="折叠侧边栏"
          @click="emit('toggle-collapsed')"
        >
          <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
            <rect x="3.5" y="4" width="13" height="12" rx="2" />
            <path d="M8 4v12" />
          </svg>
        </button>
      </div>

      <div class="conversation-sidebar__primary">
        <button
          type="button"
          class="conversation-sidebar__new-button"
          @click="emit('new-conversation')"
        >
          <span class="conversation-sidebar__nav-icon" aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="none" focusable="false">
              <path d="M10 4.5v11" />
              <path d="M4.5 10h11" />
            </svg>
          </span>
          <span>新聊天</span>
        </button>
      </div>

      <label class="conversation-sidebar__search">
        <span class="conversation-sidebar__search-icon" aria-hidden="true">
          <svg viewBox="0 0 20 20" fill="none" focusable="false">
            <circle cx="9" cy="9" r="4.5" />
            <path d="m12.5 12.5 3 3" />
          </svg>
        </span>
        <input
          name="conversation-search"
          aria-label="搜索聊天"
          autocomplete="off"
          :value="search"
          placeholder="搜索聊天"
          @input="emit('update:search', ($event.target as HTMLInputElement).value)"
        />
      </label>

      <div class="conversation-sidebar__list">
        <div v-if="loading && conversations.length === 0" class="conversation-sidebar__status">
          正在加载聊天…
        </div>
        <div v-else-if="groupedConversations.length === 0" class="conversation-sidebar__status">
          暂无聊天
        </div>

        <section
          v-for="group in groupedConversations"
          :key="group.id"
          class="conversation-sidebar__group"
        >
          <h3>{{ group.label }}</h3>
          <div class="conversation-sidebar__items">
            <div
              v-for="conversation in group.conversations"
              :key="conversation.id"
              class="conversation-sidebar__item"
              :class="{ active: activeView === 'conversation' && activeConversationId === conversation.id }"
            >
              <button
                type="button"
                class="conversation-sidebar__item-main"
                @click="emit('select', conversation.id)"
              >
                <span class="conversation-sidebar__item-title">{{ conversation.name || '新聊天' }}</span>
                <span class="conversation-sidebar__item-meta">{{ formatTime(conversation.updatedAt) }}</span>
              </button>
              <span
                v-if="isRunningConversation(conversation.id)"
                class="conversation-sidebar__running-spinner"
                role="status"
                aria-label="正在回复"
              />
              <div class="conversation-sidebar__menu" @pointerdown.stop>
                <button
                  type="button"
                  class="conversation-sidebar__menu-button"
                  aria-label="聊天记录更多操作"
                  :aria-expanded="openMenuId === conversation.id"
                  @click.stop="toggleMenu(conversation.id)"
                >
                  <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
                    <circle cx="5" cy="10" r="1" />
                    <circle cx="10" cy="10" r="1" />
                    <circle cx="15" cy="10" r="1" />
                  </svg>
                </button>
                <div v-if="openMenuId === conversation.id" class="conversation-sidebar__menu-popover">
                  <button type="button" @click.stop.prevent="requestRename(conversation)">重命名</button>
                  <button type="button" class="danger" @click.stop.prevent="requestDelete(conversation.id)">删除</button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <button
        v-if="hasMore"
        type="button"
        class="conversation-sidebar__load-more"
        :disabled="loading"
        @click="emit('load-more')"
      >
        {{ loading ? '加载中…' : '加载更多' }}
      </button>
    </template>
  </nav>
</template>
