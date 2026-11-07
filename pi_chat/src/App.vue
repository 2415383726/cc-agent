<script setup lang="ts">
import { computed, reactive, ref, shallowRef } from 'vue'
import { ReplayController } from './replay/controller'
import { scenarioById } from './replay/scenarios'
import { DifyController } from './dify/controller'
import { defaultConfig, saveSessionCredentials } from './dify/config'
import type { SessionCredentials } from './dify/config'
import { errorText, statusText, toolStatusText } from './projection/labels'
import AppShell from './shell/AppShell.vue'
import SidebarRail from './shell/SidebarRail.vue'
import ConversationColumn from './shell/ConversationColumn.vue'
import ComposerBar from './shell/ComposerBar.vue'
import ConnectionForm from './shell/ConnectionForm.vue'
import LiveConversation from './shell/LiveConversation.vue'
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
 * view/ui as plain data.
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

function entryLabel(entry: WorkbenchEntry): string {
  switch (entry.kind) {
    case 'message':
      return (entry as MessageEntry).role === 'user' ? '用户' : '助手'
    case 'reasoning':
      return '思考'
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
    case 'terminal':
      return '终态'
    case 'note':
      return '备注'
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

function terminalText(entry: TerminalEntry): string {
  const terminal = entry.terminal
  const lines = [statusText(terminal.status)]
  if (terminal.answer) lines.push(terminal.answer)
  if (terminal.error?.message) lines.push(errorText(terminal.error.code, terminal.error.message))
  return lines.join('\n')
}

function resultText(entry: ToolEntry): string {
  const parts: string[] = []
  if (entry.updates.length) parts.push(entry.updates.join('\n'))
  if (entry.result) parts.push(entry.result)
  return parts.join('\n')
}

const isUser = (entry: WorkbenchEntry): boolean =>
  entry.kind === 'message' && (entry as MessageEntry).role === 'user'
const isAssistant = (entry: WorkbenchEntry): boolean =>
  entry.kind === 'message' && (entry as MessageEntry).role === 'assistant'
</script>

<template>
  <AppShell>
    <template #sidebar>
      <SidebarRail :controller="mode === 'live' ? live : null" />
    </template>
    <ConversationColumn :title="liveTitle" :badge="modeBadge">
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
        <ol v-else aria-label="会话记录">
        <li v-for="entry in view.entries" :key="`${entry.kind}:${entry.id}`">
          <template v-if="isUser(entry)">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ (entry as MessageEntry).text }}</p>
          </template>

          <template v-else-if="isAssistant(entry)">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ (entry as MessageEntry).text }}</p>
          </template>

          <template v-else-if="entry.kind === 'reasoning'">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ (entry as ReasoningEntry).text }}</p>
          </template>

          <template v-else-if="entry.kind === 'tool'">
            <strong>{{ entryLabel(entry) }} · {{ (entry as ToolEntry).name }}</strong>
            <span>{{ toolStatusText((entry as ToolEntry).status) }}</span>
            <pre>{{ JSON.stringify((entry as ToolEntry).args) }}</pre>
            <p v-if="resultText(entry as ToolEntry)">{{ resultText(entry as ToolEntry) }}</p>
          </template>

          <template v-else-if="entry.kind === 'skill'">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ skillText(entry as SkillEntry) }}</p>
          </template>

          <template v-else-if="entry.kind === 'compaction'">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ compactionText(entry as CompactionEntry) }}</p>
          </template>

          <template v-else-if="entry.kind === 'question'">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ questionText(entry as QuestionEntry) }}</p>
          </template>

          <template v-else-if="entry.kind === 'approval'">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ approvalText(entry as ApprovalEntry) }}</p>
          </template>

          <template v-else-if="entry.kind === 'terminal'">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ terminalText(entry as TerminalEntry) }}</p>
          </template>

          <template v-else-if="entry.kind === 'note'">
            <strong>{{ entryLabel(entry) }}</strong>
            <p>{{ (entry as NoteEntry).text }}</p>
          </template>

          <template v-else>
            <strong>{{ entryLabel(entry) }}</strong>
          </template>
        </li>
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
