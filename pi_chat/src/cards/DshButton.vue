<script setup lang="ts">
import buttonCss from '../vendor/dsh/ui-primitives/src/Button.module.css'

/*
 * dsh Button 原子的 Vue 重写（上游 ui-primitives/Button.tsx，MIT：React 组件
 * 只作 DOM/类名蓝图，重写为 Vue SFC）。变体映射 --dsw-alias-button-* 令牌族；
 * outline 变体用 DPR 感知的 inset stroke。问卷卡（跳过/下一题）与审批卡
 * （票据 06）共用。
 */
withDefaults(defineProps<{ variant?: 'primary' | 'ghost' | 'outline'; size?: 'md' | 'sm' }>(), {
  variant: 'ghost',
  size: 'md',
})
</script>

<template>
  <button type="button" :class="[buttonCss.button, buttonCss[variant], buttonCss[size]]">
    <slot />
  </button>
</template>
