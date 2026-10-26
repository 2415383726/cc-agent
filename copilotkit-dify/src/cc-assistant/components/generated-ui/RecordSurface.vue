<template>
  <BusinessSurface surface="record" :meta="spec.meta" :actions="spec.actions" :is-running="isRunning"
    @intent="emit('intent', $event)">
    <div class="record-container">
      <section v-for="(section, index) in spec.sections" :key="section.title || index" class="record-section">

        <!-- 模块标题 (显著放大，加粗) -->
        <h4 v-if="section.title" class="section-title">
          <span class="title-indicator"></span>
          {{ section.title }}
        </h4>

        <!-- 数据看板网格 -->
        <dl class="record-grid">
          <div v-for="field in section.fields" :key="field.label" class="record-field">
            <!-- 字段名 (作为辅助信息，适度放大) -->
            <dt class="field-label">{{ field.label }}</dt>

            <!-- 标签 (Tags - 放大并增加点击感) -->
            <dd v-if="field.format === 'tags' && Array.isArray(field.value)" class="field-value tags-wrapper">
              <span v-for="tag in field.value" :key="tag" class="tag-badge">{{ tag }}</span>
            </dd>

            <!-- 状态 (Status - 放大指示器) -->
            <dd v-else-if="field.format === 'status'" class="field-value status-wrapper"
              :class="getStatusTheme(field.value)">
              <span class="status-dot"></span>
              {{ displayValue(field.value) || '—' }}
            </dd>

            <!-- 核心数字 (🌟 KPI级别放大，极粗) -->
            <dd v-else-if="field.format === 'number'" class="field-value is-numeric">
              {{ displayValue(field.value) || '—' }}
            </dd>

            <!-- 普通文本 (加粗放大) -->
            <dd v-else class="field-value">
              {{ displayValue(field.value) || '—' }}
            </dd>
          </div>
        </dl>

      </section>
    </div>
  </BusinessSurface>
</template>

<script setup lang="ts">
import BusinessSurface from './BusinessSurface.vue'
import { displayValue, type RecordSpec } from '../../lib/structuredContent'

withDefaults(defineProps<{ spec: RecordSpec; isRunning?: boolean }>(), { isRunning: false })
const emit = defineEmits<{ intent: [prompt: string] }>()

function getStatusTheme(val: any) {
  const text = displayValue(val) || ''
  if (/正常|优秀|完成|通过|成功/.test(text)) return 'theme-success'
  if (/风险|异常|拒绝|失败|需改进/.test(text)) return 'theme-danger'
  if (/未开始|待定|取消|关闭/.test(text)) return 'theme-neutral'
  return 'theme-primary'
}
</script>

<style scoped>
.record-container {
  display: flex;
  flex-direction: column;
}

/* ================= 模块区域 ================= */
.record-section {
  padding: 24px;
  /* 🌟 进一步增加外围呼吸感，撑起大卡片 */
}

.record-section+.record-section {
  border-top: 1px solid var(--cc-agent-muted-line, #e5e7eb);
}

/* 🌟 标题：更大，更黑，更有分量 */
.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 24px 0;
  /* 标题与内容的间距拉大 */
  color: var(--cc-agent-text-main, #111827);
  /* 极深的黑灰色 */
  font-size: 16px;
  /* 从14px 提至 16px */
  font-weight: 700;
  /* 加到最粗 */
}

.title-indicator {
  width: 4px;
  /* 加粗指示条 */
  height: 16px;
  border-radius: 2px;
  background-color: var(--cc-agent-primary-strong, #1677ff);
}

/* ================= 数据网格 ================= */
.record-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  row-gap: 24px;
  /* 🌟 行间距拉大，因为字变大了 */
  column-gap: 48px;
  /* 列间距进一步拉大，防止大字打架 */
  margin: 0;
}

.record-field {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* 🌟 Label (字段名)：作为数据的绿叶 */
.field-label {
  margin: 0 0 8px 0;
  /* 与数据拉开一点点距离 */
  color: var(--cc-agent-muted, #6b7280);
  font-size: 14px;
  /* 从13px 提至 14px */
  font-weight: 400;
}

/* 🌟 Value (普通数据)：变成核心主角 */
.field-value {
  margin: 0;
  color: var(--cc-agent-text-main, #111827);
  font-size: 16px;
  /* 🌟 从14px 提至 16px，一目了然 */
  font-weight: 600;
  /* 提升字重，充满力量感 */
  line-height: 1.4;
  overflow-wrap: break-word;
  word-break: break-all;
}

/* 🌟 核心数字 (Number)：KPI 看板级别的特权放大 */
.is-numeric {
  font-family: var(--cc-agent-data-font-family, 'Menlo', 'Monaco', monospace);
  font-variant-numeric: tabular-nums;
  font-size: 22px;
  /* 🌟🌟 直接飙到 22px，领导最爱看的数据 */
  font-weight: 700;
  /* 最粗字重 */
  color: var(--cc-agent-primary-strong, #1677ff);
  /* 给数字上主题色，极度吸睛 */
  line-height: 1.2;
}

/* ================= 标签与状态 ================= */

.tags-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  /* 间距拉大 */
  margin-top: 2px;
}

.tag-badge {
  padding: 4px 12px;
  /* 变胖变饱满 */
  border-radius: 6px;
  background: var(--cc-agent-surface-alt, #f3f4f6);
  color: var(--cc-agent-text, #374151);
  font-size: 13px;
  /* 变大 */
  font-weight: 500;
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.status-wrapper {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  /* 🌟 状态也跟着放大 */
  font-weight: 700;
  /* 加粗突出状态 */
}

.status-dot {
  width: 8px;
  /* 圆点放大 */
  height: 8px;
  border-radius: 50%;
  background-color: currentColor;
}

/* 状态颜色 (调深了一点点，在大字号下更沉稳) */
.theme-success {
  color: #059669;
}

.theme-success .status-dot {
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
}

.theme-danger {
  color: #dc2626;
}

.theme-danger .status-dot {
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.2);
}

.theme-neutral {
  color: #4b5563;
}

.theme-neutral .status-dot {
  box-shadow: 0 0 0 3px rgba(156, 163, 175, 0.2);
}

.theme-primary {
  color: #2563eb;
}

.theme-primary .status-dot {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}

/* ================= 响应式 ================= */
@media (max-width: 560px) {
  .record-section {
    padding: 20px 16px;
  }

  .record-grid {
    grid-template-columns: 1fr;
    row-gap: 16px;
  }
}
</style>