<template>
  <div class="assistant-composer">
    <div class="assistant-composer__box" :class="{ disabled, 'has-skill': selectedSkill }" @click="focus">
      <button v-if="showAddButton" type="button" class="assistant-composer__icon-button" :disabled="disabled"
        aria-label="添加附件" @click.stop="emit('addFile')">
        <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
          <path d="M10 4v12" />
          <path d="M4 10h12" />
        </svg>
      </button>
      <div class="assistant-composer__input-wrap" @click.stop="focus">
        <span v-if="selectedSkill" class="assistant-composer__skill-prefix" @click.stop="focus">
          <span class="assistant-composer__skill-icon" aria-hidden="true">
            <svg viewBox="0 0 16 16" focusable="false">
              <path d="M8 1.8 3.2 4.4 8 7l4.8-2.6L8 1.8Z" />
              <path d="M3.2 5.8v5.4L8 14V8.6L3.2 5.8Z" />
              <path d="M12.8 5.8 8 8.6V14l4.8-2.8V5.8Z" />
            </svg>
          </span>
          <span>{{ selectedSkill.label }}</span>
          <button type="button" class="assistant-composer__skill-remove" aria-label="移除已选择技能" title="移除已选择技能"
            @click.stop="clearSelectedSkill">
            <svg viewBox="0 0 16 16" fill="none" focusable="false" aria-hidden="true">
              <path d="M4.5 4.5 11.5 11.5" />
              <path d="M11.5 4.5 4.5 11.5" />
            </svg>
          </button>
        </span>
        <textarea ref="textareaRef" name="assistant-message" aria-label="消息内容" autocomplete="off"
          :value="modelValue" :placeholder="placeholder" :disabled="disabled" rows="1"
          @input="handleInput" @click.stop @keydown="handleKeydown" />

        <div v-if="slashMenuVisible" class="assistant-composer__slash-menu" role="listbox" aria-label="命令和技能"
          @click.stop @pointerdown.stop>
          <template v-for="group in groupedEntries" :key="group.kind">
            <div v-if="group.items.length" class="assistant-composer__slash-group">
              <div class="assistant-composer__slash-heading">{{ group.label }}</div>
              <button v-for="entry in group.items" :key="`${entry.kind}:${entry.name}`" type="button" role="option"
                class="assistant-composer__slash-item"
                :class="{ active: flatEntries[highlightIndex]?.name === entry.name && flatEntries[highlightIndex]?.kind === entry.kind }"
                :data-kind="entry.kind" @pointerdown.stop.prevent="selectEntryByPointer(entry)"
                @click.stop.prevent="selectEntryByClick(entry)">
                <span class="assistant-composer__slash-icon" :data-icon="slashEntryIcon(entry)" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="none" focusable="false">
                    <template v-for="path in slashEntryIconPaths(entry)" :key="path">
                      <path :d="path" />
                    </template>
                  </svg>
                </span>
                <span class="assistant-composer__slash-copy">
                  <span class="assistant-composer__slash-title">{{ entry.label }}</span>
                  <span class="assistant-composer__slash-description">{{ entry.description }}</span>
                </span>
              </button>
            </div>
          </template>
          <div v-if="flatEntries.length === 0" class="assistant-composer__slash-empty">没有匹配项</div>
        </div>
      </div>
      <button type="button" class="assistant-composer__send" :disabled="sendDisabled"
        :aria-label="isRunning ? '停止生成' : '发送消息'" @click="handleSendClick">
        <svg v-if="isRunning" viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
          <rect x="5" y="5" width="10" height="10" rx="2" />
        </svg>
        <svg v-else viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
          <path d="M10 15V5" />
          <path d="M5.5 9.5 10 5l4.5 4.5" />
        </svg>
      </button>
    </div>

    <div v-if="hint" class="assistant-composer__hint">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { AssistantCatalog, AssistantSkill, AssistantSlashEntry } from '../../lib/assistantCatalog'
import { defaultAssistantCatalog, slashEntriesFromCatalog } from '../../lib/assistantCatalog'
import { buildSubmittedText, filterSlashEntries, isSlashMode, shouldClearSelectedSkillOnDelete } from '../../lib/assistantComposer'

