<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CardFrame from './CardFrame.vue'
import DshButton from './DshButton.vue'
import composerCss from '../vendor/dsh/ui-user-questions/src/client/QuestionComposer.module.css'
import { iconSvg } from '../timeline/icons'
import { statusText } from '../projection/labels'
import { QUESTION_STRINGS, questionString } from './questionStrings'
import { QuestionPending, type QuestionCardSnapshot } from './questionPending'
import {
  answered as isDraftAnswered,
  answersOf,
  draftsWithRecord,
  emptyDrafts,
  parseRecommendedLabel,
  validateDrafts,
  type QuestionDraftAnswer,
} from './questionDraft'
import type { Question, QuestionEntry, QuestionOption } from '../projection/transcript'

/*
 * 问卷卡（票据 05 主目标）：Harness ui-user-questions QuestionComposer.tsx
 * 的 QuestionFlow（MIT）忠实重写为 Vue SFC——编号选项（单选）/勾选框（多选）、
 * 选项描述折叠、推荐徽章解析、自定义答案行、无选项题的整块文本域、
 * 分页器（1/N + 上一题/下一题）、跳过（只清当前题草稿）、必填与 min/max
 * 校验、expires_at 倒计时（上游 PendingQuestion 状态机，见 questionPending.ts）、
 * 作答后只读回显（上游 review 卡：同一卡面锁定重放记录）。
 *
 * 提交通道偏离上游：上游经 waterfall/rpc 双通道 settle；本应用 emit('submit')
 * 交给 controller（新轮次 inputs.interaction JSON）。
 * 问卷作答不是工具授权——审批语义严格归票据 06。
 *
 * 其余有意偏离（上游 wire 无对应物，均有注释）：
 * - multi 不渲染自定义答案行：pi_dify 契约对 multi 数组逐项校验选项
 *   id/label，自定义文本没有通道，渲染一个会被静默丢弃的输入框是坏的 UI。
 * - 提交校验只拦必填（票据 DoD）与 min/max（pi_dify 同款约束）；上游还要求
 *   可选题显式作答或跳过，这里放宽为可直接提交。
 */
const props = defineProps<{ entry: QuestionEntry }>()

const emit = defineEmits<{
  submit: [answers: Record<string, string | string[]>]
  cancel: []
}>()

const questions = computed<Question[]>(() => props.entry.questionnaire.questions || [])
/* 上游 review 卡：已落定的调用记录，同一卡面锁定、无提交通道。 */
const review = computed<Record<string, string | string[]> | undefined>(() =>
  props.entry.status === 'waiting' ? undefined : props.entry.answers ?? {},
)
const busy = computed(() => props.entry.submitting === true)
const locked = computed(() => busy.value || review.value !== undefined)
const canSubmit = computed(() => props.entry.status === 'waiting' && card.value.canSubmit)

/* ---- 草稿状态（questionDraft.ts 状态机） ---- */
const drafts = ref<QuestionDraftAnswer[]>(initDrafts())
const index = ref(0)
type Feedback = { key: 'errorIncomplete' | 'errorUnanswered' | 'errorUnavailable' } | { text: string }
const error = ref<Feedback | null>(null)
const expandedCopy = ref<{ index: number; copies: Set<'question' | number> }>({ index: 0, copies: new Set() })

function initDrafts(): QuestionDraftAnswer[] {
  return review.value !== undefined
    ? draftsWithRecord(questions.value, review.value)
    : emptyDrafts(questions.value)
}

// question.answered/cancelled 事件原地改写 entry：状态翻转时按记录重建回显。
watch(
  () => [props.entry.pendingId, props.entry.status] as const,
  ([nextPendingId, nextStatus], [prevPendingId]) => {
    if (nextPendingId !== prevPendingId) {
      drafts.value = initDrafts()
      index.value = 0
      error.value = null
      return
    }
    if (nextStatus !== 'waiting') {
      drafts.value = draftsWithRecord(questions.value, props.entry.answers ?? {})
      index.value = 0
      error.value = null
    }
  },
)

