<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { statusText } from '../projection/labels'
import type { Question, Questionnaire } from '../projection/transcript'

const props = defineProps<{
  questionnaire: Questionnaire
  status: 'waiting' | 'answered' | 'cancelled'
  answers?: Record<string, string | string[]>
  submitting?: boolean
  error?: string
}>()

const emit = defineEmits<{
  submit: [answers: Record<string, string | string[]>]
  cancel: []
}>()

const draft = reactive<Record<string, string | string[]>>({})
const localError = reactive({ message: '' })

function resetDraft() {
  for (const key of Object.keys(draft)) delete draft[key]
  for (const question of props.questionnaire.questions || []) {
    if (props.answers && question.id in props.answers) {
      draft[question.id] = props.answers[question.id]
    } else if (question.type === 'multi') {
      draft[question.id] = []
    } else {
      draft[question.id] = ''
    }
  }
  localError.message = ''
}

watch(
  () => [props.questionnaire, props.answers, props.status],
  () => resetDraft(),
  { immediate: true, deep: true },
)

const waiting = computed(() => props.status === 'waiting')
const title = computed(() => props.questionnaire.title || '来自 Agent 的问题')
const answeredEntries = computed(() =>
  (props.questionnaire.questions || []).map((question) => ({
    question,
    display: displayAnswer(question, (props.answers || {})[question.id]),
  })),
)

function optionId(value: string): string {
  return `${props.questionnaire.id}_${value}`
}

function setText(questionId: string, event: Event) {
  draft[questionId] = (event.target as HTMLTextAreaElement).value
}

function setSingle(question: Question, optionIdValue: string) {
  draft[question.id] = optionIdValue
}

function toggleMulti(question: Question, optionIdValue: string, checked: boolean) {
  const current = Array.isArray(draft[question.id]) ? [...(draft[question.id] as string[])] : []
  const index = current.indexOf(optionIdValue)
  if (checked && index < 0) current.push(optionIdValue)
  if (!checked && index >= 0) current.splice(index, 1)
  draft[question.id] = current
}

function submit() {
  if (!waiting.value || props.submitting) return
  const normalized: Record<string, string | string[]> = {}
  for (const question of props.questionnaire.questions || []) {
    const value = draft[question.id]
    if (question.type === 'multi') {
      const selected = Array.isArray(value) ? value : []
      if (question.required && !selected.length) {
        localError.message = `请回答：${question.question}`
        return
      }
      if (selected.length) normalized[question.id] = selected
    } else if (question.type === 'text') {
      const text = String(value || '').trim()
      if (question.required && !text) {
        localError.message = `请回答：${question.question}`
        return
      }
      if (text) normalized[question.id] = text
    } else {
      const selected = String(value || '')
      if (question.required && !selected) {
        localError.message = `请回答：${question.question}`
        return
      }
      if (selected) normalized[question.id] = selected
    }
  }
  localError.message = ''
  emit('submit', normalized)
}

function displayAnswer(question: Question, value: string | string[] | undefined): string {
  if (value == null || value === '' || (Array.isArray(value) && !value.length)) return '未回答'
  if (question.type === 'text') return String(value)
  const options = new Map((question.options || []).map((option) => [option.id, option.label]))
  if (Array.isArray(value)) return value.map((item) => options.get(item) || item).join(', ')
  return options.get(value) || value
}
</script>

<template>
  <section class="pi-question-card" :class="{ 'is-answered': status !== 'waiting' }">
    <header class="pi-card-title">
      <span class="pi-card-icon" aria-hidden="true">?</span>
      <div>
        <strong>{{ title }}</strong>
        <p v-if="questionnaire.description" class="pi-muted">{{ questionnaire.description }}</p>
      </div>
      <span class="pi-pill">{{ status === 'waiting' ? '等待回答' : statusText(status) }}</span>
    </header>

    <div v-if="waiting" class="pi-question-form">
      <fieldset
        v-for="(question, index) in questionnaire.questions"
        :key="question.id"
        class="pi-question"
        :disabled="submitting"
      >
        <legend>
          <span class="pi-question-index">{{ index + 1 }}</span>
          <span v-if="question.header" class="pi-question-header">{{ question.header }}</span>
          {{ question.question }}
          <span v-if="question.required" class="pi-required" aria-label="必填">*</span>
        </legend>

        <div v-if="question.type === 'single'" class="pi-options">
          <label v-for="option in question.options" :key="option.id" class="pi-option">
            <input
              type="radio"
              :name="`${questionnaire.id}_${question.id}`"
              :value="option.id"
              :checked="draft[question.id] === option.id"
              @change="setSingle(question, option.id)"
            />
            <span>
              <strong>{{ option.label }}</strong>
              <small v-if="option.description">{{ option.description }}</small>
            </span>
          </label>
        </div>

        <div v-else-if="question.type === 'multi'" class="pi-options">
          <label v-for="option in question.options" :key="option.id" class="pi-option">
            <input
              type="checkbox"
              :value="option.id"
              :checked="Array.isArray(draft[question.id]) && (draft[question.id] as string[]).includes(option.id)"
              @change="toggleMulti(question, option.id, ($event.target as HTMLInputElement).checked)"
            />
            <span>
              <strong>{{ option.label }}</strong>
              <small v-if="option.description">{{ option.description }}</small>
            </span>
          </label>
        </div>

        <textarea
          v-else
          class="pi-textarea"
          rows="3"
          :value="String(draft[question.id] || '')"
          :placeholder="question.placeholder || '请输入答案'"
          :maxlength="question.max_length || 4000"
          @input="(event) => setText(question.id, event)"
          @keydown.ctrl.enter.prevent="submit"
          @keydown.meta.enter.prevent="submit"
        ></textarea>
      </fieldset>

      <p v-if="localError.message || error" class="pi-form-error" role="alert">
        {{ localError.message || error }}
      </p>

      <div class="pi-form-actions">
        <button type="button" class="pi-button pi-button-ghost" :disabled="submitting" @click="emit('cancel')">
          取消
        </button>
        <button type="button" class="pi-button pi-button-primary" :disabled="submitting" @click="submit">
          {{ submitting ? '提交中…' : '提交答案' }}
        </button>
      </div>
    </div>

    <div v-else class="pi-answered">
      <p v-if="status === 'cancelled'" class="pi-muted">该问卷已取消。</p>
      <dl v-else>
        <template v-for="item in answeredEntries" :key="item.question.id">
          <dt>{{ item.question.question }}</dt>
          <dd>{{ item.display }}</dd>
        </template>
      </dl>
    </div>
  </section>
</template>
