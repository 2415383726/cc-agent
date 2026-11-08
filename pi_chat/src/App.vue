<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { DifyController } from './dify/controller'
import { defaultConfig, saveSessionCredentials } from './dify/config'
import type { SessionCredentials } from './dify/config'
/* toolStatusText/statusText 不再由本壳引用：状态文案由各卡片与 timeline 组件经 projection 取得。 */
import AppShell from './shell/AppShell.vue'
import SidebarRail from './shell/SidebarRail.vue'
import ConversationColumn from './shell/ConversationColumn.vue'
import ComposerBar from './shell/ComposerBar.vue'
import ConnectionForm from './shell/ConnectionForm.vue'
import LiveConversation from './shell/LiveConversation.vue'
import { ScrollFollow, scrollMetrics } from './timeline/scrollFollow'
import { railItems as deriveRailItems, type TurnRailItem } from './timeline/rail'
import type { FileRef } from './projection/transcript'

/*
 * Binding seam: the controller is framework-agnostic pure TS. This shell is the
 * only Vue-aware layer — it wraps the controller in reactive() and reads
 * view/ui as plain data. 时间线条目由 LiveConversation 内的共享 TranscriptView
 * 渲染；问卷/审批回调经 controller 的 inputs.interaction 通道。自动吸底：
 * 读者未向上滚离底部时，新内容保持贴底（timeline/scrollFollow.ts，上游
 * use-scroll-follow 的 best-effort 平移）。
 */
const config = defaultConfig()
const live = reactive(new DifyController(config)) as DifyController
/* 会话凭据保存过就直接续连；否则连接表单常显（showForm）。 */
if (config.apiKey) void live.refreshConversations()

const liveDraft = ref('')
/* 票 08：连接表单收尾——未连接时常显，连接成功收起，「连接设置」可再展开。 */
const formOpen = ref(false)
const showForm = computed(() => !live.ui.connected || formOpen.value)

const liveTitle = computed(() => {
  if (!live.ui.conversationId) return '新会话'
  const found = live.ui.conversations.find((item) => item.id === live.ui.conversationId)
  return found?.name || '当前会话'
})

const liveInteractive = computed(() => Boolean(live.ui.connected) && !live.ui.running)

async function onConnect(credentials: SessionCredentials): Promise<void> {
  live.updateConfig({ ...credentials })
  saveSessionCredentials({ ...credentials })
  await live.refreshConversations()
  // 连接失败（列表刷新报错）时表单保持展开显示重试提示；成功即收起。
  formOpen.value = Boolean(live.ui.conversationsError)
}

/* 票 08：composer 提交完整 payload（文本 + 附件），草稿由 ComposerBar 清空。 */
async function onLiveSend(text: string, files: FileRef[]): Promise<void> {
  await live.send(text, files)
}

/* P3-4：上传失败的即时反馈贴近 composer 附件行；actionNote 兜底提示仍留在侧栏。 */
const composerNote = ref('')

async function onLiveUpload(file: File): Promise<FileRef | null> {
  composerNote.value = ''
  const uploaded = await live.upload(file)
  if (!uploaded) composerNote.value = live.ui.actionNote || '附件上传失败'
  return uploaded
}

/* ---- 自动吸底跟随 ---- */
const activeEntries = computed(() => live.view.entries)
/* 回合导航轨条目（右侧刻度）：每回合一个预览刻度。 */
const turnRailItems = computed<TurnRailItem[]>(() => deriveRailItems(activeEntries.value))

/* ---- 侧栏折叠（对齐 dsh：280 ↔ 56 轨道过渡 + 内容淡出/导轨入场） ---- */
const sidebarCollapsed = ref(false)

const column = ref<InstanceType<typeof ConversationColumn> | null>(null)
/* 阈值对齐上游 FOLLOW_THRESHOLD（24px）：滚离底部超过 24px 即暂停跟随。 */
const follow = new ScrollFollow(true, 24)
let stopWatch: (() => void) | undefined
/* 回到底部按钮可见性 = 未处于跟随尾部的状态（上游 toBottomSlot 的开关）。 */
const showToBottom = ref(false)

function scrollElement(): HTMLElement | null {
  return (column.value?.scrollBody as HTMLElement | null | undefined) ?? null
}

function onScroll(): void {
  const el = scrollElement()
  if (el) showToBottom.value = !follow.sample(scrollMetrics(el))
}

/* scrollend 结算未竟动画（停在目标外则释放跟随）；内核不支持时用防抖兜底。 */
let settleTimer: number | null = null
function onScrollSettle(): void {
  const el = scrollElement()
  if (!el) return
  if (settleTimer !== null) window.clearTimeout(settleTimer)
  settleTimer = window.setTimeout(() => {
    settleTimer = null
    showToBottom.value = !follow.settle(scrollMetrics(el))
  }, 150)
}

function onReaderGesture(): void {
  const el = scrollElement()
  if (el) follow.interrupt(el, scrollMetrics(el))
}

