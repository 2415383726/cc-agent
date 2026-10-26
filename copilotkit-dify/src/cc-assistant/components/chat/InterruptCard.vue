<template>
  <form ref="formRef" class="interrupt-card" novalidate @submit.prevent="submit">
    <header class="interrupt-header">
      <div class="interrupt-kicker">
        <span class="interrupt-kicker__mark" aria-hidden="true" />
        {{ title }}
      </div>
      <p class="interrupt-question">{{ question.question }}</p>
      <p v-if="question.fields.length" class="interrupt-guidance">
        填写后将从当前步骤继续，不会创建新的对话。
      </p>
    </header>

    <div v-if="fieldGroups.length" class="interrupt-field-groups">
      <section v-for="group in fieldGroups" :key="group.key" class="interrupt-field-group">
        <div v-if="group.title" class="interrupt-field-group__heading">
          <span>{{ group.title }}</span>
          <i aria-hidden="true" />
        </div>

        <div class="interrupt-fields">
          <div
            v-for="field in group.fields"
            :key="field.name"
            class="interrupt-field"
            :data-field="safeId(field.name)"
            :class="[`is-${field.type}`, `is-${field.width}`, { 'has-error': fieldErrors[field.name] }]"
          >
            <fieldset v-if="field.type === 'radio' || field.type === 'multiselect'" class="interrupt-choice-field">
              <legend>
                {{ field.label }}<em v-if="field.required" aria-hidden="true">*</em>
              </legend>
              <p v-if="field.description" :id="descriptionId(field.name)" class="interrupt-field-description">
                {{ field.description }}
              </p>
              <div class="interrupt-field-options" :class="{ compact: field.options.length > 4 }">
                <label
                  v-for="(option, optionIndex) in field.options"
                  :key="option.value"
                  class="interrupt-field-option"
                  :class="{ selected: isFieldOptionSelected(field.name, option.value), disabled: option.disabled }"
                  :for="optionId(field.name, optionIndex)"
                >
                  <input
                    v-if="field.type === 'multiselect'"
                    :id="optionId(field.name, optionIndex)"
                    v-model="fieldValues[field.name] as string[]"
                    type="checkbox"
                    :name="field.name"
                    :value="option.value"
                    :disabled="isSubmitting || option.disabled"
                    :aria-invalid="Boolean(fieldErrors[field.name])"
                    :aria-describedby="describedBy(field)"
                  >
                  <input
                    v-else
                    :id="optionId(field.name, optionIndex)"
                    v-model="fieldValues[field.name] as string"
                    type="radio"
                    :name="field.name"
                    :value="option.value"
                    :disabled="isSubmitting || option.disabled"
                    :aria-invalid="Boolean(fieldErrors[field.name])"
                    :aria-describedby="describedBy(field)"
                  >
                  <span class="interrupt-option-indicator" aria-hidden="true" />
                  <span class="interrupt-option-copy">
                    <strong>{{ option.label }}</strong>
                    <small v-if="option.description">{{ option.description }}</small>
                  </span>
                </label>
              </div>
            </fieldset>

            <label v-else-if="field.type === 'checkbox'" class="interrupt-boolean" :for="fieldId(field.name)">
              <input
                :id="fieldId(field.name)"
                v-model="fieldValues[field.name] as boolean"
                type="checkbox"
                :name="field.name"
                :disabled="isSubmitting"
                :aria-invalid="Boolean(fieldErrors[field.name])"
                :aria-describedby="describedBy(field)"
                autocomplete="off"
              >
              <span class="interrupt-boolean__control" aria-hidden="true" />
              <span class="interrupt-boolean__copy">
                <strong>{{ field.label }}<em v-if="field.required" aria-hidden="true">*</em></strong>
                <small v-if="field.description">{{ field.description }}</small>
              </span>
            </label>

            <template v-else>
              <label class="interrupt-field-label" :for="fieldId(field.name)">
                {{ field.label }}<em v-if="field.required" aria-hidden="true">*</em>
              </label>
              <p v-if="field.description" :id="descriptionId(field.name)" class="interrupt-field-description">
                {{ field.description }}
              </p>

              <textarea
                v-if="field.type === 'textarea'"
                :id="fieldId(field.name)"
                v-model="fieldValues[field.name] as string"
                :name="field.name"
                :placeholder="placeholderText(field.placeholder)"
                :maxlength="field.maxLength"
                :disabled="isSubmitting"
                :aria-invalid="Boolean(fieldErrors[field.name])"
                :aria-describedby="describedBy(field)"
                autocomplete="off"
                rows="4"
              />

              <select
                v-else-if="field.type === 'select'"
                :id="fieldId(field.name)"
                v-model="fieldValues[field.name] as string"
                :name="field.name"
                :disabled="isSubmitting"
                :aria-invalid="Boolean(fieldErrors[field.name])"
                :aria-describedby="describedBy(field)"
                autocomplete="off"
              >
                <option value="">请选择…</option>
                <option v-for="option in field.options" :key="option.value" :value="option.value" :disabled="option.disabled">
                  {{ option.label }}
                </option>
              </select>

              <div v-else-if="field.type === 'daterange'" class="interrupt-date-range">
                <label :for="rangeId(field.name, 0)">
                  <span>开始日期</span>
                  <input
                    :id="rangeId(field.name, 0)"
                    type="date"
                    :name="`${field.name}_start`"
                    :value="rangePart(field.name, 0)"
                    :disabled="isSubmitting"
                    :aria-invalid="Boolean(fieldErrors[field.name])"
                    :aria-describedby="describedBy(field)"
                    autocomplete="off"
                    @input="updateRange(field.name, 0, $event)"
                  >
                </label>
                <span class="interrupt-date-range__separator" aria-hidden="true">至</span>
                <label :for="rangeId(field.name, 1)">
                  <span>结束日期</span>
                  <input
                    :id="rangeId(field.name, 1)"
                    type="date"
                    :name="`${field.name}_end`"
                    :value="rangePart(field.name, 1)"
                    :disabled="isSubmitting"
                    :aria-invalid="Boolean(fieldErrors[field.name])"
                    :aria-describedby="describedBy(field)"
                    autocomplete="off"
                    @input="updateRange(field.name, 1, $event)"
                  >
                </label>
              </div>

              <div v-else class="interrupt-control-shell" :class="{ 'has-prefix': field.prefix, 'has-suffix': field.suffix }">
                <span v-if="field.prefix" class="interrupt-control-affix" aria-hidden="true">{{ field.prefix }}</span>
                <input
                  v-if="field.type === 'number'"
                  :id="fieldId(field.name)"
                  v-model.number="fieldValues[field.name] as number | string"
                  type="number"
                  inputmode="decimal"
                  :name="field.name"
                  :placeholder="placeholderText(field.placeholder)"
                  :min="field.min"
                  :max="field.max"
                  :step="field.step"
                  :disabled="isSubmitting"
                  :aria-invalid="Boolean(fieldErrors[field.name])"
                  :aria-describedby="describedBy(field)"
                  autocomplete="off"
                >
                <input
                  v-else
                  :id="fieldId(field.name)"
                  v-model="fieldValues[field.name] as string"
                  :type="inputType(field.type)"
                  :inputmode="field.type === 'tel' ? 'tel' : field.type === 'email' ? 'email' : undefined"
                  :name="field.name"
                  :placeholder="placeholderText(field.placeholder)"
                  :maxlength="field.maxLength"
                  :disabled="isSubmitting"
                  :aria-invalid="Boolean(fieldErrors[field.name])"
                  :aria-describedby="describedBy(field)"
                  :spellcheck="field.type === 'email' ? false : undefined"
                  autocomplete="off"
                >
                <span v-if="field.suffix" class="interrupt-control-affix" aria-hidden="true">{{ field.suffix }}</span>
              </div>
            </template>

            <small v-if="fieldErrors[field.name]" :id="errorId(field.name)" class="interrupt-field-error" role="alert">
              {{ fieldErrors[field.name] }}
            </small>
          </div>
        </div>
      </section>
    </div>

    <fieldset v-if="question.options.length" class="interrupt-response-options">
      <legend>{{ question.fields.length ? '下一步选择' : '请选择' }}</legend>
      <div class="interrupt-options">
        <label
          v-for="(option, index) in question.options"
          :key="option.value"
          class="interrupt-option"
          :class="{ selected: isQuestionOptionSelected(option.value), disabled: option.disabled }"
          :for="questionOptionId(index)"
        >
          <input
            v-if="question.multiSelect"
            :id="questionOptionId(index)"
            v-model="selectedValues"
            type="checkbox"
            name="interrupt-options"
            :value="option.value"
            :disabled="isSubmitting || option.disabled"
          >
          <input
            v-else
            :id="questionOptionId(index)"
            v-model="singleValue"
            type="radio"
            name="interrupt-option"
            :value="option.value"
            :disabled="isSubmitting || option.disabled"
          >
          <span class="interrupt-option-indicator" aria-hidden="true" />
          <span class="interrupt-option-copy">
            <strong>{{ option.label }}</strong>
            <small v-if="option.description">{{ option.description }}</small>
          </span>
        </label>
      </div>
    </fieldset>

    <div v-if="question.allowCustomInput" class="interrupt-custom-input">
      <label :for="customInputId">补充说明</label>
      <textarea
        :id="customInputId"
        v-model="customInput"
        class="interrupt-input"
        name="customInput"
        rows="3"
        :disabled="isSubmitting"
        autocomplete="off"
        placeholder="补充你的选择或直接输入回答…"
      />
    </div>

    <p v-if="submissionError" class="interrupt-submit-error" role="alert" aria-live="polite">
      {{ submissionError }}
    </p>

    <footer class="interrupt-actions">
      <span class="interrupt-actions__note">带 <em>*</em> 的项目必须填写</span>
      <button class="primary" type="submit" :disabled="!canSubmit">
        <span v-if="isSubmitting" class="interrupt-spinner" aria-hidden="true" />
        {{ isSubmitting ? '正在继续…' : submitLabel }}
      </button>
    </footer>
  </form>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import {
  buildInterruptResumePayload,
  type InterruptField,
  type InterruptFieldType,
  type InterruptFieldValue,
  type InterruptQuestion,
} from '../../lib/question'