/* ---- 倒计时 carrier（questionPending.ts；到期自动关闭作答通道） ---- */
const pending = new QuestionPending(
  props.entry.pendingId,
  typeof props.entry.questionnaire.expires_at === 'number' ? props.entry.questionnaire.expires_at : undefined,
)
const cardTick = ref(0)
const unsubscribe = pending.subscribe(() => {
  cardTick.value += 1
})
onBeforeUnmount(() => {
  unsubscribe()
  pending.dispose()
})
const card = computed<QuestionCardSnapshot>(() => {
  void cardTick.value
  return pending.snapshot()
})

/* ---- 头部等待状态（上游 headerActions 的 waitStatus/waitButton 规则逐字平移） ---- */
const countdown = computed(() => card.value.countdown)
const waitState = computed(() => card.value.waitState)
const countdownLabel = computed(() => {
  if (countdown.value === undefined) return ''
  if (waitState.value === 'waiting' || waitState.value === 'editing') return questionString('waitHeld')
  const seconds = Math.ceil(countdown.value.remainingMs / 1000)
  return countdown.value.running
    ? questionString('waitCountdown', { seconds })
    : questionString('waitPaused', { seconds })
})
const showTakeTime = computed(
  () => countdown.value !== undefined && waitState.value !== 'waiting' && waitState.value !== 'editing',
)
const reviewStatusLabel = computed(() => (review.value === undefined ? '' : statusText(props.entry.status)))

/* ---- 当前题与草稿 ---- */
const EMPTY_DRAFT: QuestionDraftAnswer = { selected: [], custom: '', skipped: false }
const question = computed<Question>(
  () =>
    questions.value[index.value] ?? {
      id: '',
      question: '',
      type: 'single',
      options: [],
    },
)
const draft = computed<QuestionDraftAnswer>(() => drafts.value[index.value] ?? EMPTY_DRAFT)
const hasOptions = computed(() => (question.value.options?.length ?? 0) > 0)
const eyebrow = computed(() => question.value.header || props.entry.questionnaire.title || '')
const expanded = computed(() =>
  expandedCopy.value.index === index.value ? expandedCopy.value.copies : new Set<'question' | number>(),
)
/* 自定义答案行：活卡只给有通道的题（single/text）；回显卡只在记录用到时保留。 */
const hasCustomRow = computed(() =>
  hasOptions.value &&
  (review.value !== undefined ? draft.value.custom !== '' : question.value.type !== 'multi'),
)

/* glyph 尺寸取上游调用点的 size props：chevron 14、check 12（勾选框内）、edit/close 16。 */
const chevronDown = iconSvg('chevron-down', 14)
const chevronUp = iconSvg('chevron-up', 14)
const chevronLeft = iconSvg('chevron-left', 14)
const chevronRight = iconSvg('chevron-right', 14)
const checkIcon = iconSvg('check', 12)
const editIcon = iconSvg('edit', 12)

const feedbackText = computed(() => {
  if (error.value === null) return ''
  return 'key' in error.value ? questionString(error.value.key) : error.value.text
})

function toggleCopy(copy: 'question' | number): void {
  const copies = new Set(expanded.value)
  if (!copies.delete(copy)) copies.add(copy)
  expandedCopy.value = { index: index.value, copies }
}

function replaceProgress(nextIndex: number, nextDrafts: QuestionDraftAnswer[]): void {
  if (nextIndex !== index.value) {
    // 另一题从顶部开始，长文案重新折叠（上游 replaceProgress 同款复位）。
    expandedCopy.value = { index: nextIndex, copies: new Set() }
  }
  index.value = nextIndex
  drafts.value = nextDrafts
}

