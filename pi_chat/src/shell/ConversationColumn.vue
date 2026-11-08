<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import css from '../vendor/dsh/ui-conversation/src/client/skeleton/ConversationRoot.module.css'
import TurnNavigator from '../timeline/TurnNavigator.vue'
import { smoothScrollTo } from '../timeline/smoothScroll'
import type { TurnRailItem } from '../timeline/rail'

/*
 * DOM 蓝图：ui-conversation skeleton/ConversationRoot.tsx 的 active 相态骨架：
 * .header（titleRow：titleCluster + headerActions）→ .body → .scrollBody（时间线
 * 滚动区，default slot）→ .composerSeat（composer 槽）。data-phase="active" 激活
 * 上游的 sticky composer 座位与渐变遮罩；宽度轴变量（--dsh-chat-content-width 等）
 * 随 .body 类生效。连接设置由父级通过 actions 槽注入 headerActions。
 * scrollBody 经 defineExpose 暴露给父级，供自动吸底跟随使用。
 * 回合导航轨（对齐上游 TurnNavigator 挂载点）：scrollBody 内首个子元素
 * （data-conversation-scroll 的 sticky 零高带）；带高两变量
 * （--dsh-composer-height / --dsh-conversation-viewport-height）按上游
 * ConversationContent 的 ResizeObserver 语义发布在滚动体上。
 */
const props = defineProps<{
  title?: string
  railItems?: TurnRailItem[]
  /** 未跟随尾部时显示「回到底部」浮动按钮（上游 toBottomSlot 的开关）。 */
  toBottomVisible?: boolean
}>()

const emit = defineEmits<{ toBottom: [] }>()

const scrollBody = ref<HTMLElement | null>(null)
const composerSeat = ref<HTMLElement | null>(null)
const rootEl = ref<HTMLElement | null>(null)
defineExpose({ scrollBody })

/* ---- 宽度轴与带高变量 ----
   上游 ConversationContent seatObserver 发布 --dsh-composer-height /
   --dsh-conversation-viewport-height；ConversationWidthControls.publishWidths
   发布 --dsh-conversation-column-width（内容宽度轴
   --dsh-chat-content-width 的 clamp 输入，未发布时 clamp 输入为 0px、
   内容恒压 680px 下限）。本应用无拖宽手柄（P3-5），只发布测量值。 */
let seatObserver: ResizeObserver | null = null

function publishMeasures(): void {
  const scroller = scrollBody.value
  const seat = composerSeat.value
  const root = rootEl.value
  if (scroller === null || seat === null || root === null) return
  scroller.style.setProperty('--dsh-composer-height', `${seat.offsetHeight}px`)
  scroller.style.setProperty('--dsh-conversation-viewport-height', `${scroller.clientHeight}px`)
  root.style.setProperty('--dsh-conversation-column-width', `${scroller.offsetWidth}px`)
}

onMounted(() => {
  const scroller = scrollBody.value
  const seat = composerSeat.value
  /* 首帧同步发布（ResizeObserver 的初始回调在部分内核不投递），观察器只管后续尺寸变化。 */
  publishMeasures()
  if (scroller === null || seat === null || typeof ResizeObserver === 'undefined') return
  seatObserver = new ResizeObserver(publishMeasures)
  seatObserver.observe(seat)
  seatObserver.observe(scroller)
  if (rootEl.value !== null) seatObserver.observe(rootEl.value)
  window.addEventListener('resize', publishMeasures)
})
onBeforeUnmount(() => {
  seatObserver?.disconnect()
  seatObserver = null
  window.removeEventListener('resize', publishMeasures)
})

/* ---- 回合导航：scrollspy（激活回合）+ 跳转（对齐 scrollToTurn 的 24px 落点） ----
   激活回合 = 视口上缘 min(96px, 视口高 20%) 内最近的回合锚点（读者位置，
   对齐上游 use-chat-viewport 的 ACTIVE_ROW_INSET）；跳转 = 锚点顶部落在滚动体
   顶部下方 24px（上游 use-chat-viewport align(row, 24, turn)）。 */
const activeTurnId = ref<string | null>(null)

function anchorElements(): HTMLElement[] {
  const scroller = scrollBody.value
  if (scroller === null) return []
  return [...scroller.querySelectorAll<HTMLElement>('[data-turn-anchor]')]
}

let spyFrame: number | null = null