const props = defineProps<{
  question: InterruptQuestion
  resolve: (payload: unknown) => unknown | Promise<unknown>
}>()

const formRef = ref<HTMLFormElement | null>(null)
const selectedValues = ref<string[]>([])
const singleValue = ref('')
const customInput = ref('')
const isSubmitting = ref(false)
const submissionError = ref('')
const fieldValues = reactive<Record<string, InterruptFieldValue>>({})
const fieldErrors = reactive<Record<string, string>>({})

watch(() => props.question, (question) => {
  selectedValues.value = []
  singleValue.value = ''
  customInput.value = ''
  isSubmitting.value = false
  submissionError.value = ''
  for (const key of Object.keys(fieldValues)) delete fieldValues[key]
  for (const field of question.fields || []) {
    fieldValues[field.name] = Array.isArray(field.defaultValue) ? [...field.defaultValue] : field.defaultValue
  }
  for (const key of Object.keys(fieldErrors)) delete fieldErrors[key]
}, { immediate: true, deep: true })

const title = computed(() => {
  if (props.question.purpose === 'approval') return '等待业务确认'
  return props.question.fields.length ? '补充业务信息' : '需要你的选择'
})

const submitLabel = computed(() => props.question.purpose === 'approval' ? '确认并继续' : '提交并继续')
const customInputId = computed(() => `${questionId.value}-custom`)
const questionId = computed(() => `interrupt-${safeId(props.question.id || 'prompt')}`)
const fieldGroups = computed(() => {
  const groups = new Map<string, { key: string; title: string; fields: InterruptField[] }>()
  for (const field of props.question.fields || []) {
    const title = field.group.trim()
    const key = title || '__default__'
    if (!groups.has(key)) groups.set(key, { key, title, fields: [] })
    groups.get(key)!.fields.push(field)
  }
  return [...groups.values()]
})