const props = withDefaults(defineProps<{
  modelValue: string
  selectedSkill?: AssistantSkill | null
  catalog?: AssistantCatalog
  placeholder?: string
  disabled?: boolean
  isRunning?: boolean
  showAddButton?: boolean
  hint?: string
}>(), {
  modelValue: '',
  selectedSkill: null,
  catalog: () => defaultAssistantCatalog,
  placeholder: '直接提问，或选择常用能力',
  disabled: false,
  isRunning: false,
  showAddButton: false,
  hint: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  submit: [value: string]
  command: [value: string]
  selectSkill: [skill: AssistantSkill]
  clearSkill: []
  addFile: []
  stop: []
}>()

let pointerSelectionHandled = false
const TEXTAREA_MAX_HEIGHT = 148
const highlightIndex = ref(0)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const entries = computed(() => slashEntriesFromCatalog(props.catalog || defaultAssistantCatalog))
const flatEntries = computed(() => filterSlashEntries(entries.value, props.modelValue || ''))
const slashMenuVisible = computed(() => isSlashMode(props.modelValue || ''))
const groupedEntries = computed(() => [
  {
    kind: 'command',
    label: '命令',
    items: flatEntries.value.filter((entry) => entry.kind === 'command'),
  },
  {
    kind: 'skill',
    label: '技能',
    items: flatEntries.value.filter((entry) => entry.kind === 'skill'),
  },
])
const sendDisabled = computed(() => {
  if (props.isRunning) return false
  return props.disabled || (!String(props.modelValue || '').trim() && !props.selectedSkill)
})

watch(flatEntries, () => {
  if (!flatEntries.value.length) {
    highlightIndex.value = -1
    return
  }
  if (highlightIndex.value < 0 || highlightIndex.value >= flatEntries.value.length) {
    highlightIndex.value = 0
  }
})

watch(
  () => props.modelValue,
  () => {
    void nextTick(() => resizeTextarea())
  },
)

onMounted(() => {
  resizeTextarea()
})

function handleInput(event: Event) {
  const textarea = event.target as HTMLTextAreaElement
  resizeTextarea(textarea)
  emit('update:modelValue', textarea.value)
}

function resizeTextarea(target = textareaRef.value) {
  if (!target) return
  target.style.height = 'auto'
  const nextHeight = Math.min(target.scrollHeight, TEXTAREA_MAX_HEIGHT)
  target.style.height = `${nextHeight}px`
  target.style.overflowY = target.scrollHeight > TEXTAREA_MAX_HEIGHT ? 'auto' : 'hidden'
}

function handleKeydown(event: KeyboardEvent) {
  if (props.disabled) return
  const textarea = event.target as HTMLTextAreaElement | null
  if (shouldClearSelectedSkillOnDelete({
    key: event.key,
    hasSelectedSkill: Boolean(props.selectedSkill),
    value: textarea?.value ?? props.modelValue ?? '',
    selectionStart: textarea?.selectionStart ?? null,
    selectionEnd: textarea?.selectionEnd ?? null,
  })) {
    event.preventDefault()
    clearSelectedSkill()
    return
  }

  if (slashMenuVisible.value) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (flatEntries.value.length) highlightIndex.value = (highlightIndex.value + 1) % flatEntries.value.length
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (flatEntries.value.length) highlightIndex.value = highlightIndex.value <= 0 ? flatEntries.value.length - 1 : highlightIndex.value - 1
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      emit('update:modelValue', '')
      return
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      const selected = flatEntries.value[highlightIndex.value]
      if (selected) {
        event.preventDefault()
        selectEntry(selected)
        return
      }
    }
  }

  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}

function selectEntry(entry: AssistantSlashEntry) {
  if (entry.kind === 'command') {
    emit('update:modelValue', '')
    emit('clearSkill')
    emit('command', entry.message)
    return
  }
  emit('update:modelValue', '')
  emit('selectSkill', entry)
  void nextTick(() => focus())
}

function selectEntryByPointer(entry: AssistantSlashEntry) {
  pointerSelectionHandled = true
  selectEntry(entry)
  window.setTimeout(() => {
    pointerSelectionHandled = false
  }, 0)
}

function selectEntryByClick(entry: AssistantSlashEntry) {
  if (pointerSelectionHandled) return
  selectEntry(entry)
}

