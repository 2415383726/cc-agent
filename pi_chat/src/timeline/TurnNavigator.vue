<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import css from '../vendor/dsh/ui-chat/src/client/chat/TurnNavigator.module.css'
import type { TurnRailItem } from './rail'

/*
 * 右侧回合导航轨（Vue 重写）。DOM 蓝图：ui-chat TurnNavigator.tsx（MIT）——
 * nav.frame（28px 宽、右 12px、垂直居中于 composer 之上的可视带、max 420px）
 * > div.scroller（无滚动条、两端 24px 渐隐遮罩）> div.marks（定距 10px 刻度）
 * > button.mark（20×2 刻度线：未激活 scaleX(0.6)、悬停 scaleX(0.9)、激活
 * scaleX(1) 主墨色）+ div.preview（悬停预览卡：问题 1 行 + 回答 3 行截断，
 * elevation-panel 阴影，top 随预览刻度平滑跟随）。
 * 偏离：上游用 @tanstack/react-virtual 固定节距虚拟化；本应用回合数有限，
 * 刻度以绝对定位 + marks 总高一次铺满（视觉与滚动/渐隐行为一致），
 * 「unloaded 刻度」与 busy 脉冲不适用（本应用无分页历史加载）。
 * 定位机制平移：.slot 渲染在滚动体内（data-conversation-scroll）借
 * position: sticky + height: 0 固定于视口（vendored CSS 原样生效）。
 */
const props = defineProps<{
  items: readonly TurnRailItem[]
  activeId: string | null
}>()

const emit = defineEmits<{ navigate: [item: TurnRailItem] }>()

/** 与上游一致的固定节距（TurnNavigator.tsx TURN_SPACING_PX）。 */
const TURN_SPACING_PX = 10
/** 上游 RAIL_INSET_PX：首尾刻度内缩（paddingStart/End = INSET - SPACING/2）。 */
const RAIL_INSET_PX = 6
/** 渐隐带宽度（上游 FADE_PX）。 */
const FADE_PX = 24

const scroller = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const viewHeight = ref(0)
const previewId = ref<string | null>(null)
/** 指针在轨上时跟随必须停手（上游 pointerInsideRef：预览不被滚动顶走）。 */
const pointerInside = ref(false)

const marksHeight = computed(() => props.items.length * TURN_SPACING_PX)
const activeIndex = computed(() => props.items.findIndex((item) => item.id === props.activeId))
const previewIndex = computed(() =>
  previewId.value === null ? -1 : props.items.findIndex((item) => item.id === previewId.value),
)
const preview = computed(() => (previewIndex.value >= 0 ? props.items[previewIndex.value] : null))

function onScroll(): void {
  const el = scroller.value
  if (!el) return
  scrollTop.value = el.scrollTop
  viewHeight.value = el.clientHeight
}

/* 视口高度初始测量（上游 observeElementRect 的 ResizeObserver 语义）：
   首次布局与尺寸变化时刷新，让激活刻度在无滚动事件时也能落位。 */
let frameObserver: ResizeObserver | null = null
onMounted(() => {
  const el = scroller.value
  if (el === null || typeof ResizeObserver === 'undefined') return
  frameObserver = new ResizeObserver(() => {
    viewHeight.value = el.clientHeight
    scrollTop.value = el.scrollTop
  })
  frameObserver.observe(el)
})
onBeforeUnmount(() => {
  frameObserver?.disconnect()
  frameObserver = null
})

/* 上游 scrollToIndex 的 if-needed 语义：激活刻度中心落在渐隐带内不动，
   否则居中；首次放置（无尺寸）与 reduced-motion 用瞬时滚动。 */
function followActive(behavior: 'auto' | 'smooth'): void {
  const el = scroller.value
  if (!el || activeIndex.value < 0 || viewHeight.value <= 0) return
  const center = RAIL_INSET_PX + activeIndex.value * TURN_SPACING_PX + TURN_SPACING_PX / 2
  const top = center - FADE_PX
  const bottom = center + FADE_PX
  if (top >= el.scrollTop && bottom <= el.scrollTop + viewHeight.value) return
  const target = Math.max(0, Math.min(el.scrollHeight - viewHeight.value, center - viewHeight.value / 2))
  if (target !== el.scrollTop) el.scrollTo({ top: target, behavior })
}

let lastItemCount = -1
watch(
  () => [props.activeId, props.items.length, viewHeight.value] as const,
  ([, count, height]) => {
    if (height <= 0) return
    if (pointerInside.value) return
    /* 会话切换（条目数变化）瞬时落位；同一会话内平滑跟随。 */
    followActive(lastItemCount !== count ? 'auto' : 'smooth')
    lastItemCount = count
  },
  { flush: 'post' },
)

/* 预览卡垂直中心（相对滚动视口）：刻度中心 - 滚动量。vendored CSS 把
   clamp(0px … 100% - 100px) 的约束交给 --turn-preview-center。 */
const previewCenter = computed(() => {
  if (previewIndex.value < 0) return 0
  const center = RAIL_INSET_PX + previewIndex.value * TURN_SPACING_PX + TURN_SPACING_PX / 2
  return center - scrollTop.value
})

function markStyle(index: number): Record<string, string> {
  return { top: `${RAIL_INSET_PX - TURN_SPACING_PX / 2 + index * TURN_SPACING_PX}px` }
}

function markLabel(item: TurnRailItem): string {
  const prompt = item.prompt.trim()
  return prompt !== '' ? prompt : '空回合'
}

function navigate(item: TurnRailItem): void {
  emit('navigate', item)
}
</script>

<template>
  <div v-if="items.length >= 2" :class="css.slot" data-testid="turn-navigator">
    <nav
      :class="css.frame"
      aria-label="回合导航"
      @pointerenter="pointerInside = true"
      @pointerleave="pointerInside = false; previewId = null"
    >
      <div
        ref="scroller"
        :class="[
          css.scroller,
          scrollTop > 1 && css.fadeTop,
          scrollTop < marksHeight + RAIL_INSET_PX * 2 - viewHeight - 1 && css.fadeBottom,
        ]"
        @scroll="onScroll"
      >
        <div :class="css.marks" :style="{ height: `${marksHeight + RAIL_INSET_PX * 2 - TURN_SPACING_PX}px` }">
          <button
            v-for="(item, index) in items"
            :key="item.id"
            :class="[
              css.mark,
              item.id === activeId && css.markActive,
              item.id === previewId && previewId !== activeId && css.markPreview,
            ]"
            :style="markStyle(index)"
            type="button"
            :aria-label="markLabel(item)"
            :aria-current="item.id === activeId ? 'true' : undefined"
            :data-testid="`turn-mark-${index}`"
            @pointermove="previewId = item.id"
            @focus="previewId = item.id"
            @blur="previewId = null"
            @click="navigate(item)"
          />
        </div>
      </div>
      <div
        v-if="preview !== null"
        role="tooltip"
        :class="css.preview"
        :style="{ '--turn-preview-center': `${previewCenter}px` }"
        data-testid="turn-preview"
      >
        <div :class="css.previewPrompt">{{ preview.prompt || '空回合' }}</div>
        <div v-if="preview.response !== ''" :class="css.previewResponse">{{ preview.response }}</div>
      </div>
    </nav>
  </div>
</template>