const effectiveValues = computed(() =>
  props.question.multiSelect
    ? selectedValues.value
    : (singleValue.value ? [singleValue.value] : []),
)

const canSubmit = computed(() => !isSubmitting.value && (
  props.question.fields.length > 0
  || props.question.options.length > 0
  || effectiveValues.value.length > 0
  || customInput.value.trim().length > 0
))

async function submit() {
  if (isSubmitting.value || !validateFields()) return
  const payload = buildInterruptResumePayload(
    props.question,
    effectiveValues.value,
    customInput.value,
    { ...fieldValues },
  )
  if (!payload) {
    submissionError.value = '请至少填写一项内容后再继续。'
    return
  }
  isSubmitting.value = true
  submissionError.value = ''
  try {
    await Promise.resolve(props.resolve(payload))
  } catch (_) {
    isSubmitting.value = false
    submissionError.value = '提交未完成，请检查连接后重试。'
  }
}

function validateFields() {
  for (const key of Object.keys(fieldErrors)) delete fieldErrors[key]
  submissionError.value = ''
  for (const field of props.question.fields || []) {
    const value = fieldValues[field.name]
    const text = Array.isArray(value) ? value : String(value ?? '').trim()
    const missing = Array.isArray(value)
      ? value.length === 0 || (field.type === 'daterange' && value.filter(Boolean).length < 2)
      : field.type === 'checkbox'
        ? value !== true
        : text === ''
    if (field.required && missing) {
      fieldErrors[field.name] = field.type === 'daterange' ? `请选择完整的${field.label}` : `请填写${field.label}`
      continue
    }
    if (field.type === 'daterange' && Array.isArray(value) && value.some(Boolean) && value.filter(Boolean).length < 2) {
      fieldErrors[field.name] = `请选择完整的${field.label}`
    } else if (field.type === 'daterange' && Array.isArray(value) && value[0] && value[1] && value[0] > value[1]) {
      fieldErrors[field.name] = '结束日期不能早于开始日期'
    } else if (field.type === 'number' && value !== '' && typeof value === 'number') {
      if (field.min !== undefined && value < field.min) fieldErrors[field.name] = `${field.label}不能小于 ${field.min}`
      else if (field.max !== undefined && value > field.max) fieldErrors[field.name] = `${field.label}不能大于 ${field.max}`
    } else if (field.type === 'email' && text && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(text))) {
      fieldErrors[field.name] = '请输入有效的邮箱地址'
    } else if (field.maxLength && typeof text === 'string' && text.length > field.maxLength) {
      fieldErrors[field.name] = `${field.label}不能超过 ${field.maxLength} 个字符`
    }
  }
  const firstError = Object.keys(fieldErrors)[0]
  if (firstError) {
    void nextTick(() => {
      const container = formRef.value?.querySelector<HTMLElement>(`.interrupt-field[data-field="${safeId(firstError)}"]`)
        || formRef.value?.querySelector<HTMLElement>('.interrupt-field.has-error')
      container?.querySelector<HTMLElement>('input, textarea, select')?.focus()
    })
  }
  return !firstError
}

