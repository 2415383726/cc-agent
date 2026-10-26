<template>
  <div class="ai-assistant-wrapper">
    <div class="ai-hero-header">
      <h1 class="ai-hero-title">有什么能帮你的？</h1>
      <!-- <p class="ai-hero-subtitle">选择业务能力，或直接在下方输入问题。</p> -->
    </div>

    <div class="home-catalog-panel" :class="{ compact, 'home-catalog-panel--pills': variant === 'pills' }">
      <section class="home-catalog-section">
        <div class="home-catalog-section__heading">
          <h2>常用能力</h2>
          <p>选择一个业务入口后进入问答，通常能获得更好的效果。</p>
        </div>

        <div class="home-catalog-grid">
          <button v-for="card in businessCards" :key="card.key" type="button" class="home-catalog-card"
            :class="`home-catalog-card--${card.kind}`" @click="selectCard(card)">
            <span class="home-catalog-card__icon-wrapper" :data-icon="card.icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" focusable="false">
                <path v-for="path in iconPaths(card.icon)" :key="path" :d="path" />
              </svg>
            </span>
            <div class="home-catalog-card__content">
              <div class="home-catalog-card__header-row">
                <strong class="home-catalog-card__title">{{ card.title }}</strong>
                <span v-if="card.category" class="home-catalog-card__category">{{ card.category }}</span>
              </div>
              <small class="home-catalog-card__desc">{{ card.description }}</small>
            </div>
          </button>
        </div>
      </section>
      <section v-if="showQuestionList" class="home-catalog-section mt-4">
        <div class="home-catalog-section__heading">
          <h2>推荐问题</h2>
          <p>点击后会填入下方输入框。</p>
        </div>
        <div class="home-question-list">
          <button v-for="question in suggestedQuestions" :key="question.message" type="button"
            class="home-question-chip" @click="emit('selectQuestion', question)">
            <span class="home-question-chip__icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" focusable="false">
                <path d="M3.5 8h8" />
                <path d="M8.5 5l3 3-3 3" />
              </svg>
            </span>
            <span>{{ question.title }}</span>
          </button>
        </div>
      </section>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AssistantCatalog, AssistantSkill, SuggestedQuestion } from '../../lib/assistantCatalog'
import { defaultAssistantCatalog } from '../../lib/assistantCatalog'

const props = withDefaults(defineProps<{
  catalog?: AssistantCatalog
  compact?: boolean
  variant?: 'cards' | 'pills'
  showSuggestedQuestions?: boolean
}>(), {
  catalog: () => defaultAssistantCatalog,
  compact: false,
  variant: 'cards',
  showSuggestedQuestions: false,
})

const emit = defineEmits<{
  selectSkill: [skill: AssistantSkill]
  selectQuestion: [question: SuggestedQuestion]
}>()

type HomeCatalogCard = {
  key: string
  kind: 'skill' | 'question'
  title: string
  description: string
  category: string
  icon: string
  skill?: AssistantSkill
  question?: SuggestedQuestion
}

const skills = computed(() => props.catalog?.skills || [])
const suggestedQuestions = computed(() => props.catalog?.suggestedQuestions || [])
const showSuggestedQuestions = computed(() => Boolean(props.showSuggestedQuestions))
const businessCards = computed<HomeCatalogCard[]>(() => [
  ...skills.value.map((skill) => ({
    key: `skill:${skill.name}`,
    kind: 'skill' as const,
    title: skill.label,
    description: skill.description,
    category: skill.category,
    icon: skillIconName(skill),
    skill,
  })),
])
const showQuestionList = computed(() => (
  showSuggestedQuestions.value
  && suggestedQuestions.value.length > 0
))

