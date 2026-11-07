<script setup lang="ts">
import css from '../vendor/dsh/ui-conversation/src/client/skeleton/ConversationRoot.module.css'

/*
 * DOM 蓝图：ui-conversation skeleton/ConversationRoot.tsx 的 active 相态骨架：
 * .header（titleRow：titleCluster + headerActions）→ .body → .scrollBody（时间线
 * 滚动区，default slot）→ .composerSeat（composer 槽）。data-phase="active" 激活
 * 上游的 sticky composer 座位与渐变遮罩；宽度轴变量（--dsh-chat-content-width 等）
 * 随 .body 类生效。模式徽标/场景选择由父级通过 actions 槽注入 headerActions；
 * badge 文案由模式决定（回放/实时），置空则不渲染。
 */
withDefaults(defineProps<{ title?: string; badge?: string | null }>(), { badge: '回放模式' })
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
      <div :class="css.scrollBody" data-zone="timeline">
        <main :class="css.viewArea">
          <slot />
        </main>
      </div>
      <div :class="css.composerSeat" data-zone="composer">
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