function returnToBottom(): void {
  const el = scrollElement()
  if (!el) return
  follow.toBottom(el, scrollMetrics(el), 'smooth')
  showToBottom.value = false
}

/* ---- 响应式自动折叠（对齐上游 columns.ts SIDEBAR_AUTO_COLLAPSE：<1024px 收拢） ---- */
let collapseQuery: MediaQueryList | null = null
function onCollapseQuery(event: MediaQueryListEvent): void {
  sidebarCollapsed.value = event.matches
}

onMounted(() => {
  const el = scrollElement()
  el?.addEventListener('scroll', onScroll, { passive: true })
  if ('onscrollend' in window) el?.addEventListener('scrollend', onScrollSettle, { passive: true })
  el?.addEventListener('wheel', onReaderGesture, { passive: true })
  el?.addEventListener('touchstart', onReaderGesture, { passive: true })
  collapseQuery = window.matchMedia('(max-width: 1023.98px)')
  sidebarCollapsed.value = collapseQuery.matches
  collapseQuery.addEventListener('change', onCollapseQuery)
  stopWatch = watch(
    () => [
      activeEntries.value,
      activeEntries.value[activeEntries.value.length - 1],
      activeEntries.value.length,
    ],
    () => {
      const target = scrollElement()
      if (!target || !follow.active) return
      follow.toBottom(target, scrollMetrics(target))
    },
    { deep: true, immediate: true },
  )
})

onBeforeUnmount(() => {
  const el = scrollElement()
  el?.removeEventListener('scroll', onScroll)
  if ('onscrollend' in window) el?.removeEventListener('scrollend', onScrollSettle)
  el?.removeEventListener('wheel', onReaderGesture)
  el?.removeEventListener('touchstart', onReaderGesture)
  collapseQuery?.removeEventListener('change', onCollapseQuery)
  if (settleTimer !== null) window.clearTimeout(settleTimer)
  stopWatch?.()
})
</script>

<template>
  <AppShell :sidebar-collapsed="sidebarCollapsed">
    <template #sidebar>
      <SidebarRail
        :controller="live"
        :collapsed="sidebarCollapsed"
        @toggle="sidebarCollapsed = !sidebarCollapsed"
      />
    </template>
    <ConversationColumn
      ref="column"
      :title="liveTitle"
      :rail-items="turnRailItems"
      :to-bottom-visible="showToBottom"
      @to-bottom="returnToBottom"
    >
      <template #actions>
        <!-- 停止按钮已移入 composer（票 08）：只在运行中渲染，停止 best-effort 由控制器承接。 -->
        <button
          v-if="live.ui.connected"
          type="button"
          class="pi-mode-button"
          data-testid="open-connect-form"
          @click="formOpen = true"
        >
          连接设置
        </button>
      </template>

      <div class="pi-live-stack">
        <ConnectionForm
          v-if="showForm"
          :connection-error="live.ui.conversationsError || ''"
          :connected="Boolean(live.ui.connected)"
          @connect="onConnect"
          @close="formOpen = false"
        />
        <LiveConversation :controller="live" />
      </div>

      <template #composer>
        <!-- P3-4：上传失败即时提示（附件行上方），与侧栏 actionNote 同源互补。 -->
        <p
          v-if="composerNote"
          class="pi-composer-note"
          data-testid="composer-action-note"
          role="status"
        >
          {{ composerNote }}
        </p>
        <ComposerBar
          v-model="liveDraft"
          :interactive="liveInteractive"
          :busy="Boolean(live.ui.running)"
          :stoppable="Boolean(live.ui.running || live.ui.stopping)"
          :stopping="Boolean(live.ui.stopping)"
          :upload="onLiveUpload"
          @send="onLiveSend"
          @stop="live.stop()"
        />
      </template>
    </ConversationColumn>
  </AppShell>
</template>

<style>
/* 组件自有（非 vendor）：会话栈（连接表单叠加在会话视图上方）。 */
.pi-live-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 组件自有（非 vendor）：composer 附件行上方的即时提示（上传失败等）。 */
.pi-composer-note {
  margin: 0 0 6px;
  padding: 0 4px;
  color: var(--dsw-alias-state-error-primary, #b3261e);
  font-size: 12px;
  line-height: 18px;
}

/* 组件自有（非 vendor）：headerActions 里的连接设置按钮，几何对齐 28px 图标行。 */
.pi-mode-button {
  height: 28px;
  padding: 0 10px;
  border: none;
  border-radius: var(--dsw-radius-sm, 8px);
  background: transparent;
  color: var(--dsw-alias-label-secondary, #545557);
  font-size: 13px;
  line-height: 20px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
}

.pi-mode-button:hover {
  background-color: var(--dsw-alias-interactive-bg-hover, rgba(0, 0, 0, 0.04));
  color: var(--dsw-alias-label-primary, #0b0b0c);
}
</style>
