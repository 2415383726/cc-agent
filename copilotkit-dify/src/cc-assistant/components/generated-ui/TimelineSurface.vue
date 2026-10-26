<template>
  <BusinessSurface surface="timeline" :meta="spec.meta" :actions="spec.actions" :is-running="isRunning"
    @intent="emit('intent', $event)">
    <div class="timeline-container">
      <ol class="timeline-list">
        <li v-for="(item, index) in spec.items" :key="item.id" class="timeline-item">

          <!-- 1. 时间列 (放大并改用等宽数字字体) -->
          <time class="timeline-time">{{ item.time }}</time>

          <!-- 2. 时间轴线与节点 (带语义化颜色) -->
          <div class="timeline-rail" aria-hidden="true">
            <span class="timeline-dot" :class="getStatusTheme(item.status)"></span>
            <div class="timeline-line" v-if="index !== spec.items.length - 1"></div>
          </div>

          <!-- 3. 内容区 -->
          <div class="timeline-entry">
            <div class="timeline-header">
              <strong class="timeline-title">{{ item.title }}</strong>

              <!-- 状态徽章 -->
              <span v-if="item.status" class="timeline-status" :class="getStatusTheme(item.status)">
                {{ item.status }}
              </span>
            </div>

            <p v-if="item.description" class="timeline-desc">{{ item.description }}</p>
          </div>

        </li>
      </ol>
    </div>
  </BusinessSurface>
</template>

<script setup lang="ts">
import BusinessSurface from './BusinessSurface.vue'
import type { TimelineSpec } from '../../lib/structuredContent'

withDefaults(defineProps<{ spec: TimelineSpec; isRunning?: boolean }>(), { isRunning: false })
const emit = defineEmits<{ intent: [prompt: string] }>()

/**
 * 智能状态颜色推断（全局统一）
 * 用于给时间节点和徽章上色
 */
function getStatusTheme(statusText?: string): string {
  if (!statusText) return 'theme-neutral' // 没有状态默认灰
  const text = statusText.toLowerCase()
  if (/正常|完成|优秀|通过|成功|上线/.test(text)) return 'theme-success'
  if (/风险|延期|异常|拒绝|失败|警告|红/.test(text)) return 'theme-danger'
  if (/需改进|审核中|待定|黄|橙/.test(text)) return 'theme-warning'
  if (/未开始/.test(text)) return 'theme-neutral'
  // 进行中 / 良好等 默认为主色蓝
  return 'theme-primary'
}
</script>

