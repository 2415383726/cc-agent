<template>
  <section class="search-tool-card" :class="displayState">
    <header class="search-tool-header">
      <div class="search-tool-title">
        <span class="search-tool-icon" :class="{ 'is-loading': displayState === 'executing' }" aria-hidden="true">
          <svg viewBox="0 0 20 20" fill="none" focusable="false">
            <circle cx="8.5" cy="8.5" r="4.75" />
            <path d="M12.25 12.25 16 16" />
          </svg>
        </span>
        <div class="search-tool-heading">
          <div class="search-tool-title-row">
            <strong>{{ name }}</strong>
            <span v-if="query" class="search-query-tag" :title="query">
              "{{ query }}"
            </span>
          </div>
          <span>{{ resultCountLabel }}</span>
        </div>
      </div>

      <div class="search-tool-meta">
        <span class="search-status" :class="displayState">{{ statusLabel }}</span>
      </div>
    </header>

    <div v-if="hits.length" class="search-carousel">
      <button class="search-nav" type="button" aria-label="上一条搜索结果" title="上一条" :disabled="activeIndex <= 0"
        @click="scrollToResult(activeIndex - 1)">
        <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
          <path d="M12.5 5 7.5 10l5 5" />
        </svg>
      </button>

      <div ref="trackRef" class="search-results" @scroll="handleScroll">
        <article v-for="(hit, index) in hits" :key="`${hit.title}-${index}`" class="search-result is-clickable"
          :class="{ active: index === activeIndex }" role="button" tabindex="0"
          :aria-label="`查看搜索结果：${hit.title}`" @click="openDetail(hit)"
          @keydown.enter.prevent="openDetail(hit)" @keydown.space.prevent="openDetail(hit)">
          <div class="search-result-topline">
            <span class="search-result-index">{{ index + 1 }}</span>
            <span class="search-result-title" :title="hit.title">{{ hit.title }}</span>
            <span v-if="hit.scoreLabel" class="search-score">{{ hit.scoreLabel }}</span>
          </div>

          <p class="search-snippet">{{ hit.content }}</p>

          <div v-if="hit.documentName && hit.documentName !== hit.title" class="search-document">
            <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M4 2.5C4 1.67157 4.67157 1 5.5 1H9.62132C10.0191 1 10.4006 1.15804 10.6819 1.43934L13.5606 4.31802C13.8419 4.59932 14 4.98086 14 5.37868V13.5C14 14.3284 13.3284 15 12.5 15H5.5C4.67157 15 4 14.3284 4 13.5V2.5Z"
                stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M9.5 1V4.5C9.5 5.05228 9.94772 5.5 10.5 5.5H14" stroke="currentColor" stroke-width="1.2"
                stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            {{ hit.documentName }}
          </div>
        </article>
      </div>

      <button class="search-nav" type="button" aria-label="下一条搜索结果" title="下一条"
        :disabled="activeIndex >= hits.length - 1" @click="scrollToResult(activeIndex + 1)">
        <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
          <path d="m7.5 5 5 5-5 5" />
        </svg>
      </button>
    </div>

    <div v-else class="search-empty">
      <span>{{ fallbackText }}</span>
    </div>
  </section>

  <!-- 全局详情弹窗 -->
  <Teleport to="body">
    <Transition name="fade-scale">
      <div v-if="selectedHit" class="search-modal-overlay" @click.self="closeDetail">
        <div class="search-modal-container" role="dialog" aria-modal="true" aria-label="搜索结果详情">
          <header class="search-modal-header">
            <div class="search-modal-title-area">
              <span class="search-modal-badge">片段详情</span>
              <h3 class="search-modal-title" :title="modalTitle">{{ modalTitle }}</h3>
            </div>
            <button type="button" class="search-modal-close" @click="closeDetail" aria-label="关闭搜索结果详情">
              <svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"
                  stroke-linejoin="round" />
              </svg>
            </button>
          </header>

          <div class="search-modal-body">
            <!-- 优化点：弹窗正文支持安全的高亮渲染 -->
            <p class="search-modal-text" v-html="highlightText(selectedHit.content, query)"></p>
          </div>

          <footer class="search-modal-footer">
            <div class="search-modal-source">
              <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M4 2.5C4 1.67157 4.67157 1 5.5 1H9.62132C10.0191 1 10.4006 1.15804 10.6819 1.43934L13.5606 4.31802C13.8419 4.59932 14 4.98086 14 5.37868V13.5C14 14.3284 13.3284 15 12.5 15H5.5C4.67157 15 4 14.3284 4 13.5V2.5Z"
                  stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
                <path d="M9.5 1V4.5C9.5 5.05228 9.94772 5.5 10.5 5.5H14" stroke="currentColor" stroke-width="1.2"
                  stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              <span>{{ selectedHit.documentName || '未知来源' }}</span>
            </div>
            <span v-if="selectedHit.scoreLabel" class="search-modal-score">
              匹配度：{{ selectedHit.scoreLabel }}
            </span>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { toolDisplayState } from '../../lib/toolStatus'

