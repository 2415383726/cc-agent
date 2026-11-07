<script setup lang="ts">
import css from '../vendor/dsh/ui-sidebar/src/client/SidebarRoot.module.css'

/*
 * DOM 蓝图：ui-sidebar SidebarRoot.tsx 的展开态骨架（logoRow → newSession →
 * scrollRegion/scrollArea → footArea）。本票只是占位轨道：会话列表、插件等
 * 面板项与真实「新会话」行为属 ticket 07；此处的按钮是视觉占位，不接逻辑。
 */
</script>

<template>
  <div :class="css.root">
    <div :class="css.logoRow">
      <span :class="css.brand">
        <span :class="css.brandIdentity">
          <span :class="css.brandName">Pi Chat</span>
        </span>
      </span>
    </div>
    <button
      type="button"
      :class="css.newSession"
      aria-label="新会话（后续票据启用）"
    >
      <span :class="css.newSessionContent">
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
          <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.3" />
          <path d="M8 5v6M5 8h6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
        </svg>
        <span :class="css.newSessionLabel">新会话</span>
      </span>
    </button>
    <div :class="css.scrollRegion">
      <div :class="css.scrollArea" aria-label="会话列表（后续票据提供）" />
    </div>
    <div :class="css.footArea">
      <span class="pi-rail-caption">回放基座</span>
    </div>
  </div>
</template>

<style>
/* 组件自有（非 vendor）：占位轨道的底部说明行，用令牌着色。 */
.pi-rail-caption {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 5px 12px;
  color: var(--dsw-alias-label-caption);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}
</style>
