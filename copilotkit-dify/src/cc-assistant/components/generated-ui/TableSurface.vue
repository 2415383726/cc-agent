<template>
  <BusinessSurface surface="table" :meta="spec.meta" :actions="spec.actions" :is-running="isRunning"
    @intent="emit('intent', $event)">
    <div class="table-container">
      <div v-if="sortedRows.length" class="table-viewport" tabindex="0" aria-label="结构化数据表格">
        <table>
          <thead>
            <tr>
              <th v-for="column in spec.columns" :key="column.key" :class="alignment(column)"
                :aria-sort="ariaSort(column)">
                <!-- 支持排序的表头 -->
                <button v-if="column.sortable" type="button" class="sort-btn" @click="toggleSort(column.key)">
                  <span>{{ column.label }}</span>
                  <span class="sort-icon" :class="sortDirectionClass(column.key)" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
                      stroke-linejoin="round">
                      <path d="M7 15l5 5 5-5" class="arrow-down" />
                      <path d="M7 9l5-5 5 5" class="arrow-up" />
                    </svg>
                  </span>
                </button>
                <!-- 普通表头 -->
                <span v-else class="th-label">{{ column.label }}</span>
              </th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="row in sortedRows" :key="row.id" class="table-row">
              <td v-for="column in spec.columns" :key="column.key" :class="alignment(column)">

                <!-- 标签类型 (Tags - 变成饱满的徽章) -->
                <div v-if="column.format === 'tags' && Array.isArray(row.values[column.key])" class="table-tags">
                  <span v-for="tag in row.values[column.key] as string[]" :key="tag" class="tag-pill">
                    {{ tag }}
                  </span>
                </div>

                <!-- 状态类型 (Status - 放大红绿灯) -->
                <span v-else-if="column.format === 'status'" class="status-text"
                  :class="getStatusColorClass(displayValue(row.values[column.key]))">
                  <span class="status-dot"></span>
                  {{ displayValue(row.values[column.key]) || '—' }}
                </span>

                <!-- 🌟 数字类型 (Number - 专属放大加粗) -->
                <span v-else-if="column.format === 'number'" class="cell-text is-numeric">
                  {{ displayValue(row.values[column.key]) || '—' }}
                </span>

                <!-- 普通文本 -->
                <span v-else class="cell-text">
                  {{ displayValue(row.values[column.key]) || '—' }}
                </span>

              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 空状态 -->
      <div v-else class="table-empty">
        <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <line x1="3" y1="9" x2="21" y2="9" />
          <line x1="9" y1="21" x2="9" y2="9" />
        </svg>
        <p>{{ spec.emptyText || '暂无数据' }}</p>
      </div>
    </div>
  </BusinessSurface>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import BusinessSurface from './BusinessSurface.vue'
import { displayValue, type TableSpec } from '../../lib/structuredContent'

const props = withDefaults(defineProps<{ spec: TableSpec; isRunning?: boolean }>(), { isRunning: false })
const emit = defineEmits<{ intent: [prompt: string] }>()

const sortKey = ref('')
const sortDirection = ref<'ascending' | 'descending'>('ascending')

const sortedRows = computed(() => {
  if (!sortKey.value) return props.spec.rows
  const direction = sortDirection.value === 'ascending' ? 1 : -1
  return [...props.spec.rows].sort((left, right) => {
    const a = left.values[sortKey.value]
    const b = right.values[sortKey.value]
    if (typeof a === 'number' && typeof b === 'number') return (a - b) * direction
    return displayValue(a).localeCompare(displayValue(b), 'zh-CN', { numeric: true }) * direction
  })
})

function toggleSort(key: string) {
  if (sortKey.value === key) {
    sortDirection.value = sortDirection.value === 'ascending' ? 'descending' : 'ascending'
  } else {
    sortKey.value = key
    sortDirection.value = 'ascending'
  }
}

// 供排序 SVG 使用的类名
function sortDirectionClass(key: string) {
  if (sortKey.value !== key) return 'is-default'
  return sortDirection.value === 'ascending' ? 'is-asc' : 'is-desc'
}

function ariaSort(column: TableSpec['columns'][number]) { return column.sortable ? (sortKey.value === column.key ? sortDirection.value : 'none') : undefined }
function alignment(column: TableSpec['columns'][number]) { return `align-${column.align || (column.format === 'number' ? 'end' : 'start')}` }

// 智能状态颜色推断
function getStatusColorClass(statusText: string): string {
  if (!statusText) return 'status-default'
  const text = statusText.toLowerCase()
  if (/正常|完成|优秀|通过|成功|上线|绿/.test(text)) return 'status-success'
  if (/风险|延期|拒绝|失败|警告|红|差/.test(text)) return 'status-danger'
  if (/需改进|未开始|审核中|待定|黄|橙/.test(text)) return 'status-warning'
  // 进行中/良好 默认为蓝
  return 'status-info'
}
</script>

<style scoped>
:focus-visible {
  outline: none;
}