const ICON_PATHS: Record<string, string[]> = {
  'file-text': ['M7 3h6l4 4v14H7z', 'M13 3v5h4', 'M9.5 12h5', 'M9.5 16h5'],
  chart: ['M5 19V5', 'M5 19h14', 'M9 16v-5', 'M13 16V8', 'M17 16v-8'],
  mail: ['M4 6.5h16v11H4z', 'm4.5 8 7.5 5 7.5-5'],
  pen: ['M5 19l3.5-1 9-9-2.5-2.5-9 9L5 19z', 'm14.5 6.5 1.5-1.5'],
  target: ['M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z', 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M12 12h.01'],
  feedback: ['M5 6.5h14v8H9l-4 3v-11Z', 'M8.5 10.5h5.5', 'M8.5 13h8'],
  checklist: ['M6 6.5h12', 'M6 12h12', 'M6 17.5h12', 'M3.5 6.5l.8.8 1.5-1.8', 'M3.5 12l.8.8 1.5-1.8', 'M3.5 17.5l.8.8 1.5-1.8'],
  skill: ['M12 3 5.5 6.5 12 10l6.5-3.5L12 3z', 'M5.5 10 12 13.5 18.5 10', 'M5.5 13.5 12 17l6.5-3.5'],
}

function skillIconName(skill: AssistantSkill) {
  return skill.icon || iconFromName(skill.name, skill.category)
}

function iconFromName(name: string, category: string) {
  const haystack = `${name} ${category}`.toLowerCase()
  if (haystack.includes('email') || haystack.includes('mail') || haystack.includes('沟通')) return 'mail'
  if (haystack.includes('weekly') || haystack.includes('report') || haystack.includes('周报')) return 'chart'
  if (haystack.includes('writer') || haystack.includes('content') || haystack.includes('写作')) return 'pen'
  if (haystack.includes('meeting') || haystack.includes('notes') || haystack.includes('办公')) return 'file-text'
  return 'skill'
}

function iconPaths(name: string) {
  return ICON_PATHS[name] || ICON_PATHS.skill
}

function selectCard(card: HomeCatalogCard) {
  if (card.kind === 'skill' && card.skill) {
    emit('selectSkill', card.skill)
    return
  }
  if (card.question) emit('selectQuestion', card.question)
}
</script>

<style scoped>
/* ========== 全局变量与外层包裹 ========== */
.ai-assistant-wrapper {
  width: 100%;
  /* 修复居中挤压：强制占满可用宽度 */
  max-width: 900px;
  margin: 0 auto;
  padding: 0 16px;
}

/* 顶部巨大的欢迎语 */
.ai-hero-header {
  text-align: center;
  margin: 24px 0 22px;
}

.ai-hero-title {
  font-size: 24px;
  font-weight: 800;
  color: var(--cc-agent-text);
  letter-spacing: -0.5px;
  margin-bottom: 8px;
}

.ai-hero-subtitle {
  font-size: 14px;
  color: var(--cc-agent-muted);
}

/* ========== 布局 ========== */
.home-catalog-panel {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.home-catalog-panel.compact {
  gap: 20px;
}

.home-catalog-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mt-4 {
  margin-top: 16px;
}

/* ========== 标题区域 ========== */
.home-catalog-section__heading {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  /* 修复：强制左对齐，防止被外层容器居中 */
  text-align: left;
}

.home-catalog-section__heading h2 {
  margin: 0;
  color: var(--cc-agent-text);
  font-size: 15px;
  font-weight: 700;
}

.home-catalog-section__heading p {
  margin: 0;
  color: var(--cc-agent-muted);
  font-size: 13px;
}

/* ========== 常用能力 (Cards) - 恢复左右布局 ========== */
.home-catalog-grid {
  display: grid;
  /* 修复单列问题：宽度充裕时两列/三列，窄屏自动一列。260px是左右结构的舒适宽度 */
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 12px;
  width: 100%;
  /* 强制网格撑满容器 */
}

.home-catalog-card {
  position: relative;
  display: flex;
  flex-direction: row;
  /* 恢复左右布局 */
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--cc-agent-line);
  border-radius: var(--cc-agent-card-radius);
  background: #ffffff;
  text-align: left;
  /* 修复文字居中问题 */
  cursor: pointer;
  box-shadow: none;
  transition: background-color 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

/* Hover 微交互 */
.home-catalog-card:hover {
  background: #ffffff;
  border-color: var(--cc-agent-primary-border);
  box-shadow: none;
  transform: none;
}

.home-catalog-card:focus-visible {
  outline: 2px solid var(--cc-agent-primary);
  outline-offset: 2px;
}

/* 左侧：技能图标 */
.home-catalog-card__icon-wrapper {
  flex-shrink: 0;
  /* 防止图标被挤压 */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
  transition: transform 0.2s ease;
}

.home-catalog-card:hover .home-catalog-card__icon-wrapper {
  transform: scale(1.05);
}

.home-catalog-card__icon-wrapper svg {
  width: 22px;
  height: 22px;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}

/* 右侧：卡片内容区 */
.home-catalog-card__content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-grow: 1;
  min-width: 0;
  /* 保证省略号(ellipsis)能正常工作 */
}

/* 标题与标签同行 */
.home-catalog-card__header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

.home-catalog-card__title {
  color: var(--cc-agent-text);
  font-size: 15px;
  line-height: 1.4;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 分类标签 */
.home-catalog-card__category {
  flex-shrink: 0;
  border-radius: 6px;
  background: #f8fafc;
  color: #64748b;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 600;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.home-catalog-card:hover .home-catalog-card__category {
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
}

.home-catalog-card__desc {
  color: var(--cc-agent-muted);
  font-size: 13px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ========== 推荐问题 (Chips) ========== */
.home-question-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.home-question-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #ffffff;
  color: #475569;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: none;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.home-question-chip:hover {
  border-color: var(--cc-agent-primary-border);
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
  box-shadow: none;
  transform: none;
}

.home-question-chip__icon {
  display: inline-flex;
  color: #cbd5e1;
  transition: color 0.2s ease;
}

.home-question-chip:hover .home-question-chip__icon {
  color: var(--cc-agent-primary);
}

.home-question-chip__icon svg {
  width: 14px;
  height: 14px;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

/* ========== Pills 降级模式 (兼容保留) ========== */
.home-catalog-panel--pills .home-catalog-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.home-catalog-panel--pills .home-catalog-card {
  align-items: center;
  padding: 8px 16px;
  border-radius: 999px;
  box-shadow: none;
  transform: none;
}

.home-catalog-panel--pills .home-catalog-card__category,
.home-catalog-panel--pills .home-catalog-card__desc {
  display: none;
}

/* ========== 响应式调整 ========== */
@media (max-width: 600px) {
  .home-catalog-grid {
    grid-template-columns: 1fr;
    /* 极窄情况下强制单列 */
  }
}

@media (prefers-reduced-motion: reduce) {
  .home-catalog-card,
  .home-catalog-card__icon-wrapper,
  .home-catalog-card__category,
  .home-question-chip,
  .home-question-chip__icon {
    transition: none;
  }

  .home-catalog-card:hover,
  .home-question-chip:hover {
    transform: none;
  }
}
</style>
