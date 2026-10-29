<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ApprovalEntry } from '../projection/transcript'
import { renderJson } from '../projection/markdown'

const props = defineProps<{ entry: ApprovalEntry }>()
const emit = defineEmits<{
  decide: [decision: 'approve' | 'reject', scope: 'once' | 'session']
}>()

const scope = ref<'once' | 'session'>('once')
const waiting = computed(() => props.entry.status === 'waiting')
const argumentsJson = computed(() => renderJson(props.entry.arguments || {}))
</script>

<template>
  <section class="pi-approval-card" :class="{ 'is-resolved': !waiting }">
    <header class="pi-card-title">
      <span class="pi-card-icon pi-card-icon-warning" aria-hidden="true">!</span>
      <div>
        <strong>Approval required: {{ entry.tool }}</strong>
        <p class="pi-muted">
          This is a tool authorization, not a questionnaire answer. The operation has not run.
        </p>
      </div>
      <span class="pi-pill" :class="`pi-pill-${entry.status}`">{{ entry.status }}</span>
    </header>

    <dl class="pi-approval-meta">
      <dt>Tool</dt>
      <dd>{{ entry.tool }}</dd>
      <dt>Source</dt>
      <dd>{{ entry.source || 'Dify' }}</dd>
      <dt>Call ID</dt>
      <dd><code>{{ entry.toolCallId }}</code></dd>
    </dl>

    <details class="pi-approval-arguments">
      <summary>Operation parameters</summary>
      <pre v-html="argumentsJson"></pre>
    </details>

    <div v-if="waiting" class="pi-approval-actions">
      <label class="pi-scope">
        <span>Authorization scope</span>
        <select v-model="scope" :disabled="entry.submitting">
          <option value="once">This operation only</option>
          <option value="session">This tool for the rest of the conversation</option>
        </select>
      </label>
      <p class="pi-muted pi-small">
        Approval is re-checked against the current tool set, policy and budget. A session grant never
        overrides server-side permissions.
      </p>
      <p v-if="entry.error" class="pi-form-error" role="alert">{{ entry.error }}</p>
      <div class="pi-form-actions">
        <button
          type="button"
          class="pi-button pi-button-danger"
          :disabled="entry.submitting"
          @click="emit('decide', 'reject', scope)"
        >
          Reject
        </button>
        <button
          type="button"
          class="pi-button pi-button-primary"
          :disabled="entry.submitting"
          @click="emit('decide', 'approve', scope)"
        >
          {{ entry.submitting ? 'Submitting…' : 'Approve' }}
        </button>
      </div>
    </div>

    <div v-else class="pi-approval-result">
      <p v-if="entry.status === 'rejected'">The operation was rejected and was not executed.</p>
      <p v-else-if="entry.status === 'approved'">
        The operation was approved{{ entry.scope ? ` (${entry.scope} scope)` : '' }} and its result is
        shown in the transcript.
      </p>
      <p v-else>The approval was cancelled.</p>
    </div>
  </section>
</template>
