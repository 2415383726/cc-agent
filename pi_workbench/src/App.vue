<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import ConnectionForm from './components/ConnectionForm.vue'
import TranscriptEntry from './components/TranscriptEntry.vue'
import WorkbenchComposer from './components/WorkbenchComposer.vue'
import {
  defaultConfig,
  loadDeploymentConfig,
  saveSessionCredentials,
  type WorkbenchConfig,
} from './dify/config'
import { DifyController, type WorkbenchController } from './dify/controller'
import { ReplayController } from './replay/controller'
import { REPLAY_SCENARIOS } from './replay/scenarios'
import type {
  ApprovalEntry,
  FileRef,
  QuestionEntry,
  WorkbenchEntry,
} from './projection/transcript'

const initialScenario = new URLSearchParams(window.location.search).get('replay')
const config = ref<WorkbenchConfig>(defaultConfig())
const controller = reactive(new DifyController(config.value)) as DifyController
const replay = reactive(new ReplayController()) as ReplayController
const mode = ref<'dify' | 'replay'>(initialScenario ? 'replay' : 'dify')
const showConfig = ref(!config.value.apiKey && !initialScenario)
if (initialScenario) replay.loadScenario(initialScenario)
const showReplayPanel = ref(false)
const transcriptEl = ref<HTMLElement | null>(null)
const appTitle = ref('Pi Agent Workbench')

const active = computed<WorkbenchController>(() =>
  mode.value === 'dify' ? (controller as WorkbenchController) : (replay as WorkbenchController),
)
const view = computed(() => active.value.view)
const ui = computed(() => active.value.ui)
const pending = computed(() => {
  const question = view.value.entries.find(
    (entry): entry is QuestionEntry => entry.kind === 'question' && entry.status === 'waiting',
  )
  if (question) return { kind: 'question' as const, entry: question }
  const approval = view.value.entries.find(
    (entry): entry is ApprovalEntry => entry.kind === 'approval' && entry.status === 'waiting',
  )
  if (approval) return { kind: 'approval' as const, entry: approval }
  return null
})
const statusLabel = computed(() => {
  if (ui.value.stopping) return 'stopping'
  if (ui.value.running) return 'running'
  if (view.value.terminal) return view.value.terminal.status.replace(/_/g, ' ')
  return 'idle'
})
const statusTone = computed(() => {
  const status = statusLabel.value
  if (['running', 'stopping'].includes(status)) return 'running'
  if (['completed', 'awaiting user', 'awaiting approval'].includes(status)) return 'ok'
  if (['failed', 'state save failed', 'context overflow', 'context too large'].includes(status)) return 'error'
  if (['stopped', 'cancelled', 'unknown', 'budget exhausted'].includes(status)) return 'warning'
  return 'idle'
})
const connectionLabel = computed(() =>
  mode.value === 'replay'
    ? 'Static replay'
    : controller.ui.connected
      ? 'Dify connected'
      : 'Dify not configured',
)
const conversationValue = computed(() =>
  mode.value === 'replay' ? 'replay' : controller.ui.conversationId,
)
const isWaiting = computed(() =>
  Boolean(view.value.terminal && ['awaiting_user', 'awaiting_approval'].includes(view.value.terminal.status)),
)

watch(
  () => [view.value.entries.length, view.value.terminal?.status, pending.value?.kind],
  async () => {
    await nextTick()
    const element = transcriptEl.value
    if (!element) return
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight
    if (distance < 220) element.scrollTop = element.scrollHeight
  },
)

onMounted(async () => {
  const deployment = await loadDeploymentConfig()
  if (deployment) {
    if (deployment.title) appTitle.value = deployment.title
    if (deployment.baseUrl) config.value.baseUrl = deployment.baseUrl
    if (deployment.user) config.value.user = deployment.user
    if (deployment.inputs) config.value.inputs = deployment.inputs
    controller.updateConfig(config.value)
  }
  if (initialScenario) return
  if (!config.value.apiKey) {
    showConfig.value = true
    return
  }
  controller.updateConfig(config.value)
  await controller.refreshConversations()
})

function saveConnection(next: WorkbenchConfig) {
  config.value = next
  saveSessionCredentials(next)
  controller.updateConfig(next)
  showConfig.value = false
  void controller.refreshConversations()
}

function onSend(text: string, files: FileRef[]) {
  void active.value.send(text, files)
}

function onStop() {
  void active.value.stop()
}

function onSelectConversation(event: Event) {
  if (mode.value !== 'dify') return
  const id = (event.target as HTMLSelectElement).value
  if (!id) {
    controller.newConversation()
    return
  }
  void controller.loadConversation(id)
}

function onNewConversation() {
  if (mode.value === 'replay') {
    replay.loadScenario(replay.current?.id || 'process')
    return
  }
  controller.newConversation()
}

function openReplay(id: string) {
  mode.value = 'replay'
  showReplayPanel.value = false
  showConfig.value = false
  replay.loadScenario(id)
}

function backToDify() {
  mode.value = 'dify'
  showReplayPanel.value = false
  showConfig.value = !config.value.apiKey
}

