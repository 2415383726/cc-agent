<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import css from '../vendor/dsh/ui-primitives/src/StateDot.module.css'

/*
 * dsh StateDot 的 Vue 重写子集（上游 ui-primitives/StateDot.tsx，MIT：React
 * 组件只作 DOM/类名蓝图）。实心四态（done/warning/error/idle）+ ongoing 转圈；
 * `step`（检查步）外观本应用没有调用点，裁剪。ongoing 的动画相位钉扎按上游
 * best-effort 平移（getAnimations 环境不支持时静默跳过，jsdom/happy-dom 同款）。
 * 审批卡阻断提示行（warning 点）与提交中（ongoing 转圈）使用。
 */
const props = withDefaults(
  defineProps<{ state: 'done' | 'warning' | 'ongoing' | 'error' | 'idle'; size?: number }>(),
  {},
)

const root = ref<SVGSVGElement | null>(null)

onMounted(() => {
  const spinner = root.value as (SVGSVGElement & { getAnimations?: (options?: { subtree?: boolean }) => Animation[] }) | null
  for (const animation of spinner?.getAnimations?.({ subtree: true }) ?? []) animation.startTime = 0
})

/* 尺寸取上游调用点默认：实心态 10px，ongoing 14px。 */
const edge = computed(() => props.size ?? (props.state === 'ongoing' ? 14 : 10))
</script>

<template>
  <svg
    v-if="state === 'ongoing'"
    ref="root"
    :class="css.spinner"
    data-state="ongoing"
    :width="edge"
    :height="edge"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <g :class="css.spinnerMotion">
      <circle :class="css.spinnerTrack" cx="12" cy="12" r="9.5" />
      <circle :class="css.spinnerArc" cx="12" cy="12" r="9.5" />
    </g>
  </svg>
  <span
    v-else
    :class="css.dot"
    :data-state="state"
    :style="{ width: `${edge}px`, height: `${edge}px` }"
    aria-hidden="true"
  />
</template>
