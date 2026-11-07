<script setup lang="ts">
import { computed } from 'vue'
import css from '../vendor/dsh/ui-primitives/src/SegmentedControl.module.css'

/*
 * dsh SegmentedControl 的 Vue 重写（上游 ui-primitives/SegmentedControl.tsx，
 * MIT：React 组件只作 DOM/类名蓝图）。CSS 类零改动引用 vendored
 * SegmentedControl.module.css（indicator 滑块由 --dsh-segment-count/
 * --dsh-segment-index 自定义属性算术定位，不量 DOM）。
 *
 * 一处有意偏离（上游注释同位）：上游是 tablist，用于「切换卡片/面板的几个
 * 模式」，每个 tab aria-controls 指向真实面板；本组件承载审批卡的授权范围
 * 这类「值选择」——选中不展示任何面板，tab 语义会让 aria-controls 指向不存在
 * 的元素，故语义改用 radiogroup/radio + aria-checked（WAI-ARIA radio 模式），
 * 视觉与键盘走选保持上游同款（方向键/Home/End 平移上游 walk）。
 */
export interface SegmentedOption<Value extends string> {
  /** 选中后 change 事件带回的值。 */
  value: Value
  /** 本地化段文案。 */
  label: string
}

const props = withDefaults(
  defineProps<{
    /** 当前选中值（受控）。 */
    value: string
    options: SegmentedOption<string>[]
    /** 读屏可访问名（上游 label 必填同款约束）。 */
    label: string
    /** 整组锁定（提交中）。 */
    disabled?: boolean
    /** 段按钮 data-testid 前缀（测试 seam；上游无此 prop）。 */
    testIdPrefix?: string
  }>(),
  { disabled: false, testIdPrefix: '' },
)

const emit = defineEmits<{ change: [next: string] }>()

const selectedIndex = computed(() => props.options.findIndex((option) => option.value === props.value))
const indicatorStyle = computed(() => ({
  '--dsh-segment-count': String(props.options.length),
  '--dsh-segment-index': String(selectedIndex.value),
}))

type WalkKey = 'ArrowLeft' | 'ArrowRight' | 'ArrowUp' | 'ArrowDown' | 'Home' | 'End'

function isWalkKey(key: string): key is WalkKey {
  return key === 'ArrowLeft' || key === 'ArrowRight' || key === 'ArrowUp' || key === 'ArrowDown'
    || key === 'Home' || key === 'End'
}

/** 上游 walk：方向键步进（环绕），Home/End 跳首尾；disabled 组无目标。 */
function walk(from: number, key: WalkKey): string | undefined {
  if (props.disabled) return undefined
  if (key === 'Home') return props.options[0]?.value
  if (key === 'End') return props.options[props.options.length - 1]?.value
  const step = key === 'ArrowRight' || key === 'ArrowDown' ? 1 : -1
  const count = props.options.length
  for (let offset = 1; offset < count; offset += 1) {
    const candidate = props.options[((from + step * offset) % count + count) % count]
    if (candidate !== undefined) return candidate.value
  }
  return undefined
}

function onKeydown(event: KeyboardEvent): void {
  if (!isWalkKey(event.key)) return
  event.preventDefault()
  const target = walk(selectedIndex.value, event.key)
  if (target !== undefined && target !== props.value) emit('change', target)
}

function choose(value: string): void {
  if (props.disabled || value === props.value) return
  emit('change', value)
}
</script>

<template>
  <div :class="css.control" role="radiogroup" :aria-label="label" :style="indicatorStyle" :data-testid="testIdPrefix ? testIdPrefix : undefined">
    <span aria-hidden="true" :class="css.indicator" />
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="radio"
      :aria-checked="option.value === value"
      :tabindex="option.value === value ? 0 : -1"
      :disabled="disabled"
      :class="css.tab"
      :data-testid="testIdPrefix ? `${testIdPrefix}-${option.value}` : undefined"
      @click="choose(option.value)"
      @keydown="onKeydown"
    >
      {{ option.label }}
    </button>
  </div>
</template>
