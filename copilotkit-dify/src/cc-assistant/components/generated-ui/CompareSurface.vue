<template>
  <BusinessSurface surface="compare" :meta="spec.meta" :actions="spec.actions" :is-running="isRunning"
    @intent="emit('intent', $event)">
    <div class="compare-container">
      <div class="compare-viewport" tabindex="0" aria-label="对象对比表">
        <table>
          <thead>
            <tr>
              <th class="corner-header">对比维度</th>
              <th v-for="subject in spec.subjects" :key="subject.id" class="subject-header">
                <strong>{{ subject.label }}</strong>
                <small v-if="subject.description">{{ subject.description }}</small>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="criterion in spec.criteria" :key="criterion.id" class="data-row">
              <th class="criterion-header">
                <strong>{{ criterion.label }}</strong>
                <small v-if="criterion.note">{{ criterion.note }}</small>
              </th>
              <td v-for="subject in spec.subjects" :key="subject.id"
                :class="{ 'highlighted-cell': criterion.highlight === subject.id }">
                <div class="cell-content">
                  {{ displayValue(criterion.values[subject.id]) || '—' }}
                </div>

                <!-- 🌟 高亮徽章重塑：更像一个专业的“优势/推荐”标签 -->
                <div v-if="criterion.highlight === subject.id" class="compare-mark">
                  <svg class="mark-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                    stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                  优势
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </BusinessSurface>
</template>

<script setup lang="ts">
import BusinessSurface from './BusinessSurface.vue'
import { displayValue, type CompareSpec } from '../../lib/structuredContent'

withDefaults(defineProps<{ spec: CompareSpec; isRunning?: boolean }>(), { isRunning: false })
const emit = defineEmits<{ intent: [prompt: string] }>()
</script>

<style scoped>
.compare-container {
  /* 外层容器增加边框和圆角，看起来像一份完整的报告卡片 */
  border: 1px solid var(--cc-agent-line, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
  background: var(--cc-agent-surface, #ffffff);
}

.compare-viewport {
  overflow-x: auto;
  overflow-y: auto;
  max-height: 600px;
  /* 限制最高度，保证表头能在内部滚动时吸顶 */
  outline: none;
}

.compare-viewport:focus-visible {
  box-shadow: inset 0 0 0 2px var(--cc-agent-focus, #3b82f6);
}

/* 优雅滚动条 */
.compare-viewport::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.compare-viewport::-webkit-scrollbar-track {
  background: transparent;
}

.compare-viewport::-webkit-scrollbar-thumb {
  background: rgba(144, 147, 153, 0.3);
  border-radius: 4px;
}

.compare-viewport::-webkit-scrollbar-thumb:hover {
  background: rgba(144, 147, 153, 0.5);
}

table {
  width: 100%;
  min-width: 800px;
  /* 🌟 放大内容后，表格最小宽度必须撑开，防止挤压变形 */
  border-collapse: separate;
  border-spacing: 0;
  font-size: 15px;
  /* 基础字号提升 */
  line-height: 1.5;
}

/* ================= 单元格基础规范 ================= */
th,
td {
  border-right: 1px solid var(--cc-agent-muted-line, #f3f4f6);
  border-bottom: 1px solid var(--cc-agent-muted-line, #f3f4f6);
  padding: 20px 24px;
  /* 🌟 大幅增加留白，呼吸感拉满 */
  text-align: left;
  vertical-align: top;
}

/* 去掉最右和最下的边框，由外层容器接管 */
tr> :last-child {
  border-right: 0;
}

tbody tr:last-child>* {
  border-bottom: 0;
}

/* ================= 表头优化 (顶部维度的对象) ================= */
thead th {
  background: var(--cc-agent-surface-alt, #f9fafb);
  position: sticky;
  top: 0;
  z-index: 10;
  border-bottom: 2px solid var(--cc-agent-line, #e5e7eb);
  /* 顶部表头底边线加粗，压住下面数据 */
}

.subject-header strong {
  display: block;
  font-size: 16px;
  /* 🌟 顶部主对象（如“慧客通CRM”）放大 */
  font-weight: 700;
  color: var(--cc-agent-text-main, #111827);
}

.subject-header small {
  display: block;
  margin-top: 6px;
  color: var(--cc-agent-muted, #6b7280);
  font-size: 13px;
  font-weight: 400;
}

/* ================= 左侧栏优化 (对比指标) ================= */
tbody th {
  background: var(--cc-agent-surface, #ffffff);
}

/* 左侧冻结列 */
thead th.corner-header,
tbody th.criterion-header {
  position: sticky;
  left: 0;
  z-index: 11;
  width: 160px;
  /* 🌟 加宽左侧列 */
  background: var(--cc-agent-surface-alt, #f9fafb);
  /* 左侧列也使用浅灰底色，与数据区隔开 */
}

/* 左上角交叉点层级最高 */
thead th.corner-header {
  z-index: 12;
  font-size: 14px;
  color: var(--cc-agent-muted, #6b7280);
  font-weight: 600;
  vertical-align: bottom;
  /* 交叉点文字靠下对齐更好看 */
  padding-bottom: 16px;
}

.criterion-header strong {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: var(--cc-agent-text-main, #374151);
}

.criterion-header small {
  display: block;
  margin-top: 6px;
  color: var(--cc-agent-muted, #9ca3af);
  font-size: 12px;
  font-weight: 400;
}

/* ================= 数据区优化 ================= */
td {
  color: var(--cc-agent-text-main, #1f2937);
  font-size: 16px;
  /* 🌟 数据字号看齐 16px */
  font-weight: 500;
  transition: background-color 0.2s ease;
}

tbody tr.data-row:hover td {
  background-color: var(--cc-agent-surface-hover, #f8fafc);
  /* 增加悬停行高亮，防止看走眼 */
}

/* ================= 🌟 胜出/高亮 单元格 (决策核心) ================= */
td.highlighted-cell {
  background-color: var(--cc-agent-primary-soft, #eff6ff);
  /* 浅蓝色背景垫底 */
  color: var(--cc-agent-primary-strong, #1d4ed8);
  font-weight: 700;
  /* 数据加粗 */
  border-left: 2px solid var(--cc-agent-primary-strong, #3b82f6);
  /* 左侧增加一个细细的主题色高亮条，极其有质感 */
  /* 因为加了 border-left，微调 padding 保证文字对齐 */
  padding-left: 22px;
}

/* 悬停时高亮单元格也要保持颜色 */
tbody tr.data-row:hover td.highlighted-cell {
  background-color: #e0effe;
}

/* 胜出徽章 */
.compare-mark {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 12px;
  /* 和上面的数据拉开距离 */
  border-radius: 999px;
  /* 胶囊型圆角 */
  padding: 4px 10px;
  background: var(--cc-agent-primary-strong, #2563eb);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.5px;
  box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
  /* 加一点点弥散阴影，浮现感 */
}

.mark-icon {
  width: 12px;
  height: 12px;
}
</style>