function fieldId(name: string) {
  return `${questionId.value}-${safeId(name)}`
}

function descriptionId(name: string) {
  return `${fieldId(name)}-description`
}

function errorId(name: string) {
  return `${fieldId(name)}-error`
}

function describedBy(field: InterruptField) {
  return [field.description ? descriptionId(field.name) : '', fieldErrors[field.name] ? errorId(field.name) : ''].filter(Boolean).join(' ') || undefined
}

function optionId(name: string, index: number) {
  return `${fieldId(name)}-option-${index}`
}

function questionOptionId(index: number) {
  return `${questionId.value}-option-${index}`
}

function rangeId(name: string, index: number) {
  return `${fieldId(name)}-${index === 0 ? 'start' : 'end'}`
}

function rangePart(name: string, index: number) {
  const value = fieldValues[name]
  return Array.isArray(value) ? value[index] || '' : ''
}

function updateRange(name: string, index: number, event: Event) {
  const current = Array.isArray(fieldValues[name]) ? [...fieldValues[name] as string[]] : ['', '']
  while (current.length < 2) current.push('')
  current[index] = (event.target as HTMLInputElement).value
  fieldValues[name] = current.slice(0, 2)
}

function inputType(type: InterruptFieldType) {
  if (type === 'datetime') return 'datetime-local'
  if (['date', 'email', 'tel'].includes(type)) return type
  return 'text'
}

