<template>
  <section class="tool-call-card" :class="{ 'is-expanded': isExpanded }">
    <!-- 头部：可点击展开/折叠 -->
    <button type="button" class="tool-header" :aria-expanded="isExpanded" @click="toggleExpand">
      <div class="tool-header-left">
        <!-- 工具执行状态图标 -->
        <div class="status-icon" :class="displayState">
          <svg v-if="displayState === 'executing'" class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round">
            <path d="M21 12a9 9 0 11-6.219-8.56" />
          </svg>
          <svg v-else-if="displayState === 'complete'" class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 6L9 17l-5-5" />
          </svg>
          <svg v-else class="pending" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </div>
        <div class="tool-name">{{ name }}</div>
      </div>

      <div class="tool-header-right">
        <span class="tool-status-badge" :class="displayState">{{ statusLabel }}</span>
        <svg class="chevron-icon" :class="{ 'rotate': isExpanded }" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </div>
    </button>

    <!-- 主体：折叠区 -->
    <transition name="expand">
      <div v-show="isExpanded" class="tool-body">
        <!-- 基础信息区 -->
        <div class="meta-info">
          <div class="meta-row">
            <span class="meta-label">文件名</span>
            <span class="meta-value file-url">{{ filenameLabel }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">格式</span>
            <span class="meta-value">{{ fileFormat || '-' }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">长度</span>
            <span class="meta-value">{{ contentLengthLabel }}</span>
          </div>
        </div>

        <!-- 内容预览区 (write_file 特有) -->
        <div v-if="contentPreview" class="code-section">
          <div class="section-title">内容预览</div>
          <pre class="code-block">{{ contentPreview }}</pre>
        </div>

        <!-- 参数区 -->
        <div v-if="hasParameters" class="code-section">
          <div class="section-title">参数</div>
          <pre class="code-block">{{ prettyParameters }}</pre>
        </div>

        <!-- 结果区 -->
        <div v-if="result" class="code-section">
          <div class="section-title">结果</div>
          <pre class="code-block">{{ result }}</pre>
        </div>
      </div>
    </transition>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { toolDisplayLabel, toolDisplayState } from '../../lib/toolStatus'

const props = defineProps<{
  name: string
  toolCallId: string
  parameters?: any
  status: 'inProgress' | 'executing' | 'complete'
  result?: string
}>()

// 默认设为 false（折叠状态），且去除了自动收起展开的 watch 逻辑
const isExpanded = ref(false)

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const params = computed(() => (props.parameters && typeof props.parameters === 'object' ? props.parameters : {}))
// 增加了备用字段容错
const title = computed(() => String(params.value.title || params.value.filename || 'generated_file'))
const fileFormat = computed(() => String(params.value.format || params.value.type || 'txt').toLowerCase())
const content = computed(() => String(params.value.content || ''))
const displayState = computed(() => toolDisplayState(props.status, props.result))

const statusLabel = computed(() => {
  return toolDisplayLabel(props.status, props.result, {
    executing: '写入中',
  })
})

const filenameLabel = computed(() => {
  // 如果 AI 传的 title 已经自带了后缀名，就直接用
  if (title.value.includes('.')) return title.value
  return `${title.value}.${fileFormat.value}`
})

const contentLengthLabel = computed(() => `${content.value.length} 字符`)

const contentPreview = computed(() => {
  const text = content.value.trim()
  if (!text) return ''
  return text.length > 600 ? `${text.slice(0, 600)}...` : text
})

const hasParameters = computed(() => Object.keys(params.value).length > 0)
const prettyParameters = computed(() => JSON.stringify(params.value, null, 2))
</script>

<style scoped>
/* 容器：统一阴影和圆角 */
.tool-call-card {
  margin: 12px 0;
  border: 1px solid var(--cc-agent-line);
  border-radius: 8px;
  background: var(--cc-agent-surface);
  overflow: hidden;
  transition: border-color 0.2s ease;
}

.tool-call-card:hover {
  border-color: var(--cc-agent-primary-border);
}

/* 头部：改为单行紧凑布局，整行可点击 */
.tool-header {
  width: 100%;
  border: 0;
  color: var(--cc-agent-text);
  font: inherit;
  text-align: left;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  cursor: pointer;
  background: var(--cc-agent-surface);
  user-select: none;
  transition: background-color 0.2s ease;
}

.tool-header:hover {
  background: var(--cc-agent-surface-alt);
}

.is-expanded .tool-header {
  border-bottom: 1px solid var(--cc-agent-line);
}

/* 头部左侧：状态图标 + 工具名 */
.tool-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
}

.status-icon.executing {
  color: var(--cc-agent-primary);
}

.status-icon.complete {
  color: var(--cc-agent-primary);
}

.status-icon.pending {
  color: #94a3b8;
}

.status-icon.waiting_permission {
  color: var(--cc-agent-primary);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}

.tool-name {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
}

/* 头部右侧：状态 Badge + 箭头 */
.tool-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tool-status-badge {
  font-size: 11.5px;
  font-weight: 500;
  padding: 2px 8px;
  border: 1px solid var(--cc-agent-line);
  border-radius: 8px;
}

.tool-status-badge.complete {
  background: var(--cc-agent-surface);
  color: var(--cc-agent-primary);
}

.tool-status-badge.executing {
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
}

.tool-status-badge.pending {
  background: #f1f5f9;
  color: #475569;
}

.tool-status-badge.waiting_permission {
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
}

.chevron-icon {
  width: 16px;
  height: 16px;
  color: #64748b;
  transition: transform 0.3s ease;
}

.chevron-icon.rotate {
  transform: rotate(180deg);
}

/* 展开的主体内容区 */
.tool-body {
  padding: 12px;
  background: var(--cc-agent-surface);
}

/* Meta 信息区（Filename, Format, Length） */
.meta-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.meta-row {
  display: flex;
  align-items: baseline;
  font-size: 12.5px;
}

.meta-label {
  width: 70px;
  /* 稍微加宽一点适应 Filename */
  flex-shrink: 0;
  color: #64748b;
  font-weight: 500;
}

.meta-value {
  color: #334155;
  word-break: break-all;
}

.meta-value.file-url {
  color: var(--cc-agent-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

/* 代码区块结构 */
.code-section {
  margin-top: 12px;
}

.section-title {
  font-size: 11px;
  font-weight: 700;
  color: #7b8798;
  letter-spacing: 0;
  margin-bottom: 6px;
}

.code-block {
  margin: 0;
  padding: 10px 12px;
  background: var(--cc-agent-surface-alt);
  color: #1f2937;
  border-radius: 8px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid var(--cc-agent-line);
}

/* 为深色代码块定制滚动条 */
.code-block::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.code-block::-webkit-scrollbar-track {
  background: transparent;
}

.code-block::-webkit-scrollbar-thumb {
  background: #c8d2df;
  border-radius: 4px;
}

.code-block::-webkit-scrollbar-thumb:hover {
  background: #aab7c6;
}

/* Vue 过渡动画类 */
.expand-enter-active,
.expand-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
  transform-origin: top;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  transform: scaleY(0.95);
}

.tool-header:focus-visible {
  outline: 2px solid var(--cc-agent-focus);
  outline-offset: -2px;
}

@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
  }

  .expand-enter-active,
  .expand-leave-active,
  .chevron-icon {
    transition: none;
  }
}
</style>
