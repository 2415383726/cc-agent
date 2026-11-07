<script setup lang="ts">
import heroCss from '../vendor/dsh/ui-conversation/src/client/skeleton/HeroShell.module.css'

/*
 * 新会话空态 hero（Vue 重写）。DOM 蓝图：ui-conversation HeroShell.tsx（MIT）
 * 的居中栈（headline 26px/32px wt500，垂直水平居中于滚动体，composer 卡宽度
 * 上限对齐 --dsh-composer-card-max-width）。偏离：上游 headline 前有品牌
 * fish（悬停游动动画）且带「预览版」徽标——票面裁剪品牌区，本应用只渲染
 * 问候标题；正文（composer）仍由 ConversationColumn 的 composerSeat 承载，
 * hero 只占滚动体的空态一屏。
 */
withDefaults(defineProps<{ headline?: string }>(), { headline: '你好，有什么可以帮忙的？' })
</script>

<template>
  <div :class="[heroCss.root, 'pi-empty-hero']" data-testid="empty-hero">
    <div :class="heroCss.stack">
      <div :class="heroCss.headline">
        <span :class="heroCss.titleGroup">
          <span>{{ headline }}</span>
        </span>
      </div>
      <div :class="heroCss.body" />
    </div>
  </div>
</template>

<style>
/* 组件自有（非 vendor）：上游 hero 挂在满高 body 内（height:100% 可解析）；
   本应用 hero 在滚动内容流里，用发布的视口高度变量撑出一屏。 */
.pi-empty-hero {
  height: auto;
  min-height: var(--dsh-conversation-viewport-height, 60dvh);
}
</style>
