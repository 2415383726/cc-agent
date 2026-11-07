<script setup lang="ts">
import css from '../vendor/dsh/ui-layout/src/client/AppFrame.module.css'

/*
 * DOM 蓝图：ui-layout AppFrame.tsx 的 .frame 三栏 grid（侧栏列 / 中心列 / 右栏列）。
 * 本票侧栏固定默认宽（columns.ts 的 SIDEBAR_DEFAULT = 280），右栏无轨道
 * （rightbar 0 → minmax(0px, 0px)）；拖拽调宽与折叠留待后续票据。
 */
withDefaults(defineProps<{ sidebarWidth?: number }>(), { sidebarWidth: 280 })
</script>

<template>
  <div
    :class="css.frame"
    :style="{ gridTemplateColumns: `${sidebarWidth}px minmax(0px, 1fr) minmax(0px, 0px)` }"
  >
    <aside :class="css.sidebarCol" data-zone="sidebar">
      <slot name="sidebar" />
    </aside>
    <div :class="css.centerCol">
      <slot />
    </div>
  </div>
</template>
