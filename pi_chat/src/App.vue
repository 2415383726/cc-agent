<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ReplayController } from './replay/controller'
import { scenarioById } from './replay/scenarios'
import { errorText, statusText, toolStatusText } from './projection/labels'
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
  <div class="pi-chat-shell">
    <header>
      <h1>Pi Chat</h1>
      <p>
        <strong data-testid="replay-badge">回放模式</strong>
        <span>静态回放：使用与真实运行相同的契约、投影与控制器渲染，不发起任何网络请求。</span>
      </p>
      <label>
        回放场景
        <select :value="selectedId" aria-label="回放场景" @change="onScenarioChange">
          <option v-for="scenario in replay.scenarios" :key="scenario.id" :value="scenario.id">
            {{ scenario.title }}
          </option>
        </select>
      </label>
    </header>

    <p v-if="replay.ui.error" role="alert">{{ replay.ui.error }}</p>
    <ul v-if="view.warnings.length" aria-label="警告">
      <li v-for="warning in view.warnings" :key="warning">{{ warning }}</li>
    </ul>

    <main>
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
    </main>

    <footer>
      <input
        type="text"
        disabled
        placeholder="回放模式：输入在后续票据中启用"
        aria-label="消息输入（回放模式禁用）"
      />
      <button type="button" disabled>发送</button>
    </footer>
  </div>
</template>