<style scoped>
.timeline-container {
  /* 与前面组件看齐，增加容器包裹感 */
  padding: 24px 24px 8px;
  background: var(--cc-agent-surface, #ffffff);
  border-radius: 8px;
  border: 1px solid var(--cc-agent-line, #e5e7eb);
}

.timeline-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

/* 🌟 核心布局：左(时间) - 中(轴线) - 右(内容) */
.timeline-item {
  display: grid;
  /* 130px 给时间留足空间，32px 放轴线，剩余空间给内容 */
  grid-template-columns: 130px 32px minmax(0, 1fr);
  gap: 16px;
  padding-bottom: 32px;
  /* 拉大节点之间的间距 */
}

/* ================= 1. 时间列 ================= */
.timeline-time {
  text-align: right;
  /* 时间靠右对齐，紧贴轴线，极其专业 */
  padding-top: 2px;
  /* 微调与标题的垂直对齐 */
  color: var(--cc-agent-text-main, #374151);
  /* 加深颜色 */
  font-family: var(--cc-agent-data-font-family, 'Menlo', 'Monaco', monospace);
  font-variant-numeric: tabular-nums;
  font-size: 14.5px;
  /* 🌟 放大时间 */
  font-weight: 500;
  line-height: 1.5;
}

/* ================= 2. 时间轴线与节点 ================= */
.timeline-rail {
  position: relative;
  display: flex;
  justify-content: center;
}

/* 轴线 */
.timeline-line {
  position: absolute;
  top: 24px;
  /* 从节点下方开始 */
  bottom: -32px;
  /* 延伸到下一个节点的 padding 区域 */
  width: 2px;
  /* 线条稍微加粗一点点，从 1px 变 2px */
  background: var(--cc-agent-muted-line, #e5e7eb);
}

/* 节点圆点 (🌟 放大并带状态发光效果) */
.timeline-dot {
  position: relative;
  z-index: 1;
  width: 12px;
  /* 放大原点 */
  height: 12px;
  margin-top: 6px;
  /* 对齐文本 */
  border-radius: 50%;
  background-color: currentColor;
  /* 颜色由状态主题控制 */
  border: 2px solid var(--cc-agent-surface, #ffffff);
  /* 用白边隔开轴线 */
  box-sizing: content-box;
}

/* ================= 3. 内容区 ================= */
.timeline-entry {
  min-width: 0;
}

.timeline-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.timeline-title {
  font-size: 16px;
  /* 🌟 标题放大到 16px */
  font-weight: 600;
  color: var(--cc-agent-text-main, #111827);
  line-height: 1.5;
  margin: 0;
}

.timeline-desc {
  margin: 8px 0 0;
  /* 与标题拉开一点距离 */
  color: var(--cc-agent-muted, #6b7280);
  font-size: 14px;
  /* 🌟 描述放大到 14px */
  line-height: 1.6;
}

/* ================= 🌟 状态语义化主题 (徽章 + 节点) ================= */
.timeline-status {
  flex: 0 0 auto;
  border-radius: 6px;
  padding: 4px 10px;
  /* 更加饱满的徽章 */
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

/* 绿色 (成功/正常) */
.theme-success {
  color: #059669;
}

span.theme-success {
  background-color: #ecfdf5;
  border: 1px solid #d1fae5;
}

.timeline-dot.theme-success {
  color: #10b981;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15);
}

/* 红色 (风险/延期) */
.theme-danger {
  color: #dc2626;
}

span.theme-danger {
  background-color: #fef2f2;
  border: 1px solid #fee2e2;
}

.timeline-dot.theme-danger {
  color: #ef4444;
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15);
}

/* 橙黄色 (警告/需改进) */
.theme-warning {
  color: #d97706;
}

span.theme-warning {
  background-color: #fffbeb;
  border: 1px solid #fef3c7;
}

.timeline-dot.theme-warning {
  color: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15);
}

/* 蓝色 (进行中/主色) */
.theme-primary {
  color: #2563eb;
}

span.theme-primary {
  background-color: #eff6ff;
  border: 1px solid #dbeafe;
}

.timeline-dot.theme-primary {
  color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

/* 灰色 (未开始/默认) */
.theme-neutral {
  color: #4b5563;
}

span.theme-neutral {
  background-color: #f3f4f6;
  border: 1px solid #e5e7eb;
}

.timeline-dot.theme-neutral {
  color: #9ca3af;
  box-shadow: 0 0 0 3px rgba(156, 163, 175, 0.15);
}


/* ================= 移动端响应式优化 ================= */
@media (max-width: 560px) {
  .timeline-container {
    padding: 20px 16px 8px;
  }

  /* 移动端改为：轴线在最左，时间和内容在右侧堆叠 */
  .timeline-item {
    grid-template-columns: 24px 1fr;
    /* 轴线 24px，右侧内容沾满 */
    gap: 12px;
  }

  /* 时间移动到第二列第一行 */
  .timeline-time {
    grid-column: 2;
    text-align: left;
    /* 移动端靠左对齐 */
    font-size: 13px;
    color: var(--cc-agent-muted, #6b7280);
    /* 移动端弱化时间颜色 */
    padding-top: 0;
  }

  /* 内容区移动到第二列第二行 */
  .timeline-entry {
    grid-column: 2;
  }

  /* 轴线占满两行 */
  .timeline-rail {
    grid-row: 1 / 3;
  }

  /* 微调轴线样式适配移动端 */
  .timeline-dot {
    margin-top: 4px;
  }

  .timeline-line {
    top: 20px;
  }
}
</style>