<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { ReplayController } from './replay/controller'
import { scenarioById } from './replay/scenarios'
import { DifyController } from './dify/controller'
import { defaultConfig, saveSessionCredentials } from './dify/config'
import type { SessionCredentials } from './dify/config'
/* toolStatusText 不再由本壳引用：状态徽标文案由 timeline/ToolCard 经 projection/toolStatus 取得。 */
import { statusText } from './projection/labels'
import AppShell from './shell/AppShell.vue'
import SidebarRail from './shell/SidebarRail.vue'
import ConversationColumn from './shell/ConversationColumn.vue'
import ComposerBar from './shell/ComposerBar.vue'
import ConnectionForm from './shell/ConnectionForm.vue'
import LiveConversation from './shell/LiveConversation.vue'
import AssistantMessage from './timeline/AssistantMessage.vue'
import NoteRow from './timeline/NoteRow.vue'
import ReasoningRow from './timeline/ReasoningRow.vue'
import TerminalRow from './timeline/TerminalRow.vue'
import UserMessage from './timeline/UserMessage.vue'
import CompactionRow from './timeline/CompactionRow.vue'
import SkillRow from './timeline/SkillRow.vue'
import ToolCard from './timeline/ToolCard.vue'
import ToolGroupRow from './timeline/ToolGroupRow.vue'
import { groupTimeline, groupTitle } from './timeline/grouping'
import { ScrollFollow, scrollMetrics } from './timeline/scrollFollow'
import type {
  ApprovalEntry,
  MessageEntry,
  NoteEntry,
  QuestionEntry,
  ReasoningEntry,
  TerminalEntry,
  WorkbenchEntry,
} from './projection/transcript'

/*
 * Binding seam: both controllers are framework-agnostic pure TS. This shell is
 * the only Vue-aware layer — it wraps the controller in reactive() and reads
 * view/ui as plain data. 时间线条目由 timeline/ 下的 Harness 同族组件渲染：
 * 消息四类（票据 03）+ 工具折叠卡/分组/技能行/压缩行（票据 04）；问卷/审批卡
 * 仍是占位（票据 05/06 接管）。自动吸底：读者未向上滚离底部时，新内容保持贴底
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
}

async function onLiveSend(): Promise<void> {
  const controller = live.value
  if (!controller) return
  const text = liveDraft.value
  liveDraft.value = ''
  await controller.send(text)
}

function onScenarioChange(event: Event): void {
  const id = (event.target as HTMLSelectElement).value
  replay.loadScenario(id)
  selectedId.value = id
  // Keeps the URL shareable; replaceState is local and never touches the network.
  window.history.replaceState({}, '', `/?replay=${encodeURIComponent(id)}`)
}

/* ---- 自动吸底跟随 ---- */
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
    () => [view.value.entries, view.value.running, view.value.entries[view.value.entries.length - 1]],
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

const isUser = (entry: WorkbenchEntry): boolean =>
  entry.kind === 'message' && (entry as MessageEntry).role === 'user'
const isAssistant = (entry: WorkbenchEntry): boolean =>
  entry.kind === 'message' && (entry as MessageEntry).role === 'assistant'

/* 连续 tool/skill/compaction 折入可折叠组（票据 04）；分组与组头标题拼装是纯函数。 */
const segments = computed(() => groupTimeline(view.value.entries, view.value.running))
const groupActivity = (segment: Extract<typeof segments.value[number], { kind: 'tool-group' }>): string =>
  segment.running ? segment.counts[0]?.kind ?? 'tools' : segment.counts[0]?.kind ?? 'thinking'

function entryLabel(entry: WorkbenchEntry): string {
  switch (entry.kind) {
    case 'question':
      return '问卷'
    case 'approval':
      return '审批'
    default:
      return entry.kind
  }
}

function questionText(entry: QuestionEntry): string {
  const lines = [entry.questionnaire.title || '问卷', statusText(entry.status)]
  for (const question of entry.questionnaire.questions || []) {
    lines.push(`- ${question.question}`)
  }
  return lines.join('\n')
}

function approvalText(entry: ApprovalEntry): string {
  return `${entry.tool} · ${statusText(entry.status)}`
}