function sampleActiveTurn(): void {
  spyFrame = null
  const scroller = scrollBody.value
  if (scroller === null) return
  const probe = Math.min(96, scroller.clientHeight * 0.2)
  const scrollerTop = scroller.getBoundingClientRect().top
  let current: string | null = null
  for (const anchor of anchorElements()) {
    if (anchor.getBoundingClientRect().top - scrollerTop <= probe) current = anchor.dataset.turnAnchor ?? null
    else break
  }
  activeTurnId.value = current
}

function onScrollSpy(): void {
  if (spyFrame !== null) return
  spyFrame = window.requestAnimationFrame(sampleActiveTurn)
}

function navigateToTurn(item: TurnRailItem): void {
  const scroller = scrollBody.value
  if (scroller === null) return
  const anchor = anchorElements().find((element) => element.dataset.turnAnchor === item.id)
  if (anchor === undefined) return
  /* 相对滚动体的几何位置用 rect 差值计算，不依赖 offsetParent 定位链。 */
  const delta = anchor.getBoundingClientRect().top - scroller.getBoundingClientRect().top
  const target = Math.max(0, scroller.scrollTop + delta - 24)
  smoothScrollTo(scroller, target)
}

onMounted(() => {
  scrollBody.value?.addEventListener('scroll', onScrollSpy, { passive: true })
  sampleActiveTurn()
})
onBeforeUnmount(() => {
  scrollBody.value?.removeEventListener('scroll', onScrollSpy)
  if (spyFrame !== null) window.cancelAnimationFrame(spyFrame)
})
/* 条目变化（切换会话/新消息）后补采样一次。 */
watch(
  () => props.railItems?.length ?? 0,
  () => {
    if (spyFrame !== null) window.cancelAnimationFrame(spyFrame)
    spyFrame = window.requestAnimationFrame(sampleActiveTurn)
  },
)
</script>

<template>
  <div ref="rootEl" :class="css.root" data-phase="active">
    <header :class="css.header">
      <div :class="css.titleRow">
        <div :class="css.titleCluster">
          <div :class="[css.crumb, css.crumbCurrent]">{{ title || 'Pi Chat' }}</div>
        </div>
        <div :class="css.headerActions">
          <slot name="actions" />
        </div>
      </div>
    </header>
    <div :class="css.body">
      <div ref="scrollBody" :class="css.scrollBody" data-zone="timeline" data-conversation-scroll>
        <!-- 回合导航轨：sticky 零高带（vendored .slot 语义），先于时间线内容。 -->
        <TurnNavigator
          :items="railItems ?? []"
          :active-id="activeTurnId"
          @navigate="navigateToTurn"
        />
        <!-- data-chat-following-tail：跟随中禁用 UA 滚动锚定（上游语义，
             vendored 规则以 :has(.root[data-chat-following-tail]) 命中 scroller）。 -->
        <main :class="css.viewArea" :data-chat-following-tail="toBottomVisible ? undefined : ''">
          <slot />
        </main>
        <!-- 回到底部浮动按钮（DOM 蓝图：ChatView.tsx toBottomSlot；scroller 内
             sticky 悬浮于 composer 座位上方，vendored .toBottomSlot/.toBottom 生效）。 -->
        <div v-if="toBottomVisible" :class="css.toBottomSlot" data-testid="to-bottom-slot">
          <button
            type="button"
            :class="css.toBottom"
            aria-label="回到底部"
            title="回到底部"
            data-testid="to-bottom"
            @click="emit('toBottom')"
          >
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden>
              <path
                d="M3.2 6.1a.7.7 0 0 1 .99-.03L8 9.6l3.81-3.53a.7.7 0 1 1 .95 1.03l-4.28 3.97a.7.7 0 0 1-.95 0L3.23 7.1a.7.7 0 0 1-.03-.99Z"
                fill="currentColor"
              />
            </svg>
          </button>
        </div>
      </div>
      <div ref="composerSeat" :class="css.composerSeat" data-zone="composer">
        <div :class="css.composerStack">
          <slot name="composer" />
        </div>
      </div>
    </div>
  </div>
</template>

<style>
/* 组件自有（非 vendor）：跟随中禁用 UA 滚动锚定——上游 ChatView.module.css 的
   [data-chat-following-tail] 语义在 scrollBody 自身生效（本结构无 .root 中转）。 */
[data-conversation-scroll]:has([data-chat-following-tail]) {
  overflow-anchor: none;
}
</style>
