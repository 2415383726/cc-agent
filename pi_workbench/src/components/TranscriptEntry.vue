<script setup lang="ts">
import { computed, ref } from 'vue'
import AskUserForm from './AskUserForm.vue'
import ApprovalCard from './ApprovalCard.vue'
import { escapeHtml, renderJson, renderMarkdown } from '../projection/markdown'
import { toolStatusLabel, toolStatusTone } from '../projection/toolStatus'
import type { WorkbenchEntry } from '../projection/transcript'

const props = defineProps<{ entry: WorkbenchEntry }>()
const emit = defineEmits<{
  'submit-answers': [entry: Extract<WorkbenchEntry, { kind: 'question' }>, answers: Record<string, string | string[]>]
  'cancel-question': [entry: Extract<WorkbenchEntry, { kind: 'question' }>]
  'approval-decision': [
    entry: Extract<WorkbenchEntry, { kind: 'approval' }>,
    decision: 'approve' | 'reject',
    scope: 'once' | 'session',
  ]
}>()

const expanded = ref(false)
const reasoningExpanded = ref(false)

const tone = computed(() =>
  props.entry.kind === 'tool' ? toolStatusTone(props.entry.status) : 'completed',
)
const statusLabel = computed(() =>
  props.entry.kind === 'tool' ? toolStatusLabel(props.entry.status) : '',
)
const assistantHtml = computed(() =>
  props.entry.kind === 'message' && props.entry.role === 'assistant'
    ? renderMarkdown(props.entry.text)
    : '',
)
const argsHtml = computed(() =>
  props.entry.kind === 'tool' ? renderJson(props.entry.args || {}) : '',
)
const resultHtml = computed(() =>
  props.entry.kind === 'tool' ? escapeHtml(props.entry.result || '') : '',
)
const skillExpanded = ref(false)
const reportedTokens = computed(() => {
  if (props.entry.kind !== 'terminal') return 'unknown'
  const usage = (props.entry.terminal.stats?.usage || {}) as Record<string, any>
  return usage.reported?.total_tokens ?? 'unknown'
})
</script>