function slashEntryIcon(entry: AssistantSlashEntry) {
  if (entry.kind === 'skill') return 'skill'
  return `command-${entry.name}`
}

function slashEntryIconPaths(entry: AssistantSlashEntry) {
  if (entry.kind === 'skill') {
    return [
      'M10 2.5 4.5 5.5 10 8.5l5.5-3L10 2.5Z',
      'M4.5 7v6l5.5 3V10L4.5 7Z',
      'M15.5 7v6L10 16v-6l5.5-3Z',
    ]
  }
  switch (entry.name) {
    case 'help':
      return [
        'M10 17.5a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15Z',
        'M7.9 8a2.25 2.25 0 1 1 3.85 1.6c-.55.54-1.1.9-1.1 1.9',
        'M10 14h.01',
      ]
    case 'status':
      return [
        'M4 11a6 6 0 1 1 12 0',
        'M6 11h2',
        'M12 11h2',
        'M10 11l2.5-4',
      ]
    case 'context':
      return [
        'M4 5.5h12',
        'M4 10h12',
        'M4 14.5h8',
      ]
    case 'compact':
      return [
        'M4.5 5h11',
        'M4.5 10h11',
        'M4.5 15h11',
        'M7 3v4',
        'M13 8v4',
        'M9 13v4',
      ]
    case 'reset':
      return [
        'M5.5 7.5A5.5 5.5 0 1 1 5 12',
        'M5.5 4v3.5H9',
      ]
    default:
      return [
        'M5 5.5h10',
        'M5 10h10',
        'M5 14.5h6',
      ]
  }
}

function clearSelectedSkill() {
  emit('clearSkill')
  void nextTick(() => focus())
}

function handleSendClick() {
  if (props.isRunning) {
    emit('stop')
    return
  }
  submit()
}

function submit() {
  if (sendDisabled.value && !props.selectedSkill) return
  const value = buildSubmittedText(props.modelValue, props.selectedSkill)
  if (!value) return
  emit('submit', value)
}

function focus() {
  if (props.disabled) return
  const textarea = textareaRef.value
  if (!textarea) return
  textarea.focus()
  const end = textarea.value.length
  textarea.setSelectionRange(end, end)
}

defineExpose({ focus })
</script>

<style scoped>
/* 保持输入框主体部分原有样式不变 */
.assistant-composer {
  width: 100%;
  max-width: none;
  pointer-events: auto;
}

.assistant-composer__box {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: end;
  gap: 8px;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  background: #fff;
  box-shadow: none;
  padding: 8px 10px;
  cursor: text;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.assistant-composer__box:focus-within {
  border-color: #e6ebf2;
  box-shadow: 0 0 0 3px var(--cc-agent-focus-soft);
}

.assistant-composer__box.has-skill {
  border-color: var(--cc-agent-primary-border);
}

.assistant-composer__box.disabled {
  opacity: 0.68;
}

.assistant-composer__input-wrap {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}

/* 技能 Tag 样式保留 */
.assistant-composer__skill-prefix {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 6px;
  max-width: min(220px, 42vw);
  margin-top: 7px;
  border: 1px solid var(--cc-agent-primary-border);
  border-radius: 6px;
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
  cursor: text;
  padding: 2px 3px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
}

.assistant-composer__skill-prefix:hover {
  background: var(--cc-agent-primary-soft);
}

.assistant-composer__skill-prefix>span:nth-child(2) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-composer__skill-icon {
  display: inline-flex;
  width: 16px;
  height: 16px;
}

.assistant-composer__skill-icon svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-linejoin: round;
  stroke-width: 1.7;
}

.assistant-composer__skill-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 999px;
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0;
}

.assistant-composer__skill-remove svg {
  width: 12px;
  height: 12px;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-width: 1.8;
}

.assistant-composer__skill-remove:hover {
  background: var(--cc-agent-primary-border);
}

.assistant-composer textarea {
  width: 100%;
  min-width: 0;
  min-height: 38px;
  max-height: 148px;
  overflow-y: hidden;
  pointer-events: auto;
  resize: none;
  border: 0;
  outline: 0;
  background: transparent;
  color: #111827;
  font: inherit;
  line-height: 1.5;
  padding: 8px 0;
  font-size: 14px;
}

.assistant-composer textarea::placeholder {
  color: #9aa4b2;
}