function updateDraft(update: (current: QuestionDraftAnswer) => QuestionDraftAnswer, nextIndex = index.value): void {
  pending.engage()
  const nextDrafts = drafts.value.map((item, itemIndex) => (itemIndex === index.value ? update(item) : item))
  replaceProgress(nextIndex, nextDrafts)
  error.value = null
}

/* 上游 choose：单选替换选中并自动翻页，多选切换勾选。 */
function choose(optionId: string): void {
  updateDraft(
    (current) => {
      if (question.value.type === 'multi') {
        const selected = current.selected.includes(optionId)
          ? current.selected.filter((item) => item !== optionId)
          : [...current.selected, optionId]
        return { ...current, selected, skipped: false }
      }
      return { selected: [optionId], custom: '', skipped: false }
    },
    question.value.type !== 'multi' && index.value < questions.value.length - 1 ? index.value + 1 : index.value,
  )
}

/* Enter 续流，Shift+Enter 换行，IME 组合中不拦截（isComposing 平移）。 */
function isComposing(event: KeyboardEvent): boolean {
  // keyCode 229 is the legacy IME-composition signal engines emit without isComposing.
  return event.isComposing || (event as KeyboardEvent & { keyCode?: number }).keyCode === 229
}

function draftCustom(event: Event): void {
  const value = (event.target as HTMLTextAreaElement).value
  updateDraft((current) => ({
    ...current,
    // 多选草稿保留勾选，单选/文本输入替换选择。
    selected: question.value.type === 'multi' ? current.selected : [],
    custom: value,
    skipped: false,
  }))
}

function continueFromCustom(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey || isComposing(event)) return
  event.preventDefault()
  continueFlow()
}

function continueFlow(): void {
  if (!isDraftAnswered(draft.value)) {
    error.value = { key: 'errorUnanswered' }
    return
  }
  if (index.value < questions.value.length - 1) {
    replaceProgress(index.value + 1, drafts.value)
    return
  }
  submitDrafts(drafts.value)
}

function submitDrafts(values: QuestionDraftAnswer[]): void {
  const verdict = validateDrafts(questions.value, values)
  if (!verdict.ok) {
    replaceProgress(verdict.index, values)
    error.value =
      verdict.reason === 'incomplete'
        ? { key: 'errorIncomplete' }
        : verdict.reason === 'min'
          ? {
              text: questionString('errorMinSelections', {
                min: questions.value[verdict.index]?.min_selections ?? 1,
              }),
            }
          : {
              text: questionString('errorMaxSelections', {
                max: questions.value[verdict.index]?.max_selections ?? 1,
              }),
            }
    return
  }
  if (!canSubmit.value) {
    error.value = { key: 'errorUnavailable' }
    return
  }
  error.value = null
  emit('submit', answersOf(questions.value, values))
}

function skipQuestion(): void {
  pending.engage()
  const current = index.value
  const lastIndex = questions.value.length - 1
  const nextDrafts = drafts.value.map((item, itemIndex) =>
    itemIndex === current ? { selected: [], custom: '', skipped: true } : item,
  )
  replaceProgress(current < lastIndex ? current + 1 : current, nextDrafts)
  error.value = null
  if (current < lastIndex) return
  submitDrafts(nextDrafts)
}

/* 上游 answerSurface 的焦点暂停：焦点进入卡体暂停倒计时，离开恢复。 */
const answerSurface = ref<HTMLElement | null>(null)

function onSurfaceFocusIn(event: FocusEvent): void {
  if (!answerSurface.value?.contains(event.relatedTarget as Node)) pending.holdFocus()
}

function onSurfaceFocusOut(event: FocusEvent): void {
  if (!answerSurface.value?.contains(event.relatedTarget as Node)) pending.releaseFocus()
}

function displayOf(option: QuestionOption): { label: string; recommended: boolean } {
  return parseRecommendedLabel(option.label)
}
</script>

