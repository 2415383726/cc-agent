<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { ReplayController } from './replay/controller'
import { scenarioById } from './replay/scenarios'
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
import TranscriptView from './timeline/TranscriptView.vue'
import { ScrollFollow, scrollMetrics } from './timeline/scrollFollow'
import type { FileRef } from './projection/transcript'

/*
 * Binding seam: both controllers are framework-agnostic pure TS. This shell is
 * the only Vue-aware layer — it wraps the controller in reactive() and reads
 * view/ui as plain data. 时间线条目由共享 TranscriptView 渲染（ADR-0010：回放
 * 与实时用同一契约与组件，不做第二个渲染器）：回放传 ReplayController 的本地
 * 闭环回调，实时经 LiveConversation 传 DifyController 的 inputs.interaction
 * 通道。自动吸底：读者未向上滚离底部时，新内容保持贴底
 * （timeline/scrollFollow.ts，上游 use-scroll-follow 的 best-effort 平移）。
 */
const replay = reactive(new ReplayController()) as ReplayController

const requestedScenario = new URLSearchParams(window.location.search).get('replay')
const initialScenario = scenarioById(requestedScenario || '') || scenarioById('process')!
replay.loadScenario(initialScenario.id)

const selectedId = ref(initialScenario.id)
const view = computed(() => replay.view)
const scenarioTitle = computed(
  () => replay.scenarios.find((scenario) => scenario.id === selectedId.value)?.title || 'Pi Chat',
)
/* composer 草稿只停留在本地（回放不发消息）；实时模式发送由 DifyController 承接。 */
const draft = ref('')

/* 实时模式（票 07）：默认仍是回放；点「连接 Dify」惰性创建 DifyController。 */
const mode = ref<'replay' | 'live'>('replay')
const live = shallowRef<DifyController | null>(null)
const liveDraft = ref('')
/* 票 08：连接表单收尾——未连接时常显，连接成功收起，「连接设置」可再展开。 */
const formOpen = ref(false)
const showForm = computed(() => {
  const controller = live.value
  if (mode.value !== 'live' || !controller) return false
  return !controller.ui.connected || formOpen.value
})

const modeBadge = computed(() => {
  if (mode.value === 'replay') return '回放模式'
  const controller = live.value
  return controller?.ui.connected ? '实时模式' : '实时模式（未连接）'
})

const liveTitle = computed(() => {
  if (mode.value === 'replay') return scenarioTitle.value
  const controller = live.value
  if (!controller) return 'Pi Chat'
  if (!controller.ui.conversationId) return '新会话'
  const found = controller.ui.conversations.find((item) => item.id === controller.ui.conversationId)
  return found?.name || '当前会话'
})

const liveInteractive = computed(
  () => mode.value === 'live' && Boolean(live.value?.ui.connected) && !live.value?.ui.running,
)

function enterLive(): void {
  if (!live.value) {
    const config = defaultConfig()
    const controller = reactive(new DifyController(config)) as DifyController
    live.value = controller
    if (config.apiKey) void controller.refreshConversations()
  }
  mode.value = 'live'
}

function backToReplay(): void {
  mode.value = 'replay'
}

async function onConnect(credentials: SessionCredentials): Promise<void> {
  const controller = live.value
  if (!controller) return
  controller.updateConfig({ ...credentials })
  saveSessionCredentials({ ...credentials })
  await controller.refreshConversations()
  // 连接失败（列表刷新报错）时表单保持展开显示重试提示；成功即收起。
  formOpen.value = Boolean(controller.ui.conversationsError)
}

/* 票 08：composer 提交完整 payload（文本 + 附件），草稿由 ComposerBar 清空。 */
async function onLiveSend(text: string, files: FileRef[]): Promise<void> {
  const controller = live.value
  if (!controller) return
  await controller.send(text, files)
}

/* P3-4：上传失败的即时反馈贴近 composer 附件行；actionNote 兜底提示仍留在侧栏。 */
const composerNote = ref('')

async function onLiveUpload(file: File): Promise<FileRef | null> {
  const controller = live.value
  if (!controller) return null
  composerNote.value = ''
  const uploaded = await controller.upload(file)
  if (!uploaded) composerNote.value = controller.ui.actionNote || '附件上传失败'
  return uploaded
}

function onScenarioChange(event: Event): void {
  const id = (event.target as HTMLSelectElement).value
  replay.loadScenario(id)
  selectedId.value = id
  // Keeps the URL shareable; replaceState is local and never touches the network.
  window.history.replaceState({}, '', `/?replay=${encodeURIComponent(id)}`)
}

/* ---- 自动吸底跟随 ---- */
/* P2-2：跟随「当前模式」的视图条目——回放跟 replay.view，实时跟 live.view
   （此前只监视回放视图，live 流式条目不触发吸底）。 */
const activeEntries = computed(() =>
  mode.value === 'live' ? live.value?.view.entries ?? [] : view.value.entries,
)
const column = ref<InstanceType<typeof ConversationColumn> | null>(null)
const follow = new ScrollFollow(true, 80)
let stopWatch: (() => void) | undefined