<template>
  <div v-if="entry.kind === 'message'" class="transcript-message" :class="entry.role === 'user' ? 'user-message' : 'assistant-message'">
    <div v-if="entry.role === 'user'" class="pi-user-bubble">
      <p class="pi-user-text">{{ entry.text }}</p>
      <div v-if="entry.files && entry.files.length" class="pi-file-chips">
        <span v-for="file in entry.files" :key="file.id || file.name" class="pi-file-chip">
          {{ file.name || file.id || 'file' }}
          <small v-if="file.mime_type || file.mimeType">· {{ file.mime_type || file.mimeType }}</small>
        </span>
      </div>
    </div>
    <div v-else>
      <div class="markdown-body" v-html="assistantHtml"></div>
      <span v-if="entry.streaming" class="pi-streaming-dot" aria-label="streaming"></span>
      <span v-if="entry.platformConfirmed" class="pi-platform-note">Dify final text merged</span>
    </div>
  </div>

  <div v-else-if="entry.kind === 'reasoning'" class="thinking-block" :class="{ 'is-expanded': reasoningExpanded, 'is-streaming': entry.streaming }">
    <button type="button" class="thinking-trigger" :aria-expanded="reasoningExpanded" @click="reasoningExpanded = !reasoningExpanded">
      <span class="chevron" aria-hidden="true">›</span>
      <span class="thinking-label">{{ entry.streaming ? 'Thinking…' : 'Thinking' }}</span>
    </button>
    <div class="thinking-expand-wrapper" :class="{ 'is-expanded': reasoningExpanded }">
      <div class="thinking-expand-inner">
        <pre>{{ entry.text }}</pre>
      </div>
    </div>
  </div>

  <article v-else-if="entry.kind === 'tool'" class="tool-card transcript-tool" :class="{ 'is-expanded': expanded, 'error-card': tone === 'error' }">
    <div class="tool-card-header">
      <button type="button" class="tool-expand-button" :aria-expanded="expanded" @click="expanded = !expanded">
        <span class="chevron" aria-hidden="true">›</span>
        <span class="tool-label">{{ entry.name }}</span>
        <code v-if="entry.callId" :title="entry.callId">{{ entry.callId }}</code>
        <span class="tool-status-mark" :class="`status-${tone}`" :title="statusLabel">
          <span v-if="tone === 'running'" class="tool-status-spinner" aria-hidden="true"></span>
          <svg v-else-if="tone === 'completed'" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.1 8.5 6.4 11.7 12.9 4.4" /></svg>
          <svg v-else-if="tone === 'error'" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.3 4.3 11.7 11.7M11.7 4.3 4.3 11.7" /></svg>
          <svg v-else-if="tone === 'stopped'" viewBox="0 0 16 16" aria-hidden="true"><path d="M5 5h6v6H5z" /></svg>
          <span v-else class="tool-status-question" aria-hidden="true">?</span>
        </span>
        <span class="pi-tool-status-text">{{ statusLabel }}</span>
      </button>
    </div>
    <div class="tool-expand-wrapper" :class="{ 'is-expanded': expanded }">
      <div class="tool-expand-inner">
        <div v-if="expanded" class="tool-expanded-body">
          <div class="tool-command-block">
            <strong>Arguments</strong>
            <pre v-html="argsHtml"></pre>
          </div>
          <div v-if="entry.updates.length" class="pi-tool-updates">
            <strong>Updates</strong>
            <pre v-for="(update, index) in entry.updates" :key="index">{{ update }}</pre>
          </div>
          <div v-if="entry.result" class="tool-result-block">
            <strong>{{ entry.status === 'unknown' ? 'Unknown outcome' : 'Result' }}</strong>
            <pre>{{ resultHtml }}</pre>
          </div>
          <p v-if="entry.status === 'unknown'" class="pi-warning-text">
            The external execution outcome is unknown. Verify the business result before retrying a
            write operation.
          </p>
          <p v-if="entry.status === 'not_executed'" class="pi-muted">
            This call was not executed. Its result was recorded so the model can continue safely.
          </p>
          <div v-if="entry.artifacts.length" class="pi-artifacts">
            <strong>Outputs</strong>
            <ul>
              <li v-for="artifact in entry.artifacts" :key="artifact.id">
                <a v-if="artifact.url" :href="artifact.url" target="_blank" rel="noopener noreferrer">
                  {{ artifact.name }}
                </a>
                <span v-else>{{ artifact.name }}</span>
                <small>{{ artifact.mime_type || artifact.kind }}<template v-if="artifact.size"> · {{ artifact.size }} bytes</template></small>
              </li>
            </ul>
          </div>
          <p v-if="entry.businessRef" class="pi-muted pi-small">
            Business reference: <code>{{ entry.businessRef }}</code>
          </p>
          <p v-if="entry.durationMs" class="pi-muted pi-small">{{ entry.durationMs }} ms</p>
        </div>
      </div>
    </div>
  </article>

  <div v-else-if="entry.kind === 'skill'" class="pi-skill-row" :class="{ 'is-expanded': skillExpanded }">
    <button type="button" class="pi-skill-button" @click="skillExpanded = !skillExpanded">
      <span class="pi-skill-icon" aria-hidden="true">⌘</span>
      <span>
        <strong>{{ entry.action === 'activate' ? 'Skill activated' : 'Skill resource read' }}:
          {{ entry.skill }}</strong>
        <small v-if="entry.action === 'activate'">
          {{ entry.activatedBy || 'model' }} · {{ entry.source || 'skill' }}
        </small>
        <small v-else>
          {{ entry.path }}<template v-if="entry.totalChars"> · {{ entry.totalChars }} chars</template>
          <template v-if="entry.nextOffset !== undefined && entry.nextOffset !== null"> · next page at {{ entry.nextOffset }}</template>
        </small>
      </span>
      <span class="pi-pill pi-pill-ok">real activity</span>
    </button>
  </div>

  <div v-else-if="entry.kind === 'compaction'" class="pi-activity-row">
    <span class="pi-activity-icon" aria-hidden="true">≡</span>
    <span>
      <strong>{{ entry.phase === 'start' ? 'Compacting context' : 'Context compacted' }}</strong>
      <small v-if="entry.tokensBefore"> · {{ entry.tokensBefore }} tokens before</small>
      <small v-if="entry.summaryChars"> · summary {{ entry.summaryChars }} chars</small>
      <small v-if="entry.reason"> · {{ entry.reason }}</small>
    </span>
  </div>

  <AskUserForm
    v-else-if="entry.kind === 'question'"
    :questionnaire="entry.questionnaire"
    :status="entry.status"
    :answers="entry.answers"
    :submitting="entry.submitting"
    :error="entry.error"
    @submit="(answers) => emit('submit-answers', entry, answers)"
    @cancel="emit('cancel-question', entry)"
  />

  <ApprovalCard
    v-else-if="entry.kind === 'approval'"
    :entry="entry"
    @decide="(decision, scope) => emit('approval-decision', entry, decision, scope)"
  />

  <div v-else-if="entry.kind === 'terminal'" class="pi-terminal-row" :class="`pi-terminal-${entry.terminal.status}`">
    <span class="pi-terminal-dot" aria-hidden="true"></span>
    <div>
      <strong>{{ entry.terminal.status.replace(/_/g, ' ') }}</strong>
      <p v-if="entry.terminal.error" class="pi-terminal-error">
        {{ entry.terminal.error.message || entry.terminal.error.code }}
      </p>
      <p v-if="entry.terminal.stats" class="pi-muted pi-small">
        model requests: {{ entry.terminal.stats.model_requests ?? '—' }} ·
        tool calls: {{ entry.terminal.stats.tool_calls ?? '—' }} ·
        reported tokens: {{ reportedTokens }}
      </p>
      <p v-if="entry.terminal.stateRef" class="pi-muted pi-small">
        state revision {{ entry.terminal.stateRef.revision ?? '—' }} ·
        {{ entry.terminal.stateRef.delivery_status || 'unknown' }}
      </p>
    </div>
  </div>

  <div v-else-if="entry.kind === 'note'" class="pi-note-row" :class="`pi-note-${entry.tone || 'info'}`">
    {{ entry.text }}
  </div>
</template>