function placeholderText(value: string) {
  const text = value.trim()
  if (!text) return undefined
  return /[…。！？!?]$/.test(text) ? text : `${text}…`
}

function isFieldOptionSelected(name: string, value: string) {
  const current = fieldValues[name]
  return Array.isArray(current) ? current.includes(value) : current === value
}

function isQuestionOptionSelected(value: string) {
  return props.question.multiSelect ? selectedValues.value.includes(value) : singleValue.value === value
}

function safeId(value: string) {
  return String(value).replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'field'
}
</script>

<style scoped>
.interrupt-card {
  box-sizing: border-box;
  width: 100%;
  margin: 4px 0;
  border: 1px solid var(--cc-agent-line);
  border-radius: 10px;
  padding: 0;
  overflow: hidden;
  background: var(--cc-agent-surface);
  color: var(--cc-agent-text);
}

.interrupt-header {
  padding: 16px 18px 14px;
  border-bottom: 1px solid var(--cc-agent-line);
  background: linear-gradient(90deg, var(--cc-agent-surface-alt), var(--cc-agent-surface));
}

.interrupt-kicker {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 7px;
  color: var(--cc-agent-primary);
  font-size: 12px;
  font-weight: 750;
  letter-spacing: .04em;
}

.interrupt-kicker__mark {
  width: 7px;
  height: 7px;
  border-radius: 2px;
  background: var(--cc-agent-primary);
  box-shadow: 0 0 0 3px var(--cc-agent-primary-soft);
}

.interrupt-question {
  margin: 0;
  color: var(--cc-agent-text);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.55;
  overflow-wrap: anywhere;
  text-wrap: pretty;
}

.interrupt-guidance {
  margin: 5px 0 0;
  color: var(--cc-agent-muted);
  font-size: 12px;
  line-height: 1.5;
}

.interrupt-field-groups {
  display: grid;
}

.interrupt-field-group {
  padding: 16px 18px 18px;
}

.interrupt-field-group + .interrupt-field-group {
  border-top: 1px solid var(--cc-agent-line);
}

.interrupt-field-group__heading {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 13px;
  color: var(--cc-agent-text);
  font-size: 12px;
  font-weight: 750;
}

.interrupt-field-group__heading i {
  height: 1px;
  flex: 1;
  background: var(--cc-agent-line);
}

.interrupt-fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 15px 14px;
}

.interrupt-field {
  min-width: 0;
  grid-column: 1 / -1;
}

.interrupt-field.is-half {
  grid-column: span 1;
}

.interrupt-field-label,
.interrupt-choice-field legend {
  display: block;
  margin: 0 0 6px;
  padding: 0;
  color: var(--cc-agent-text);
  font-size: 12.5px;
  font-weight: 700;
}

.interrupt-field-label em,
.interrupt-choice-field legend em,
.interrupt-boolean em,
.interrupt-actions__note em {
  margin-left: 3px;
  color: #b42318;
  font-style: normal;
}

