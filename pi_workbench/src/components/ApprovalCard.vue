<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ApprovalEntry } from '../projection/transcript'
import { renderJson } from '../projection/markdown'
import { statusText } from '../projection/labels'

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
        <strong>需要审批：{{ entry.tool }}</strong>
        <p class="pi-muted">
          这是工具授权，不是问卷作答。该操作尚未执行。
        </p>
      </div>
      <span class="pi-pill" :class="`pi-pill-${entry.status}`">{{ statusText(entry.status) }}</span>
    </header>

    <dl class="pi-approval-meta">
      <dt>工具</dt>
      <dd>{{ entry.tool }}</dd>
      <dt>来源</dt>
      <dd>{{ entry.source || 'Dify' }}</dd>
      <dt>调用 ID</dt>
      <dd><code>{{ entry.toolCallId }}</code></dd>
    </dl>

    <details class="pi-approval-arguments">
      <summary>操作参数</summary>
      <pre v-html="argumentsJson"></pre>
    </details>

    <div v-if="waiting" class="pi-approval-actions">
      <label class="pi-scope">
        <span>授权范围</span>
        <select v-model="scope" :disabled="entry.submitting">
          <option value="once">仅本次操作</option>
          <option value="session">本会话内该工具</option>
        </select>
      </label>
      <p class="pi-muted pi-small">
        批准后会重新检查当前工具、策略和预算。会话授权不会绕过服务端权限。
      </p>
      <p v-if="entry.error" class="pi-form-error" role="alert">{{ entry.error }}</p>
      <div class="pi-form-actions">
        <button
          type="button"
          class="pi-button pi-button-danger"
          :disabled="entry.submitting"
          @click="emit('decide', 'reject', scope)"
        >
          拒绝
        </button>
        <button
          type="button"
          class="pi-button pi-button-primary"
          :disabled="entry.submitting"
          @click="emit('decide', 'approve', scope)"
        >
          {{ entry.submitting ? '提交中…' : '批准' }}
        </button>
      </div>
    </div>

    <div v-else class="pi-approval-result">
      <p v-if="entry.status === 'rejected'">操作已被拒绝，未执行。</p>
      <p v-else-if="entry.status === 'approved'">
        操作已批准{{ entry.scope === 'session' ? '（本会话范围）' : '（仅本次）' }}，结果显示在对话中。
      </p>
      <p v-else>审批已取消。</p>
    </div>
  </section>
</template>