type SearchHit = {
  title: string
  documentName: string
  content: string
  scoreLabel: string
}

const props = defineProps<{
  name: string
  toolCallId: string
  args?: unknown
  parameters?: unknown
  status: 'inProgress' | 'executing' | 'complete' | 'waiting_permission' | string
  result?: unknown
}>()

const trackRef = ref<HTMLElement | null>(null)
const activeIndex = ref(0)

const params = computed(() => props.args || props.parameters || {})
const query = computed(() => String((params.value as any).query || '').trim())

const resultText = computed(() => stringifyResult(props.result))
const parsedResult = computed(() => parseMaybeJson(props.result))
const hits = computed(() => extractHits(parsedResult.value))


const normalizedStatus = computed(() => {
  const status = String(props.status || '')
  return status === 'inProgress' ? 'executing' : status
})

const displayState = computed(() => toolDisplayState(normalizedStatus.value, resultText.value))

const statusLabel = computed(() => {
  if (displayState.value === 'executing') return '搜索中'
  if (displayState.value === 'complete') return '已完成'
  if (displayState.value === 'waiting_permission') return '等待授权'
  return '准备中'
})

const resultCountLabel = computed(() => `${hits.value.length} 条结果`)

const modalTitle = computed(() => query.value || selectedHit.value?.title || '搜索结果')

const fallbackText = computed(() => {
  const text = resultText.value.trim()
  if (!text) return displayState.value === 'executing' ? '正在检索知识库...' : '没有可展示的搜索结果'
  return text.length > 220 ? `${text.slice(0, 220)}...` : text
})

function scrollToResult(index: number) {
  const nextIndex = Math.max(0, Math.min(index, hits.value.length - 1))
  activeIndex.value = nextIndex
  const track = trackRef.value
  const target = track?.children.item(nextIndex) as HTMLElement | null
  target?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
}

function handleScroll() {
  const track = trackRef.value
  if (!track?.children.length) return
  const midpoint = track.scrollLeft + track.clientWidth / 2
  let nearestIndex = 0
  let nearestDistance = Number.POSITIVE_INFINITY

  Array.from(track.children).forEach((child, index) => {
    const element = child as HTMLElement
    const center = element.offsetLeft + element.offsetWidth / 2
    const distance = Math.abs(center - midpoint)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearestIndex = index
    }
  })
  activeIndex.value = nearestIndex
}

// --- 弹窗逻辑 ---
const selectedHit = ref<SearchHit | null>(null)

function openDetail(hit: SearchHit) {
  selectedHit.value = hit
  document.body.style.overflow = 'hidden'
}

function closeDetail() {
  selectedHit.value = null
  document.body.style.overflow = ''
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && selectedHit.value) {
    closeDetail()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (selectedHit.value) document.body.style.overflow = ''
})


// --- 核心：安全的高亮函数 ---
// 1. 防御 XSS 注入
function escapeHtml(unsafe: string) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// 2. 精准匹配与高亮
function highlightText(text: string, q: string) {
  const escapedText = escapeHtml(text)
  if (!q) return escapedText // 如果没有 query，直接返回安全的转义文本

  // 转义查询词中的正则特殊字符，防止正则执行错误
  const escapedQuery = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

  // 创建正则（gi 代表全局 + 忽略大小写）
  const regex = new RegExp(`(${escapedQuery})`, 'gi')

  // 使用 CSS class `highlight-match` 进行包裹渲染
  return escapedText.replace(regex, '<mark class="highlight-match">$1</mark>')
}


// --- 辅助工具函数 ---
function parseMaybeJson(value: unknown) {
  if (value && typeof value === 'object') return value
  const text = String(value ?? '').trim()
  if (!text || (!text.startsWith('{') && !text.startsWith('['))) return text
  try {
    return JSON.parse(text)
  } catch (_) {
    return text
  }
}