.interrupt-field-description {
  margin: -2px 0 7px;
  color: var(--cc-agent-muted);
  font-size: 11.5px;
  font-weight: 400;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.interrupt-choice-field,
.interrupt-response-options {
  min-width: 0;
  margin: 0;
  border: 0;
  padding: 0;
}

.interrupt-card input:not([type="checkbox"]):not([type="radio"]),
.interrupt-card textarea,
.interrupt-card select {
  box-sizing: border-box;
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--cc-agent-line-strong, var(--cc-agent-line));
  border-radius: 7px;
  padding: 9px 11px;
  background: var(--cc-agent-surface);
  color: var(--cc-agent-text);
  font: inherit;
  font-size: 13px;
  font-weight: 450;
}

.interrupt-card textarea {
  min-height: 92px;
  resize: vertical;
  line-height: 1.55;
}

.interrupt-card select {
  cursor: pointer;
}

.interrupt-card input:focus-visible,
.interrupt-card textarea:focus-visible,
.interrupt-card select:focus-visible,
.interrupt-field-option:focus-within,
.interrupt-option:focus-within,
.interrupt-boolean:focus-within {
  outline: 2px solid var(--cc-agent-focus);
  outline-offset: 2px;
}

.interrupt-field.has-error input,
.interrupt-field.has-error textarea,
.interrupt-field.has-error select,
.interrupt-field.has-error .interrupt-field-option,
.interrupt-field.has-error .interrupt-boolean {
  border-color: #d92d20;
}

.interrupt-control-shell {
  display: flex;
  align-items: stretch;
  border: 1px solid var(--cc-agent-line-strong, var(--cc-agent-line));
  border-radius: 7px;
  overflow: hidden;
  background: var(--cc-agent-surface);
}

.interrupt-control-shell:focus-within {
  outline: 2px solid var(--cc-agent-focus);
  outline-offset: 2px;
}

.interrupt-control-shell input:not([type="checkbox"]):not([type="radio"]) {
  min-width: 0;
  border: 0;
  border-radius: 0;
  outline: 0;
}

.interrupt-control-affix {
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  background: var(--cc-agent-surface-alt);
  color: var(--cc-agent-muted);
  font-size: 12px;
  white-space: nowrap;
}

.interrupt-control-shell.has-prefix .interrupt-control-affix:first-child {
  border-right: 1px solid var(--cc-agent-line);
}

.interrupt-control-shell.has-suffix .interrupt-control-affix:last-child {
  border-left: 1px solid var(--cc-agent-line);
}

