<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import css from '../vendor/dsh/ui-conversation/src/client/skeleton/ConversationRoot.module.css'
import TurnNavigator from '../timeline/TurnNavigator.vue'
import type { TurnRailItem } from '../timeline/rail'

/*
 * DOM 蓝图：ui-conversation skeleton/ConversationRoot.tsx 的 active 相态骨架：
 * .header（titleRow：titleCluster + headerActions）→ .body → .scrollBody（时间线
 * 滚动区，default slot）→ .composerSeat（composer 槽）。data-phase="active" 激活
 * 上游的 sticky composer 座位与渐变遮罩；宽度轴变量（--dsh-chat-content-width 等）
 * 随 .body 类生效。模式徽标/场景选择由父级通过 actions 槽注入 headerActions；
 * badge 文案由模式决定（回放/实时），置空则不渲染。
 * scrollBody 经 defineExpose 暴露给父级，供自动吸底跟随使用。
 * 回合导航轨（对齐上游 TurnNavigator 挂载点）：scrollBody 内首个子元素
 * （data-conversation-scroll 的 sticky 零高带）；带高两变量
 * （--dsh-composer-height / --dsh-conversation-viewport-height）按上游
 * ConversationContent 的 ResizeObserver 语义发布在滚动体上。
 */
const props = defineProps<{
  title?: string
  badge?: string | null
  railItems?: TurnRailItem[]
}>()

const scrollBody = ref<HTMLElement | null>(null)
const composerSeat = ref<HTMLElement | null>(null)
defineExpose({ scrollBody })

/* ---- 带高变量（上游 ConversationContent seatObserver 平移） ---- */
let seatObserver: ResizeObserver | null = null
onMounted(() => {
  const scroller = scrollBody.value
  const seat = composerSeat.value
  if (scroller === null || seat === null || typeof ResizeObserver === 'undefined') return
  seatObserver = new ResizeObserver(() => {
    scroller.style.setProperty('--dsh-composer-height', `${seat.offsetHeight}px`)
    scroller.style.setProperty('--dsh-conversation-viewport-height', `${scroller.clientHeight}px`)
  })
  seatObserver.observe(seat)
  seatObserver.observe(scroller)
})
onBeforeUnmount(() => {
  seatObserver?.disconnect()
  seatObserver = null
})

/* ---- 回合导航：scrollspy（激活回合）+ 跳转（对齐 scrollToTurn 的 24px 落点） ----
   激活回合 = 视口上缘 120px 内最近的回合锚点（读者位置）；跳转 = 锚点顶部
   落在滚动体顶部下方 24px（上游 use-chat-viewport align(row, 24, turn)）。 */
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
  const scrollerTop = scroller.getBoundingClientRect().top
  let current: string | null = null
  for (const anchor of anchorElements()) {
    if (anchor.getBoundingClientRect().top - scrollerTop <= 120) current = anchor.dataset.turnAnchor ?? null
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
  scroller.scrollTo({ top: target, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
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
  <div :class="css.root" data-phase="active">
    <header :class="css.header">
      <div :class="css.titleRow">
        <div :class="css.titleCluster">
          <div :class="[css.crumb, css.crumbCurrent]">{{ title || 'Pi Chat' }}</div>
          <span v-if="badge" class="pi-replay-badge" data-testid="mode-badge">{{ badge }}</span>
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
        <main :class="css.viewArea">
          <slot />
        </main>
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
/* 组件自有（非 vendor）：回放徽标 chip，令牌着色（caption 底、caption 字）。 */
.pi-replay-badge {
  display: inline-flex;
  align-items: center;
  flex: none;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--dsw-radius-sm, 8px);
  background: var(--dsw-alias-interactive-bg-hover, rgba(0, 0, 0, 0.04));
  color: var(--dsw-alias-label-secondary, #545557);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}
</style>