function stringifyResult(value: unknown) {
  if (typeof value === 'string') return value
  if (value == null) return ''
  try {
    return JSON.stringify(value)
  } catch (_) {
    return String(value)
  }
}

function extractHits(value: unknown): SearchHit[] {
  const records = resultRecords(value)
  return records.map((record, index) => normalizeHit(record, index)).filter((hit) => hit.content)
}

function resultRecords(value: unknown): Record<string, any>[] {
  if (Array.isArray(value)) return value.filter(isRecord)
  if (!isRecord(value)) return []

  const possibleLists = [value.result, value.results, value.data, value.items]
  for (const list of possibleLists) {
    if (Array.isArray(list)) return list.filter(isRecord)
  }
  return []
}

function normalizeHit(record: Record<string, any>, index: number): SearchHit {
  const metadata = isRecord(record.metadata) ? record.metadata : {}
  const title = String(record.title || metadata.title || metadata.document_name || `结果 ${index + 1}`).trim()
  const documentName = String(metadata.document_name || metadata.source || title).trim()
  const content = String(record.content || record.text || record.snippet || record.page_content || '').trim()
  const score = Number(metadata.score ?? record.score)

  return {
    title,
    documentName,
    content,
    scoreLabel: Number.isFinite(score) ? formatScore(score) : '',
  }
}

function formatScore(score: number) {
  const percentage = score <= 1 ? score * 100 : score
  return `${percentage.toFixed(1)}%`
}

function isRecord(value: unknown): value is Record<string, any> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
</script>

<style scoped>
/* 原有的全部 scoped 样式保持不变 */
.search-tool-card {
  margin: 12px 0;
  border: 1px solid var(--cc-agent-line);
  border-radius: 10px;
  background: #ffffff;
  overflow: hidden;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.search-tool-card:hover,
.search-tool-card.executing {
  border-color: var(--cc-agent-primary-border);
}

.search-tool-card.executing {
  box-shadow: inset 3px 0 0 var(--cc-agent-primary);
}

.search-tool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid #edf1f6;
}

.search-tool-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.search-tool-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  border: 1px solid var(--cc-agent-primary-border);
  border-radius: 8px;
  color: var(--cc-agent-primary);
  background: var(--cc-agent-primary-soft);
}

@keyframes pulse-spin {
  0% {
    transform: scale(0.95) rotate(0deg);
    opacity: 0.8;
  }

  50% {
    transform: scale(1.05) rotate(180deg);
    opacity: 1;
  }

  100% {
    transform: scale(0.95) rotate(360deg);
    opacity: 0.8;
  }
}