.table-container {
  border-radius: 8px;
  border: 1px solid var(--cc-agent-line, #e5e7eb);
  background: var(--cc-agent-surface, #ffffff);
  overflow: hidden;
  /* 让圆角能裁切内部的表格背景 */
}

.table-viewport {
  max-height: 560px;
  overflow-x: auto;
  overflow-y: auto;
  outline: none;
}

.table-viewport:focus-visible {
  box-shadow: inset 0 0 0 2px var(--cc-agent-focus, #3b82f6);
}

/* 优雅滚动条 */
.table-viewport::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.table-viewport::-webkit-scrollbar-track {
  background: transparent;
}

.table-viewport::-webkit-scrollbar-thumb {
  background: rgba(144, 147, 153, 0.3);
  border-radius: 4px;
}

.table-viewport::-webkit-scrollbar-thumb:hover {
  background: rgba(144, 147, 153, 0.5);
}

table {
  width: 100%;
  min-width: 680px;
  /* 随着字号放大，表格最小宽度也要撑开 */
  border-collapse: separate;
  border-spacing: 0;
  font-size: 15px;
  /* 🌟 整体基础字号提升 */
  line-height: 1.5;
  color: var(--cc-agent-text-main, #111827);
  /* 极深灰，增强对比度 */
}

/* ================= 表头样式优化 ================= */
th {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 16px 20px;
  /* 🌟 增加表头的呼吸感 */
  background: var(--cc-agent-surface-alt, #f9fafb);
  border-bottom: 2px solid var(--cc-agent-line, #e5e7eb);
  /* 表头底线加粗，压住数据 */
  color: var(--cc-agent-text-main, #374151);
  /* 表头颜色加深 */
  font-size: 14px;
  font-weight: 600;
  /* 加粗 */
  white-space: nowrap;
}

/* 🌟 排序按钮对齐修复 */
th.align-start .sort-btn {
  justify-content: flex-start;
}

th.align-center .sort-btn {
  justify-content: center;
}

th.align-end .sort-btn {
  justify-content: flex-end;
}

.sort-btn {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 6px;
  border: 0;
  padding: 4px;
  margin: -4px;
  /* 扩大点击热区 */
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  transition: background-color 0.2s;
}

.sort-btn:hover {
  background: rgba(0, 0, 0, 0.04);
}

.sort-icon {
  width: 16px;
  height: 16px;
  color: #c0c4cc;
  flex-shrink: 0;
}

.sort-icon svg {
  width: 100%;
  height: 100%;
  display: block;
}

.sort-icon.is-asc .arrow-up {
  stroke: var(--cc-agent-primary-strong, #1677ff);
  stroke-width: 2.5;
}

.sort-icon.is-asc .arrow-down {
  opacity: 0.3;
}

.sort-icon.is-desc .arrow-down {
  stroke: var(--cc-agent-primary-strong, #1677ff);
  stroke-width: 2.5;
}

.sort-icon.is-desc .arrow-up {
  opacity: 0.3;
}

/* ================= 单元格内容优化 ================= */
td {
  padding: 16px 20px;
  /* 🌟 大幅增加行高和列间距 */
  border-bottom: 1px solid var(--cc-agent-muted-line, #f3f4f6);
  vertical-align: middle;
  transition: background-color 0.15s ease;
}

tbody tr.table-row:hover td {
  background-color: var(--cc-agent-hover-bg, #f8fafc);
}

tbody tr:last-child td {
  border-bottom: 0;
}

.align-start {
  text-align: left;
}

.align-center {
  text-align: center;
}

.align-end {
  text-align: right;
}

.cell-text {
  font-weight: 500;
  /* 普通文字微微加粗，质感更好 */
}

/* 🌟 数字享有特权：更大、更粗、等宽 */
.is-numeric {
  font-family: var(--cc-agent-data-font-family, 'Menlo', 'Monaco', monospace);
  font-variant-numeric: tabular-nums;
  font-size: 16px;
  /* 数字特权放大 */
  font-weight: 600;
  color: var(--cc-agent-primary-strong, #1677ff);
  /* 给重要数据上点色 */
}

/* ================= 标签 (Tags) 优化 ================= */
.table-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  /* 间距拉大 */
}

.tag-pill {
  border-radius: 6px;
  padding: 4px 10px;
  /* 变胖变饱满 */
  background: var(--cc-agent-surface-alt, #f3f4f6);
  /* 改为低调的浅灰底 */
  color: var(--cc-agent-text, #4b5563);
  font-size: 13px;
  /* 字号放大 */
  font-weight: 500;
  border: 1px solid rgba(0, 0, 0, 0.05);
}

/* ================= 状态 (Status) 语义化指示器 ================= */
.status-text {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  /* 加粗 */
  font-size: 15px;
  /* 字号放大 */
}

.status-dot {
  width: 8px;
  /* 红绿灯放大 */
  height: 8px;
  border-radius: 50%;
  background-color: currentColor;
}

.status-success {
  color: #059669;
}

.status-success .status-dot {
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
}

.status-danger {
  color: #dc2626;
}

.status-danger .status-dot {
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.2);
}

.status-warning {
  color: #d97706;
}

.status-warning .status-dot {
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.2);
}

.status-info {
  color: #2563eb;
}

.status-info .status-dot {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}

.status-default {
  color: var(--cc-agent-muted, #6b7280);
}

/* ================= 空状态优化 ================= */
.table-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--cc-agent-muted, #9ca3af);
  font-size: 14px;
}

.empty-icon {
  width: 40px;
  height: 40px;
  margin-bottom: 12px;
  opacity: 0.5;
}
</style>