const isPlaceholder = (entry: WorkbenchEntry): boolean =>
  entry.kind === 'question' || entry.kind === 'approval'

const firstEntryTs = computed(() => view.value.entries[0]?.ts)
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
          <button
            v-if="live && live.ui.running"
            type="button"
            class="pi-mode-button"
            data-testid="live-stop"
            @click="live.stop()"
          >
            停止
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

      <ConnectionForm
        v-if="mode === 'live' && live && !live.ui.connected"
        @connect="onConnect"
      />
      <LiveConversation
        v-else-if="mode === 'live' && live"
        :controller="live"
      />
      <template v-else>
        <p v-if="replay.ui.error" role="alert">{{ replay.ui.error }}</p>
        <ul v-if="view.warnings.length" aria-label="警告">
          <li v-for="warning in view.warnings" :key="warning">{{ warning }}</li>
        </ul>

      <p v-if="!view.entries.length">选择一个回放场景查看过程事件。</p>
      <ol v-else class="pi-timeline" aria-label="会话记录">
        <template v-for="segment in segments" :key="segment.kind === 'tool-group' ? segment.id : `${segment.entry.kind}:${segment.entry.id}`">
          <li v-if="segment.kind === 'single'">
            <UserMessage v-if="isUser(segment.entry)" :entry="segment.entry as MessageEntry" />

            <AssistantMessage v-else-if="isAssistant(segment.entry)" :entry="segment.entry as MessageEntry" />

            <ReasoningRow v-else-if="segment.entry.kind === 'reasoning'" :entry="segment.entry as ReasoningEntry" />

            <TerminalRow
              v-else-if="segment.entry.kind === 'terminal'"
              :entry="segment.entry as TerminalEntry"
              :start-ts="firstEntryTs"
            />

            <NoteRow v-else-if="segment.entry.kind === 'note'" :entry="segment.entry as NoteEntry" />

            <!-- 问卷/审批卡（票据 05/06）保持占位渲染。 -->
            <template v-else-if="isPlaceholder(segment.entry)">
              <strong>{{ entryLabel(segment.entry) }}</strong>
              <p v-if="segment.entry.kind === 'question'">{{ questionText(segment.entry as QuestionEntry) }}</p>
              <p v-else-if="segment.entry.kind === 'approval'">{{ approvalText(segment.entry as ApprovalEntry) }}</p>
            </template>

            <template v-else>
              <strong>{{ segment.entry.kind }}</strong>
            </template>
          </li>

          <!-- 工具活动组（票据 04）：连续 tool/skill/compaction 折入同一折叠组。 -->
          <li v-else>
            <ToolGroupRow
              :label="groupTitle(segment.counts, segment.running)"
              :activity="groupActivity(segment)"
              :running="segment.running"
            >
              <template v-for="member in segment.entries" :key="`${member.kind}:${member.id}`">
                <ToolCard v-if="member.kind === 'tool'" :entry="member" />
                <SkillRow v-else-if="member.kind === 'skill'" :entry="member" />
                <CompactionRow v-else-if="member.kind === 'compaction'" :entry="member" />
              </template>
            </ToolGroupRow>
          </li>
        </template>
      </ol>
      </template>

      <template #composer>
        <ComposerBar
          v-if="mode === 'live'"
          v-model="liveDraft"
          :interactive="liveInteractive"
          :busy="Boolean(live?.ui.running)"
          @send="onLiveSend"
        />
        <ComposerBar v-else v-model="draft" />
      </template>
    </ConversationColumn>
  </AppShell>
</template>

<style>
/* 组件自有（非 vendor）：时间线列表。上游 ChatView 的 flow 列（容器查询轴 +
   行间 16px）在本应用由该列表承担；宽度对齐 --dsh-chat-content-width，
   使 vendored 的 .md-table-wide 断行 CSS 在同一宽度轴上生效。 */
.pi-timeline {
  list-style: none;
  margin: 0 auto;
  padding: 24px 16px 16px;
  width: 100%;
  max-width: var(--dsh-chat-content-width, min(100% - 32px, 920px));
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pi-timeline > li {
  min-width: 0;
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