.search-tool-icon.is-loading svg {
  animation: pulse-spin 2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

.search-tool-icon svg {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: transform 0.3s ease;
}

.search-tool-heading {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.search-tool-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-tool-heading strong {
  color: #0f172a;
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.2;
}

.search-query-tag {
  color: var(--cc-agent-primary);
  background: var(--cc-agent-primary-soft);
  font-size: 11.5px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
  max-width: 120px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.search-tool-heading>span {
  color: #64748b;
  font-size: 11.5px;
  line-height: 1.2;
}

.search-tool-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.search-status {
  flex: 0 0 auto;
  border: 1px solid var(--cc-agent-line);
  border-radius: 6px;
  background: #ffffff;
  color: var(--cc-agent-primary);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  padding: 4px 8px;
}

.search-status.pending {
  color: #526071;
  background: var(--cc-agent-surface-alt);
}

.search-status.executing,
.search-status.waiting_permission {
  color: var(--cc-agent-primary);
  background: var(--cc-agent-primary-soft);
}

.search-carousel {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 28px;
  gap: 8px;
  align-items: center;
  padding: 12px 14px 14px;
}

.search-nav {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 64px;
  border: 1px solid var(--cc-agent-line);
  border-radius: 8px;
  background: #ffffff;
  color: #526071;
  cursor: pointer;
  opacity: 0;
  transform: scale(0.95);
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, opacity 0.2s ease, transform 0.2s ease;
}

.search-carousel:hover .search-nav {
  opacity: 1;
  transform: scale(1);
}

.search-nav:hover:not(:disabled) {
  border-color: var(--cc-agent-primary-border);
  color: var(--cc-agent-primary);
  background: #f0f7ff;
}

.search-nav:disabled {
  cursor: default;
  color: #c8d2df;
  background: transparent;
  opacity: 0.3 !important;
}

.search-nav svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.search-results {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(240px, 82%);
  gap: 12px;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scroll-snap-type: x mandatory;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
  padding-bottom: 2px;
}

.search-results::-webkit-scrollbar {
  height: 4px;
}

.search-results::-webkit-scrollbar-track {
  background: transparent;
}

.search-results::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

.search-result {
  min-height: 118px;
  max-height: 142px;
  scroll-snap-align: center;
  border: 1px solid var(--cc-agent-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
  overflow: hidden;
  transition: border-color 0.2s ease, background-color 0.2s ease, transform 0.15s ease;
}

.search-result.is-clickable {
  cursor: pointer;
}

.search-result.is-clickable:hover {
  background-color: #f8fafc;
}

.search-result.is-clickable:active {
  transform: scale(0.98);
}

.search-result.active {
  border-color: var(--cc-agent-primary-border);
}

.search-result-topline {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin-bottom: 8px;
}

.search-result-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  border-radius: 6px;
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.search-result-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-score {
  font-variant-numeric: tabular-nums;
  color: #64748b;
  font-size: 11px;
  font-weight: 500;
}

.search-snippet {
  display: -webkit-box;
  margin: 0;
  color: #334155;
  font-size: 12.5px;
  line-height: 1.6;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.search-document {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  color: #64748b;
  font-size: 11.5px;
  overflow: hidden;
}

.search-document svg {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: #94a3b8;
}

.search-empty {
  padding: 14px;
}

.search-empty span {
  display: block;
  max-height: 120px;
  overflow: auto;
  border: 1px solid var(--cc-agent-line);
  border-radius: 8px;
  background: #f8fafc;
  color: #475569;
  font-size: 12.5px;
  line-height: 1.6;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

<!-- 第二个 Style: 不加 scoped 的全局样式，专供弹窗和高亮使用 -->
<style>
/* 新增：高亮词语的美化样式 */
.highlight-match {
  background-color: #fef08a;
  /* 舒适明亮的淡黄色，符合传统的荧光笔直觉 */
  color: #0f172a;
  border-radius: 2px;
  padding: 0 2px;
  font-weight: 500;
}

/* 弹窗样式 */
.search-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 20px;
  box-sizing: border-box;
}

.search-modal-container {
  width: 100%;
  max-width: 640px;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  max-height: 85vh;
  overflow: hidden;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

.search-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #edf1f6;
}

.search-modal-title-area {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}

.search-modal-badge {
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 6px;
  white-space: nowrap;
}

.search-modal-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.search-modal-close {
  background: transparent;
  border: none;
  color: #64748b;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, opacity 0.2s ease, transform 0.2s ease;
  margin-left: 12px;
}

.search-modal-close:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.search-modal-close svg {
  width: 18px;
  height: 18px;
}

.search-modal-body {
  padding: 24px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}

.search-modal-body::-webkit-scrollbar {
  width: 6px;
}

.search-modal-body::-webkit-scrollbar-track {
  background: transparent;
}

.search-modal-body::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

.search-modal-text {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.8;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
}

.search-modal-footer {
  padding: 14px 20px;
  background: #f8fafc;
  border-top: 1px solid #edf1f6;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.search-modal-source {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.search-modal-source svg {
  width: 14px;
  height: 14px;
}

.search-modal-score {
  color: #64748b;
  font-size: 12px;
  font-weight: 500;
}

.fade-scale-enter-active,
.fade-scale-leave-active {
  transition: opacity 0.2s ease;
}

.fade-scale-enter-active .search-modal-container,
.fade-scale-leave-active .search-modal-container {
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.fade-scale-enter-from,
.fade-scale-leave-to {
  opacity: 0;
}

.fade-scale-enter-from .search-modal-container,
.fade-scale-leave-to .search-modal-container {
  transform: scale(0.95) translateY(10px);
}

.search-nav:focus-visible,
.search-result:focus-visible,
.search-modal-close:focus-visible {
  outline: 2px solid var(--cc-agent-focus);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .search-tool-icon.is-loading {
    animation: none;
  }

  .search-nav,
  .search-result,
  .search-modal-close,
  .fade-scale-enter-active,
  .fade-scale-leave-active {
    transition: none;
  }
}
</style>
