export interface InterruptOption {
  label: string
  value: string
  description?: string
  disabled?: boolean
}

export interface InterruptQuestion {
  id: string
  question: string
  purpose: string
  options: InterruptOption[]
  allowCustomInput: boolean
  multiSelect: boolean
  fields: InterruptField[]
}

export type InterruptFieldValue = string | number | boolean | string[]
export type InterruptFieldType =
  | 'text'
  | 'textarea'
  | 'select'
  | 'multiselect'
  | 'radio'
  | 'date'
  | 'daterange'
  | 'datetime'
  | 'number'
  | 'email'
  | 'tel'
  | 'checkbox'

export interface InterruptField {
  name: string
  label: string
  type: InterruptFieldType
  required: boolean
  description: string
  placeholder: string
  defaultValue: InterruptFieldValue
  options: InterruptOption[]
  group: string
  width: 'full' | 'half'
  min?: number
  max?: number
  step?: number
  maxLength?: number
  prefix: string
  suffix: string
}

const FIELD_TYPES = new Set<InterruptFieldType>([
  'text', 'textarea', 'select', 'multiselect', 'radio', 'date', 'daterange',
  'datetime', 'number', 'email', 'tel', 'checkbox',
])

export function normalizeInterruptQuestion(raw: any): InterruptQuestion {
  const source = raw && typeof raw === 'object' ? raw : {}
  const options = normalizeOptions(source.options)
  const fields = Array.isArray(source.fields)
    ? source.fields.map(normalizeInterruptField).filter((field: InterruptField | null): field is InterruptField => Boolean(field))
    : []

  return {
    id: String(source.id || source.promptId || source.tool_call_id || ''),
    question: String(source.question || source.text || ''),
    purpose: String(source.purpose || 'clarification'),
    options,
    allowCustomInput:
      'allowCustomInput' in source ? Boolean(source.allowCustomInput) : options.length === 0 && fields.length === 0,
    multiSelect: Boolean(source.multiSelect),
    fields,
  }
}

export function buildInterruptResumePayload(
  question: InterruptQuestion,
  selectedValues: string[],
  customInput: string,
  fieldValues: Record<string, InterruptFieldValue> = {},
) {
  const values = Array.isArray(selectedValues) ? selectedValues.filter(Boolean) : []
  const selectedLabels = values
    .map((value) => question.options.find((option) => option.value === value)?.label || value)
    .filter(Boolean)
  const custom = String(customInput || '').trim()
  const fieldLines = (question.fields || []).map((field) => {
    const formatted = formatFieldValue(fieldValues[field.name], field)
    return formatted ? `${field.label}：${formatted}` : ''
  }).filter(Boolean)
  const answer = [selectedLabels.join('、'), custom, ...fieldLines].filter(Boolean).join('\n')
  if (!answer) return null

  return {
    promptId: question.id,
    purpose: question.purpose,
    question: question.question,
    selectedLabels,
    selectedValues: values,
    customInput: custom,
    answer,
    values: fieldValues,
  }
}

function normalizeInterruptField(raw: any): InterruptField | null {
  if (!raw || typeof raw !== 'object') return null
  const name = String(raw.name || '').trim()
  const label = String(raw.label || name).trim()
  if (!name || !label) return null
  const type = FIELD_TYPES.has(raw.type) ? raw.type as InterruptFieldType : 'text'
  const options = normalizeOptions(raw.options)
  let defaultValue: InterruptFieldValue = type === 'checkbox' ? false : ['multiselect', 'daterange'].includes(type) ? [] : ''
  if (type === 'checkbox') defaultValue = Boolean(raw.defaultValue)
  else if (['multiselect', 'daterange'].includes(type) && Array.isArray(raw.defaultValue)) {
    defaultValue = raw.defaultValue.map(String).slice(0, type === 'daterange' ? 2 : undefined)
  } else if (type === 'number' && typeof raw.defaultValue === 'number' && Number.isFinite(raw.defaultValue)) {
    defaultValue = raw.defaultValue
  } else if (raw.defaultValue !== undefined && raw.defaultValue !== null) {
    defaultValue = String(raw.defaultValue)
  }
  const width = raw.width === 'half' && type !== 'textarea' && type !== 'checkbox' ? 'half' : 'full'
  return {
    name,
    label,
    type,
    required: Boolean(raw.required),
    description: String(raw.description || ''),
    placeholder: String(raw.placeholder || ''),
    defaultValue,
    options,
    group: String(raw.group || ''),
    width,
    min: finiteNumber(raw.min),
    max: finiteNumber(raw.max),
    step: finiteNumber(raw.step),
    maxLength: positiveInteger(raw.maxLength),
    prefix: String(raw.prefix || ''),
    suffix: String(raw.suffix || ''),
  }
}

function normalizeOptions(raw: any): InterruptOption[] {
  if (!Array.isArray(raw)) return []
  return raw.map((option: any): InterruptOption | null => {
    if (typeof option === 'string') return { label: option, value: option, description: '' }
    const label = String(option?.label || option?.text || option?.value || '').trim()
    if (!label) return null
    const disabled = Boolean(option?.disabled)
    return {
      label,
      value: String(option?.value || label),
      description: String(option?.description || ''),
      ...(disabled ? { disabled: true } : {}),
    }
  }).filter((option: InterruptOption | null): option is InterruptOption => Boolean(option))
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function positiveInteger(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : undefined
}

function formatFieldValue(value: InterruptFieldValue | undefined, field: InterruptField) {
  if (Array.isArray(value)) return value.join(field.type === 'daterange' ? ' 至 ' : '、')
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value ?? '').trim()
}