.interrupt-field-options,
.interrupt-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.interrupt-field-options.compact {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.interrupt-field-option,
.interrupt-option,
.interrupt-boolean {
  box-sizing: border-box;
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 9px;
  border: 1px solid var(--cc-agent-line);
  border-radius: 8px;
  padding: 10px 11px;
  background: var(--cc-agent-surface);
  cursor: pointer;
  touch-action: manipulation;
  transition: border-color 140ms ease, background-color 140ms ease, color 140ms ease;
}

.interrupt-field-option:hover,
.interrupt-option:hover,
.interrupt-boolean:hover {
  border-color: var(--cc-agent-primary-border);
  background: var(--cc-agent-primary-soft);
}

.interrupt-field-option.selected,
.interrupt-option.selected {
  border-color: var(--cc-agent-primary);
  background: var(--cc-agent-primary-soft);
}

.interrupt-field-option.disabled,
.interrupt-option.disabled {
  opacity: .5;
  cursor: not-allowed;
}

.interrupt-field-option input,
.interrupt-option input,
.interrupt-boolean input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.interrupt-option-indicator,
.interrupt-boolean__control {
  box-sizing: border-box;
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
  margin-top: 1px;
  border: 1.5px solid var(--cc-agent-line-strong, #98a2b3);
  background: var(--cc-agent-surface);
}

.interrupt-field-option:has(input[type="radio"]) .interrupt-option-indicator,
.interrupt-option:has(input[type="radio"]) .interrupt-option-indicator {
  border-radius: 50%;
}

.selected .interrupt-option-indicator,
.interrupt-boolean:has(input:checked) .interrupt-boolean__control {
  border: 4px solid var(--cc-agent-primary);
}

.interrupt-field-option:has(input[type="checkbox"]) .interrupt-option-indicator,
.interrupt-option:has(input[type="checkbox"]) .interrupt-option-indicator,
.interrupt-boolean__control {
  border-radius: 4px;
}

.interrupt-option-copy,
.interrupt-boolean__copy {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.interrupt-option-copy strong,
.interrupt-boolean__copy strong {
  color: var(--cc-agent-text);
  font-size: 12.5px;
  font-weight: 700;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.interrupt-option-copy small,
.interrupt-boolean__copy small {
  color: var(--cc-agent-muted);
  font-size: 11.5px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.interrupt-date-range {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: end;
  gap: 8px;
}

.interrupt-date-range label {
  display: grid;
  gap: 4px;
}

.interrupt-date-range label > span {
  color: var(--cc-agent-muted);
  font-size: 10.5px;
}

.interrupt-date-range__separator {
  padding-bottom: 11px;
  color: var(--cc-agent-muted);
  font-size: 11px;
}

.interrupt-field-error,
.interrupt-submit-error {
  display: block;
  margin-top: 5px;
  color: #b42318;
  font-size: 11.5px;
  font-weight: 550;
  line-height: 1.4;
}

.interrupt-response-options,
.interrupt-custom-input {
  margin: 0;
  border-top: 1px solid var(--cc-agent-line);
  padding: 16px 18px;
}

.interrupt-response-options > legend,
.interrupt-custom-input > label {
  margin-bottom: 8px;
  color: var(--cc-agent-text);
  font-size: 12.5px;
  font-weight: 700;
}

.interrupt-custom-input > label {
  display: block;
}

.interrupt-input {
  margin: 0;
}

.interrupt-submit-error {
  margin: 0;
  border-top: 1px solid #fecdca;
  padding: 10px 18px;
  background: #fffbfa;
}

.interrupt-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0;
  border-top: 1px solid var(--cc-agent-line);
  padding: 12px 18px;
  background: var(--cc-agent-surface-alt);
}

.interrupt-actions__note {
  color: var(--cc-agent-muted);
  font-size: 11px;
}

.interrupt-actions .primary {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid var(--cc-agent-primary);
  border-radius: 7px;
  padding: 8px 14px;
  background: var(--cc-agent-primary);
  color: #fff;
  cursor: pointer;
  font: inherit;
  font-size: 12.5px;
  font-weight: 750;
  touch-action: manipulation;
  transition: background-color 140ms ease, border-color 140ms ease, opacity 140ms ease;
}

.interrupt-actions .primary:hover:not(:disabled) {
  border-color: var(--cc-agent-primary-hover, #1d4ed8);
  background: var(--cc-agent-primary-hover, #1d4ed8);
}

.interrupt-actions .primary:focus-visible {
  outline: 2px solid var(--cc-agent-focus);
  outline-offset: 2px;
}

.interrupt-actions .primary:disabled {
  opacity: .58;
  cursor: not-allowed;
}

.interrupt-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, .45);
  border-top-color: #fff;
  border-radius: 50%;
  animation: interrupt-spin 700ms linear infinite;
}

@keyframes interrupt-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 620px) {
  .interrupt-header,
  .interrupt-field-group,
  .interrupt-response-options,
  .interrupt-custom-input,
  .interrupt-actions {
    padding-left: 14px;
    padding-right: 14px;
  }

  .interrupt-fields,
  .interrupt-field-options,
  .interrupt-field-options.compact,
  .interrupt-options {
    grid-template-columns: minmax(0, 1fr);
  }

  .interrupt-field.is-half {
    grid-column: 1 / -1;
  }

  .interrupt-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .interrupt-actions .primary {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .interrupt-field-option,
  .interrupt-option,
  .interrupt-boolean,
  .interrupt-actions .primary {
    transition: none;
  }

  .interrupt-spinner {
    animation: none;
  }
}
</style>