<template>
  <CardFrame
    :eyebrow="eyebrow"
    :title="question.question"
    :labelledby="`question-${entry.pendingId}-${index}`"
    :busy="busy"
    close-label="放弃整组问题"
    :closable="review === undefined"
    data-testid="question-card"
    @close="emit('cancel')"
  >
    <template #header-extra>
      <span v-if="countdownLabel" :class="composerCss.waitStatus" data-testid="question-wait">{{ countdownLabel }}</span>
      <DshButton
        v-if="showTakeTime"
        variant="outline"
        size="sm"
        :class="composerCss.waitButton"
        :disabled="busy"
        data-testid="question-take-time"
        @click="pending.takeTime()"
      >
        {{ QUESTION_STRINGS.waitTakeTime }}
      </DshButton>
      <span v-if="reviewStatusLabel" :class="composerCss.waitStatus" data-testid="question-review-status">{{ reviewStatusLabel }}</span>
    </template>

    <div
      ref="answerSurface"
      :class="composerCss.body"
      data-question-scroll
      @focusin="onSurfaceFocusIn"
      @focusout="onSurfaceFocusOut"
    >
      <div :class="composerCss.questionTitle" :data-expanded="expanded.has('question') ? '' : undefined">
        <h2 :id="`question-${entry.pendingId}-${index}`" :class="[composerCss.title, composerCss.titlePreview]">
          {{ question.question }}
        </h2>
        <button
          type="button"
          :class="[composerCss.iconButton, composerCss.copyToggle, composerCss.questionToggle]"
          aria-label="展开"
          :aria-expanded="expanded.has('question')"
          :aria-controls="`question-${entry.pendingId}-${index}`"
          @click="toggleCopy('question')"
        >
          <span v-html="expanded.has('question') ? chevronUp : chevronDown" />
        </button>
      </div>

      <div :class="composerCss.options" :role="question.type === 'multi' ? 'group' : 'radiogroup'">
        <div
          v-for="(option, optionIndex) in question.options || []"
          :key="`${option.id}-${optionIndex}`"
          :class="[
            composerCss.optionRow,
            !locked ? composerCss.optionRowInteractive : '',
            draft.selected.includes(option.id) && question.type !== 'multi' ? composerCss.optionSelected : '',
          ]"
          data-option-row
          :data-expanded="expanded.has(optionIndex) ? '' : undefined"
        >
          <button
            type="button"
            :class="composerCss.option"
            :role="question.type === 'multi' ? 'checkbox' : 'radio'"
            :aria-checked="draft.selected.includes(option.id)"
            :aria-label="displayOf(option).label"
            :disabled="locked"
            :data-testid="`question-option-${optionIndex}`"
            @click="choose(option.id)"
            @keydown.enter.prevent="submitDrafts(drafts)"
          >
            <span
              v-if="question.type === 'multi'"
              :class="[composerCss.checkbox, draft.selected.includes(option.id) ? composerCss.checkboxChecked : '']"
              aria-hidden="true"
            >
              <span v-if="draft.selected.includes(option.id)" v-html="checkIcon" />
            </span>
            <span v-else :class="composerCss.number">{{ optionIndex + 1 }}</span>
            <span :class="composerCss.optionCopy">
              <span :class="composerCss.optionLine" data-option-line>
                <span :class="composerCss.optionLabel">{{ displayOf(option).label }}</span>
                <span v-if="displayOf(option).recommended" :class="composerCss.badge" data-testid="question-badge">{{ QUESTION_STRINGS.optionRecommended }}</span>
              </span>
              <span
                v-if="option.description?.trim()"
                :id="`question-${entry.pendingId}-${index}-option-${optionIndex}-description`"
                :class="composerCss.description"
                data-option-description
              >{{ option.description }}</span>
            </span>
          </button>
          <button
            v-if="option.description?.trim()"
            type="button"
            :class="[composerCss.iconButton, composerCss.copyToggle, composerCss.descriptionToggle]"
            :aria-label="expanded.has(optionIndex) ? '收起' : '展开'"
            :aria-expanded="expanded.has(optionIndex)"
            @click="toggleCopy(optionIndex)"
          >
            <span v-html="expanded.has(optionIndex) ? chevronUp : chevronDown" />
          </button>
        </div>

        <p v-if="review !== undefined && draft.skipped" :class="composerCss.reviewNote">
          {{ QUESTION_STRINGS.reviewSkipped }}
        </p>

        <!-- 只读回显卡仅当记录用到自定义文本才保留输入框（上游注释同款规则）。 -->
        <div
          v-if="hasCustomRow"
          :class="[
            composerCss.customRow,
            draft.custom !== '' ? composerCss.customRowActive : '',
            question.type !== 'multi' && draft.selected.length > 0 ? composerCss.customRowYielded : '',
          ]"
        >
          <span :class="composerCss.number" aria-hidden="true" v-html="editIcon" />
          <div :class="[composerCss.field, composerCss.customInline]">
            <div aria-hidden="true" :class="composerCss.fieldMirror">{{ `${draft.custom}\n` }}</div>
            <textarea
              :class="composerCss.fieldInput"
              :value="draft.custom"
              :disabled="locked"
              rows="1"
              :placeholder="QUESTION_STRINGS.customPlaceholder"
              :data-testid="`question-custom-${index}`"
              @input="draftCustom"
              @keydown="continueFromCustom"
            />
          </div>
        </div>
      </div>

      <!-- 无选项题（text 型）：自由文本是整个卡体，带框整块（上游 customBlock）。 -->
      <div
        v-if="!hasOptions && (review === undefined || draft.custom !== '')"
        :class="[composerCss.field, composerCss.customBlock]"
      >
        <div aria-hidden="true" :class="composerCss.fieldMirror">{{ `${draft.custom}\n` }}</div>
        <textarea
          :class="composerCss.fieldInput"
          :value="draft.custom"
          :disabled="locked"
          rows="1"
          :placeholder="question.placeholder || QUESTION_STRINGS.customPlaceholder"
          :maxlength="question.max_length"
          :data-testid="`question-text-${index}`"
          @input="draftCustom"
          @keydown="continueFromCustom"
        />
      </div>
    </div>

    <template #footer>
      <footer :class="composerCss.footer">
        <div :class="composerCss.pager">
          <button
            type="button"
            :class="composerCss.iconButton"
            aria-label="上一题"
            :disabled="index === 0 || busy"
            data-testid="question-prev"
            @click="replaceProgress(index - 1, drafts)"
          >
            <span v-html="chevronLeft" />
          </button>
          <span :class="composerCss.progress" data-testid="question-progress">{{ index + 1 }} / {{ questions.length }}</span>
          <button
            type="button"
            :class="composerCss.iconButton"
            aria-label="下一题"
            :disabled="index === questions.length - 1 || busy"
            data-testid="question-next"
            @click="replaceProgress(index + 1, drafts)"
          >
            <span v-html="chevronRight" />
          </button>
        </div>
        <div :class="composerCss.feedback" role="status" data-testid="question-feedback">{{ feedbackText }}</div>
        <!-- 回显卡没有要发送的东西：只有翻页器可走记录（上游注释同款规则）。 -->
        <div v-if="review === undefined" :class="composerCss.footerActions">
          <DshButton variant="outline" :disabled="busy" data-testid="question-skip" @click="skipQuestion">
            {{ QUESTION_STRINGS.actionSkip }}
          </DshButton>
          <DshButton
            variant="primary"
            :disabled="busy || !isDraftAnswered(draft) || (index === questions.length - 1 && !canSubmit)"
            data-testid="question-primary"
            @click="continueFlow"
          >
            {{ busy ? QUESTION_STRINGS.submitting : index === questions.length - 1 ? QUESTION_STRINGS.submit : QUESTION_STRINGS.actionNext }}
          </DshButton>
        </div>
      </footer>
    </template>
  </CardFrame>
</template>
