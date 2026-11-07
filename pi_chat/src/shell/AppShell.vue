<script setup lang="ts">
import { ref, watch } from 'vue'
import css from '../vendor/dsh/ui-layout/src/client/AppFrame.module.css'

/*
 * DOM 蓝图：ui-layout AppFrame.tsx 的 .frame 三栏 grid（侧栏列 / 中心列 / 右栏列）。
 * 折叠轨道（对齐 columns.ts SIDEBAR_DEFAULT = 280 / SIDEBAR_COLLAPSED = 56）：
 * 折叠时轨道过渡到 56px 导轨，data-sidebar-collapsed 标注折叠态；
 * data-animating 只在折叠/展开切换期间挂（上游语义：稳态窗口缩放不走缓动，
 * 只有离散的折叠/展开缓动 grid 轨道，--ds-transition-duration-slow）。
 * 右栏无轨道（rightbar 0 → minmax(0px, 0px)）；无调宽 prop（P3-5）。
 */
const props = withDefaults(defineProps<{ sidebarCollapsed?: boolean }>(), { sidebarCollapsed: false })

const SIDEBAR_WIDTH = 280
const SIDEBAR_COLLAPSED = 56
/** AppFrame 轨道过渡 = ui-theme --ds-transition-duration-slow（0.3s）+ 余量。 */
const ANIMATE_MS = 320

const animating = ref(false)
let animateTimer: number | undefined

watch(
  () => props.sidebarCollapsed,
  () => {
    animating.value = true
    if (animateTimer !== undefined) window.clearTimeout(animateTimer)
    animateTimer = window.setTimeout(() => {
      animating.value = false
    }, ANIMATE_MS)
  },
)
</script>

<template>
  <div
    :class="css.frame"
    :data-animating="animating ? '' : undefined"
    :data-sidebar-collapsed="sidebarCollapsed ? '' : undefined"
    :style="{ gridTemplateColumns: `${sidebarCollapsed ? SIDEBAR_COLLAPSED : SIDEBAR_WIDTH}px minmax(0px, 1fr) minmax(0px, 0px)` }"
  >
    <aside :class="css.sidebarCol" data-zone="sidebar">
      <slot name="sidebar" />
    </aside>
    <div :class="css.centerCol">
      <slot />
    </div>
  </div>
</template>
