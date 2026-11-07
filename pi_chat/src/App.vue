<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ReplayController } from './replay/controller'
import { scenarioById } from './replay/scenarios'
import { statusText, toolStatusText } from './projection/labels'
import AppShell from './shell/AppShell.vue'
import SidebarRail from './shell/SidebarRail.vue'
import ConversationColumn from './shell/ConversationColumn.vue'
import ComposerBar from './shell/ComposerBar.vue'
import AssistantMessage from './timeline/AssistantMessage.vue'
import NoteRow from './timeline/NoteRow.vue'
import ReasoningRow from './timeline/ReasoningRow.vue'
import TerminalRow from './timeline/TerminalRow.vue'
import UserMessage from './timeline/UserMessage.vue'
import QuestionCard from './cards/QuestionCard.vue'
import { ScrollFollow, scrollMetrics } from './timeline/scrollFollow'
import type {
  ApprovalEntry,
  CompactionEntry,
  MessageEntry,
  NoteEntry,
  QuestionEntry,
  ReasoningEntry,
  SkillEntry,
  TerminalEntry,
  ToolEntry,
  WorkbenchEntry,
} from './projection/transcript'

/*
 * Binding seam: both controllers are framework-agnostic pure TS. This shell is
 * the only Vue-aware layer — it wraps the controller in reactive() and reads
 * view/ui as plain data. 时间线四类消息条目（用户/助手/思考/终态）由
 * timeline/ 下的 Harness 同族组件渲染；问卷卡由 cards/QuestionCard.vue 渲染
 * （票据 05，提交走 controller 的 submitAnswers/cancelQuestion，回放本地闭环）；
 * 工具/技能/压缩/审批仍是占位（票据 04/06 接管）。自动吸底：读者未向上滚离
 * 底部时，新内容保持贴底（timeline/scrollFollow.ts，上游 use-scroll-follow
 * 的 best-effort 平移）。
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
/* composer 草稿只停留在本地（回放不发消息）；发送逻辑留待后续票据。 */
const draft = ref('')

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

function entryLabel(entry: WorkbenchEntry): string {
  switch (entry.kind) {
    case 'tool':
      return '工具'
    case 'skill':
      return '技能'
    case 'compaction':
      return '上下文压缩'
    case 'question':
      return '问卷'
    case 'approval':
      return '审批'
    default:
      return entry.kind
  }
}

function skillText(entry: SkillEntry): string {
  if (entry.action === 'read') {
    return `${entry.skill} · 读取 ${entry.path || ''}`
  }
  return `${entry.skill} · 已激活`
}

function compactionText(entry: CompactionEntry): string {
  const parts: string[] = []
  if (typeof entry.tokensBefore === 'number') parts.push(`压缩前 ${entry.tokensBefore} tokens`)
  if (typeof entry.summaryChars === 'number') parts.push(`摘要 ${entry.summaryChars} 字符`)
  return parts.join(' · ') || (entry.phase === 'start' ? '开始压缩' : '压缩完成')
}

function approvalText(entry: ApprovalEntry): string {
  return `${entry.tool} · ${statusText(entry.status)}`
}

function resultText(entry: ToolEntry): string {
  const parts: string[] = []
  if (entry.updates.length) parts.push(entry.updates.join('\n'))
  if (entry.result) parts.push(entry.result)
  return parts.join('\n')
}

const isPlaceholder = (entry: WorkbenchEntry): boolean =>
  entry.kind === 'tool' || entry.kind === 'skill' || entry.kind === 'compaction'
  || entry.kind === 'approval'

const firstEntryTs = computed(() => view.value.entries[0]?.ts)
</script>

<template>
  <AppShell>
    <template #sidebar>
      <SidebarRail />
    </template>
    <ConversationColumn ref="column" :title="scenarioTitle">
      <template #actions>
        <label class="pi-replay-select">
          回放场景
          <select :value="selectedId" aria-label="回放场景" @change="onScenarioChange">
            <option v-for="scenario in replay.scenarios" :key="scenario.id" :value="scenario.id">
              {{ scenario.title }}
            </option>
          </select>
        </label>
      </template>

      <p v-if="replay.ui.error" role="alert">{{ replay.ui.error }}</p>
      <ul v-if="view.warnings.length" aria-label="警告">
        <li v-for="warning in view.warnings" :key="warning">{{ warning }}</li>
      </ul>

      <p v-if="!view.entries.length">选择一个回放场景查看过程事件。</p>
      <ol v-else class="pi-timeline" aria-label="会话记录">
        <li v-for="entry in view.entries" :key="`${entry.kind}:${entry.id}`">
          <UserMessage v-if="isUser(entry)" :entry="entry as MessageEntry" />

          <AssistantMessage v-else-if="isAssistant(entry)" :entry="entry as MessageEntry" />

          <ReasoningRow v-else-if="entry.kind === 'reasoning'" :entry="entry as ReasoningEntry" />

          <TerminalRow
            v-else-if="entry.kind === 'terminal'"
            :entry="entry as TerminalEntry"
            :start-ts="firstEntryTs"
          />

          <NoteRow v-else-if="entry.kind === 'note'" :entry="entry as NoteEntry" />

          <!-- 问卷卡（票据 05）：作答/跳过/取消提交为 interaction JSON（回放本地闭环）。 -->
          <QuestionCard
            v-else-if="entry.kind === 'question'"
            :entry="entry as QuestionEntry"
            @submit="(answers) => replay.submitAnswers(entry as QuestionEntry, answers)"
            @cancel="replay.cancelQuestion(entry as QuestionEntry)"
          />

          <!-- 工具卡/技能/压缩（票据 04）与审批卡（票据 06）保持占位渲染。 -->
          <template v-else-if="isPlaceholder(entry)">
            <strong>{{ entryLabel(entry) }}</strong>
            <template v-if="entry.kind === 'tool'">
              <span> · {{ (entry as ToolEntry).name }} · {{ toolStatusText((entry as ToolEntry).status) }}</span>
              <pre>{{ JSON.stringify((entry as ToolEntry).args) }}</pre>
              <p v-if="resultText(entry as ToolEntry)">{{ resultText(entry as ToolEntry) }}</p>
            </template>
            <p v-else-if="entry.kind === 'skill'">{{ skillText(entry as SkillEntry) }}</p>
            <p v-else-if="entry.kind === 'compaction'">{{ compactionText(entry as CompactionEntry) }}</p>
            <p v-else-if="entry.kind === 'approval'">{{ approvalText(entry as ApprovalEntry) }}</p>
          </template>

          <template v-else>
            <strong>{{ entry.kind }}</strong>
          </template>
        </li>
      </ol>

      <template #composer>
        <ComposerBar v-model="draft" />
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
</style>
