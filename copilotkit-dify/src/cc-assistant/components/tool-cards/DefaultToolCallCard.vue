<template>
  <div class="big-tool-card" :class="[statusState, { 'is-open': isExpanded }]">
    <!-- 头部：一行展示，点击展开 -->
    <button class="big-tool-header" :class="{ 'has-detail': hasDetail }" @click="toggleExpand">
      <div class="big-tool-header-left">
        <!-- 状态圆点 -->
        <span class="big-tool-dot" :class="statusState" aria-hidden="true" />

        <!-- 工具名 -->
        <span class="big-tool-name">{{ name }}</span>

        <!-- 收起时的一行摘要 -->
        <span v-if="!isExpanded && shortSummary" class="big-tool-inline-summary">
          {{ shortSummary }}
        </span>
      </div>

      <div class="big-tool-header-right">
        <!-- 状态标签 -->
        <span class="big-tool-badge" :class="statusState">{{ statusLabel }}</span>
        <!-- 展开箭头 -->
        <svg v-if="hasDetail" class="big-tool-chevron" :class="{ rotated: isExpanded }" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
    </button>

    <!-- 展开的详情区 -->
    <div v-if="isExpanded && hasDetail" class="big-tool-body">
      <!-- 参数区 -->
      <div v-if="hasArgs" class="big-tool-section">
        <div class="big-tool-section-title">参数</div>
        <pre class="big-tool-code">{{ prettyArgs }}</pre>
      </div>

      <!-- 结果区 -->
      <div v-if="normalizedResult" class="big-tool-section">
        <div class="big-tool-section-title">结果</div>
        <pre class="big-tool-code">{{ normalizedResult }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  name: string
  toolCallId: string
  args?: any
  parameters?: any
  status: 'inProgress' | 'executing' | 'complete' | 'waiting_permission' | string
  result?: string
}>()

const isExpanded = ref(false)

const params = computed(() => props.args ?? props.parameters ?? {})
const normalizedResult = computed(() => String(props.result ?? '').trim())

const hasArgs = computed(() => {
  if (params.value == null) return false
  if (typeof params.value === 'object') return Object.keys(params.value).length > 0
  return String(params.value).trim().length > 0
})

const prettyArgs = computed(() => {
  if (typeof params.value === 'string') return params.value
  return JSON.stringify(params.value ?? {}, null, 2)
})

const hasDetail = computed(() => hasArgs.value || Boolean(normalizedResult.value))

const statusState = computed(() => {
  const s = String(props.status || '')
  if (s === 'inProgress' || s === 'executing') return 'running'
  if (s === 'complete') return 'done'
  return 'pending'
})

const statusLabel = computed(() => {
  if (statusState.value === 'running') return '执行中'
  if (statusState.value === 'done') return '已完成'
  return '准备中'
})

const shortSummary = computed(() => {
  const r = normalizedResult.value
  if (!r) return ''
  const parsed = parseMaybeJson(r)
  if (Array.isArray(parsed)) return `${parsed.length} 项`
  if (parsed && typeof parsed === 'object') {
    const keys = Object.keys(parsed as Record<string, any>)
    if (keys.length > 0) return `${keys.length} 个字段`
  }
  const compact = String(r).replace(/\s+/g, ' ').trim()
  return compact.length > 80 ? compact.slice(0, 80) + '…' : compact
})

function toggleExpand() {
  if (hasDetail.value) isExpanded.value = !isExpanded.value
}

function parseMaybeJson(value: string): unknown {
  const text = value.trim()
  if (!text || (!text.startsWith('{') && !text.startsWith('['))) return value
  try { return JSON.parse(text) } catch (_) { return value }
}
</script>

<style scoped>
/* ===== 卡片外壳 ===== */
.big-tool-card {
  margin: 6px 0;
  border: 1px solid var(--cc-agent-line);
  border-radius: var(--cc-agent-card-radius);
  background: var(--cc-agent-surface);
  overflow: hidden;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  font-family: var(--cc-agent-font-family);
}

.big-tool-card:hover {
  border-color: var(--cc-agent-primary-border);
  box-shadow: none;
}

.big-tool-card.running {
  border-color: var(--cc-agent-primary-border);
  box-shadow: inset 3px 0 0 var(--cc-agent-primary);
}

.big-tool-card.is-open {
  border-color: var(--cc-agent-primary-border);
  box-shadow: inset 3px 0 0 var(--cc-agent-primary);
}

/* ===== 头部行 ===== */
.big-tool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  background: transparent;
  cursor: default;
  text-align: left;
  font: inherit;
  transition: background 0.15s ease;
}

.big-tool-header.has-detail {
  cursor: pointer;
}

.big-tool-header.has-detail:hover {
  background: var(--cc-agent-surface-alt);
}

.big-tool-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}

.big-tool-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

/* ===== 状态圆点 ===== */
.big-tool-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.big-tool-dot.done {
  background: var(--cc-agent-primary);
  box-shadow: none;
}

.big-tool-dot.running {
  background: var(--cc-agent-primary);
  box-shadow: none;
  animation: dot-pulse 1.6s ease-in-out infinite;
}

.big-tool-dot.pending {
  background: #c8d2df;
}

@keyframes dot-pulse {

  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.3;
  }
}

/* ===== 工具名 ===== */
.big-tool-name {
  font-size: 15px;
  font-weight: 650;
  color: var(--cc-agent-text);
  font-family: inherit;
  white-space: nowrap;
  flex-shrink: 0;
}

/* ===== 折叠态单行摘要 ===== */
.big-tool-inline-summary {
  font-size: 12px;
  color: #7b8798;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

/* ===== 状态 Badge ===== */
.big-tool-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  border: 1px solid var(--cc-agent-line);
  border-radius: 8px;
  white-space: nowrap;
  letter-spacing: 0.01em;
}

.big-tool-badge.done {
  background: #ffffff;
  color: var(--cc-agent-primary);
}

.big-tool-badge.running {
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
}

.big-tool-badge.pending {
  background: var(--cc-agent-surface-alt);
  color: #526071;
}

/* ===== 展开箭头 ===== */
.big-tool-chevron {
  width: 18px;
  height: 18px;
  color: #7b8798;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.big-tool-chevron.rotated {
  transform: rotate(180deg);
}

/* ===== 展开体 ===== */
.big-tool-body {
  padding: 0 12px 12px;
}

.big-tool-section {
  margin-top: 12px;
}

.big-tool-section-title {
  font-size: 11px;
  font-weight: 700;
  color: #7b8798;
  letter-spacing: 0;
  margin-bottom: 6px;
}

/* ===== 代码块 ===== */
.big-tool-code {
  margin: 0;
  padding: 10px 12px;
  background: var(--cc-agent-surface-alt);
  color: var(--cc-agent-text);
  border-radius: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 360px;
  overflow-y: auto;
  border: 1px solid var(--cc-agent-line);
}

.big-tool-code::-webkit-scrollbar {
  width: 6px;
}

.big-tool-code::-webkit-scrollbar-track {
  background: transparent;
}

.big-tool-code::-webkit-scrollbar-thumb {
  background: #c8d2df;
  border-radius: 4px;
}

.big-tool-code::-webkit-scrollbar-thumb:hover {
  background: #aab7c6;
}

.big-tool-header:focus-visible {
  outline: 2px solid var(--cc-agent-focus);
  outline-offset: -2px;
}

@media (prefers-reduced-motion: reduce) {
  .big-tool-card,
  .big-tool-header,
  .big-tool-chevron {
    transition: none;
  }

  .big-tool-dot.running {
    animation: none;
  }
}
</style>
