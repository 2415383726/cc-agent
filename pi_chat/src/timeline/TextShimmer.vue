<script setup lang="ts">
import css from '../vendor/dsh/ui-primitives/src/TextShimmer.module.css'

/*
 * DOM 蓝图：ui-primitives TextShimmer.tsx（MIT）——
 * span.root[data-shimmer] > span.content + (active 时) span.decoration[aria-hidden]
 * > span.sweep > span.highlight。装饰层复制同一份文本、双层反向位移 +
 * 线性渐变 mask 形成 shimmer 扫光；keyframes 与颜色令牌都在 vendored CSS 内。
 * 偏离：React context 传播省略（本应用只有一层用法）。
 */
defineProps<{
  text: string
  active?: boolean
}>()
</script>

<template>
  <span :class="css.root" :data-shimmer="active ? '' : undefined">
    <span :class="css.content">
      <span :class="css.text">{{ text }}</span>
    </span>
    <span v-if="active" :class="css.decoration" aria-hidden="true" inert>
      <span :class="css.sweep">
        <span :class="[css.content, css.highlight]">
          <span :class="css.text">{{ text }}</span>
        </span>
      </span>
    </span>
  </span>
</template>