function submitAnswers(entry: QuestionEntry, answers: Record<string, string | string[]>) {
  void active.value.submitAnswers(entry, answers)
}

function cancelQuestion(entry: QuestionEntry) {
  void active.value.cancelQuestion(entry)
}

function approvalDecision(
  entry: ApprovalEntry,
  decision: 'approve' | 'reject',
  scope: 'once' | 'session',
) {
  void active.value.submitApproval(entry, decision, scope)
}

function entryKey(entry: WorkbenchEntry): string {
  return `${entry.kind}:${entry.id}`
}
</script>

<template>
  <div class="pi-workbench-shell">
    <header class="pi-workbench-header">
      <div class="pi-brand">
        <span class="pi-brand-mark" aria-hidden="true">π</span>
        <div>
          <h1>{{ appTitle }}</h1>
          <p class="pi-muted pi-small">{{ connectionLabel }}</p>
        </div>
      </div>

      <div class="pi-header-actions">
        <template v-if="mode === 'dify'">
          <select
            class="pi-conversation-select"
            :value="conversationValue"
            aria-label="Conversation"
            @change="onSelectConversation"
          >
            <option value="">New conversation</option>
            <option v-for="conversation in controller.ui.conversations" :key="conversation.id" :value="conversation.id">
              {{ conversation.name }}
            </option>
          </select>
          <button type="button" class="pi-button pi-button-ghost" @click="onNewConversation">New</button>
          <button type="button" class="pi-button pi-button-ghost" @click="controller.refreshConversations()">Refresh</button>
        </template>
        <span class="pi-status-pill" :class="`pi-status-${statusTone}`">{{ statusLabel }}</span>
        <button type="button" class="pi-button pi-button-ghost" @click="showReplayPanel = !showReplayPanel">
          Replay
        </button>
        <button
          v-if="mode === 'dify'"
          type="button"
          class="pi-button pi-button-ghost"
          @click="showConfig = !showConfig"
        >
          Connection
        </button>
        <button v-else type="button" class="pi-button pi-button-ghost" @click="backToDify">Connect Dify</button>
      </div>
    </header>

    <div v-if="showReplayPanel" class="pi-replay-panel">
      <div class="pi-replay-head">
        <div>
          <h2>Static event replay</h2>
          <p class="pi-muted pi-small">
            These scenarios render the display contract without the community backend. They exercise the
            same projection and components used by the live Dify stream.
          </p>
        </div>
        <button type="button" class="pi-icon-button" aria-label="Close replay panel" @click="showReplayPanel = false">×</button>
      </div>
      <div class="pi-replay-grid">
        <button
          v-for="scenario in REPLAY_SCENARIOS"
          :key="scenario.id"
          type="button"
          class="pi-replay-card"
          @click="openReplay(scenario.id)"
        >
          <strong>{{ scenario.title }}</strong>
          <span>{{ scenario.description }}</span>
        </button>
      </div>
    </div>

    <ConnectionForm
      v-if="showConfig && mode === 'dify'"
      :config="config"
      @save="saveConnection"
      @close="showConfig = false"
    />

    <p v-if="ui.error" class="pi-banner pi-banner-error" role="alert">{{ ui.error }}</p>
    <p v-if="ui.stoppedNote" class="pi-banner pi-banner-warning">{{ ui.stoppedNote }}</p>
    <p v-for="warning in view.warnings" :key="warning" class="pi-banner pi-banner-warning">{{ warning }}</p>

    <main ref="transcriptEl" class="pi-transcript" aria-live="polite">
      <div v-if="!view.entries.length" class="pi-empty-state">
        <span class="pi-brand-mark pi-brand-mark-large" aria-hidden="true">π</span>
        <h2>Agent workbench</h2>
        <p>
          Send a request to see real reasoning, tool calls, skill activity, compaction and the final
          answer. Events come from the Pi display contract carried by Dify logs.
        </p>
        <p v-if="mode === 'replay'" class="pi-muted">
          Replay mode is local. Choose a scenario above or open the Replay panel.
        </p>
        <p v-else-if="!controller.ui.connected" class="pi-muted">
          Configure the Dify connection first. The app node must expose query, model, tools, files,
          interaction, agent_state and conversation variables.
        </p>
      </div>

      <div v-else class="pi-transcript-list">
        <TranscriptEntry
          v-for="entry in view.entries"
          :key="entryKey(entry)"
          :entry="entry"
          @submit-answers="submitAnswers"
          @cancel-question="cancelQuestion"
          @approval-decision="approvalDecision"
        />
        <div v-if="ui.loadingHistory" class="pi-muted pi-history-loading">Loading history…</div>
      </div>
    </main>

    <footer class="pi-workbench-footer">
      <p v-if="pending" class="pi-composer-hint">
        <template v-if="pending.kind === 'question'">Answer the questionnaire above to continue.</template>
        <template v-else>Approve or reject the operation above to continue.</template>
      </p>
      <WorkbenchComposer
        :running="ui.running"
        :stopping="ui.stopping"
        :disabled="isWaiting"
        :upload="(file) => active.upload(file)"
        @send="onSend"
        @stop="onStop"
      />
    </footer>
  </div>
</template>