function scrollElement(): HTMLElement | null {
  return (column.value?.scrollBody as HTMLElement | null | undefined) ?? null
}

function onScroll(): void {
  const el = scrollElement()
  if (el) follow.sample(scrollMetrics(el))
}

onMounted(() => {
  const el = scrollElement()
  el?.addEventListener('scroll', onScroll, { passive: true })
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
  scrollElement()?.removeEventListener('scroll', onScroll)
  stopWatch?.()
})
</script>

<template>
  <AppShell>
    <template #sidebar>
      <SidebarRail :controller="mode === 'live' ? live : null" />
    </template>
    <ConversationColumn ref="column" :title="liveTitle" :badge="modeBadge">
      <template #actions>
        <template v-if="mode === 'live'">
          <button type="button" class="pi-mode-button" data-testid="back-replay" @click="backToReplay">回放模式</button>
          <!-- 停止按钮已移入 composer（票 08）：只在运行中渲染，停止 best-effort 由控制器承接。 -->
          <button
            v-if="live?.ui.connected"
            type="button"
            class="pi-mode-button"
            data-testid="open-connect-form"
            @click="formOpen = true"
          >
            连接设置
          </button>
        </template>
        <template v-else>
          <button type="button" class="pi-mode-button" data-testid="enter-live" @click="enterLive">连接 Dify</button>
          <label class="pi-replay-select">
            回放场景
            <select :value="selectedId" aria-label="回放场景" @change="onScenarioChange">
              <option v-for="scenario in replay.scenarios" :key="scenario.id" :value="scenario.id">
                {{ scenario.title }}
              </option>
            </select>
          </label>
        </template>
      </template>

      <!-- 实时分支用真实元素作根（多子节点的 template v-if 分支在切换模式时
           fragment 卸载不稳定）；连接表单展开时叠加在会话视图上方，未连接时常显。 -->
      <div v-if="mode === 'live' && live" class="pi-live-stack">
        <ConnectionForm
          v-if="showForm"
          :connection-error="live.ui.conversationsError || ''"
          :connected="Boolean(live.ui.connected)"
          @connect="onConnect"
          @close="formOpen = false"
        />
        <LiveConversation :controller="live" />
      </div>
      <template v-else>
        <p v-if="replay.ui.error" role="alert">{{ replay.ui.error }}</p>
        <ul v-if="view.warnings.length" aria-label="警告">
          <li v-for="warning in view.warnings" :key="warning">{{ warning }}</li>
        </ul>

      <p v-if="!view.entries.length">选择一个回放场景查看过程事件。</p>
      <!-- 共享时间线渲染器：与实时分支同一契约与组件（ADR-0010）。 -->
      <TranscriptView
        v-else
        :entries="view.entries"
        :running="view.running"
        :outputs="view.outputs"
        :on-question-submit="(entry, answers) => replay.submitAnswers(entry, answers)"
        :on-question-cancel="(entry) => replay.cancelQuestion(entry)"
        :on-approval-submit="(entry, decision, scope) => replay.submitApproval(entry, decision, scope)"
      />
      </template>

      <template #composer>
        <!-- P3-4：上传失败即时提示（附件行上方），与侧栏 actionNote 同源互补。 -->
        <p
          v-if="mode === 'live' && composerNote"
          class="pi-composer-note"
          data-testid="composer-action-note"
          role="status"
        >
          {{ composerNote }}
        </p>
        <ComposerBar
          v-if="mode === 'live'"
          v-model="liveDraft"
          :interactive="liveInteractive"
          :busy="Boolean(live?.ui.running)"
          :stoppable="Boolean(live && (live.ui.running || live.ui.stopping))"
          :stopping="Boolean(live?.ui.stopping)"
          :upload="onLiveUpload"
          @send="onLiveSend"
          @stop="live?.stop()"
        />
        <ComposerBar v-else v-model="draft" />
      </template>
    </ConversationColumn>
  </AppShell>
</template>

<style>
/* 组件自有（非 vendor）：实时分支的会话栈（连接表单叠加在会话视图上方）。 */
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

/* 组件自有（非 vendor）：headerActions 里的回放场景选择器，令牌着色的 caption 行。 */
.pi-replay-select {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--dsw-alias-label-secondary, #545557);
  font-size: 13px;
  line-height: 20px;
  white-space: nowrap;
}

.pi-replay-select select {
  max-width: 220px;
  height: 28px;
  padding: 0 20px 0 8px;
  border: none;
  border-radius: var(--dsw-radius-sm, 8px);
  outline: none;
  background-color: transparent;
  color: var(--dsw-alias-label-secondary, #545557);
  font-size: 13px;
  line-height: 20px;
  font-weight: 500;
  cursor: pointer;
  appearance: none;
}

.pi-replay-select select:hover:not(:disabled) {
  background-color: var(--dsw-alias-interactive-bg-hover, rgba(0, 0, 0, 0.04));
}

/* 组件自有（非 vendor）：headerActions 里的模式切换按钮，几何对齐 28px 图标行。 */
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