.assistant-composer__icon-button,
.assistant-composer__send {
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  pointer-events: auto;
  line-height: 1;
  align-self: center;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.assistant-composer__icon-button {
  background: transparent;
  color: #526071;
}

.assistant-composer__icon-button svg,
.assistant-composer__send svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}

.assistant-composer__icon-button:hover {
  background: var(--cc-agent-primary-soft);
  color: var(--cc-agent-primary);
}

.assistant-composer__send {
  background: var(--cc-agent-primary);
  color: #fff;
}

.assistant-composer__send:hover:not(:disabled) {
  background: var(--cc-agent-primary-strong);
}

.assistant-composer__send:disabled {
  cursor: default;
  background: #eef2f7;
  color: #9aa3b2;
}

/* =========================================================
   重点优化：Slash 弹出面板样式优化，还原图一效果
   ========================================================= */

.assistant-composer__slash-menu {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 12px);
  z-index: 30;
  max-height: min(360px, 58vh);
  overflow-y: auto;
  overflow-x: hidden;

  /* 优化1：移除生硬的 border，改用柔和的投影模拟边框和立体感 */
  border: none;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.04),
    0 8px 30px rgba(0, 0, 0, 0.08),
    0 4px 12px rgba(0, 0, 0, 0.04);

  /* 优化2：调整整体内边距，让选项顶边/底边有一点呼吸空间 */
  padding: 6px;
}

/* 优化3：定制滚动条，使其像图一一样隐形且精致 (macOS 风格) */
.assistant-composer__slash-menu::-webkit-scrollbar {
  width: 6px;
}

.assistant-composer__slash-menu::-webkit-scrollbar-track {
  background: transparent;
}

.assistant-composer__slash-menu::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 4px;
}

.assistant-composer__slash-menu:hover::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.2);
}

.assistant-composer__slash-heading {
  /* 优化4：分组标题颜色变淡，字号调小，减少视觉干扰 */
  padding: 8px 10px 4px;
  color: #a0a6b1;
  font-size: 12px;
  font-weight: 400;
  line-height: 1.3;
}

.assistant-composer__slash-item {
  width: 100%;
  display: grid;
  /* 优化5：调整图标和文字的间距 */
  grid-template-columns: 20px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 38px;
  border: 0;
  /* 选中态的圆角稍小一点，配合外层容器更和谐 */
  border-radius: 8px;
  background: transparent;
  padding: 6px 10px;
  color: #262a31;
  text-align: left;
  cursor: pointer;
  transition: background-color 100ms ease, color 100ms ease;
}

/* 优化6：悬停和选中的背景色变得极其柔和 */
.assistant-composer__slash-item:hover,
.assistant-composer__slash-item.active {
  background: #f4f5f8;
}

.assistant-composer__slash-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: #64748b;
  /* 图标颜色稍微减弱一点 */
}

.assistant-composer__slash-icon svg {
  width: 17px;
  height: 17px;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
  /* 图标线条变细，更显精致 */
}

.assistant-composer__slash-copy {
  display: flex;
  min-width: 0;
  /* 优化7：将 baseline 改为 center，并增大标题和描述间的间距 */
  align-items: center;
  gap: 12px;
}

.assistant-composer__slash-title {
  flex: 0 0 auto;
  color: #1e293b;
  font-size: 14px;
  /* 字号略微缩小，显得更内敛 */
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
}

.assistant-composer__slash-description {
  min-width: 0;
  overflow: hidden;
  /* 优化8：描述文字颜色变浅，与标题形成明显层级 */
  color: #94a3b8;
  font-size: 13px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-composer__slash-empty,
.assistant-composer__hint {
  color: #94a3b8;
  font-size: 13px;
}

.assistant-composer__slash-empty {
  padding: 12px 10px;
  text-align: center;
}

.assistant-composer__hint {
  margin: 6px 12px 0;
}

/* 移动端适配调整 */
@media (max-width: 640px) {
  .assistant-composer__slash-menu {
    max-height: min(320px, 54vh);
    border-radius: 12px;
    padding: 6px;
  }

  .assistant-composer__slash-copy {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    /* 移动端上下堆叠时缩小间距 */
  }

  .assistant-composer__slash-title {
    max-width: 100%;
  }
}
</style>
