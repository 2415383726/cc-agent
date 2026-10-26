<template>
  <section class="business-surface" :data-surface="surface" data-testid="business-surface">
    <header class="business-surface__header">
      <div class="business-surface__heading">
        <h3>{{ meta.title }}</h3>
        <p v-if="meta.description">{{ meta.description }}</p>
      </div>
      <span v-if="meta.status" class="business-surface__status">{{ meta.status }}</span>
    </header>
    <div class="business-surface__content"><slot /></div>
    <footer v-if="actions?.length" class="business-surface__actions" aria-label="后续操作">
      <button v-for="action in actions" :key="action.id" type="button"
        :class="action.variant || 'secondary'" :disabled="isRunning"
        @click="emit('intent', action.prompt)">{{ action.label }}</button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import type { UiAction, UiMeta } from '../../lib/structuredContent'
withDefaults(defineProps<{ meta: UiMeta; actions?: UiAction[]; surface: string; isRunning?: boolean }>(), {
  actions: () => [], isRunning: false,
})
const emit = defineEmits<{ intent: [prompt: string] }>()
</script>

<style scoped>
.business-surface{box-sizing:border-box;width:100%;margin:12px 0 16px;border:1px solid var(--cc-agent-line);border-radius:var(--cc-agent-card-radius);background:var(--cc-agent-surface);color:var(--cc-agent-text);overflow:hidden}
.business-surface__header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:13px 16px 12px;border-bottom:1px solid var(--cc-agent-muted-line);box-shadow:inset 3px 0 0 var(--cc-agent-primary)}
.business-surface__heading{min-width:0}.business-surface__heading h3{margin:0;font-size:15px;line-height:1.45;font-weight:700}.business-surface__heading p{margin:4px 0 0;color:var(--cc-agent-muted);font-size:12.5px;line-height:1.55}
.business-surface__status{flex:0 0 auto;border:1px solid var(--cc-agent-primary-border);border-radius:999px;padding:3px 8px;background:var(--cc-agent-primary-soft);color:var(--cc-agent-primary-strong);font-size:11px;font-weight:650}.business-surface__content{min-width:0}
.business-surface__actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;padding:10px 16px 12px;border-top:1px solid var(--cc-agent-muted-line);background:var(--cc-agent-surface-alt)}
.business-surface__actions button{min-height:32px;border:1px solid var(--cc-agent-line);border-radius:7px;padding:6px 11px;background:var(--cc-agent-surface);color:var(--cc-agent-text);font:inherit;font-size:12.5px;font-weight:650;cursor:pointer}.business-surface__actions button.primary{border-color:var(--cc-agent-primary);background:var(--cc-agent-primary);color:#fff}.business-surface__actions button:hover:not(:disabled){border-color:var(--cc-agent-primary);color:var(--cc-agent-primary-strong)}.business-surface__actions button.primary:hover:not(:disabled){color:#fff;background:var(--cc-agent-primary-strong)}.business-surface__actions button:focus-visible{outline:2px solid var(--cc-agent-focus);outline-offset:2px}.business-surface__actions button:disabled{cursor:not-allowed;opacity:.5}
@media(max-width:560px){.business-surface__header{gap:10px;padding-inline:13px}.business-surface__actions{justify-content:stretch;padding-inline:13px}.business-surface__actions button{flex:1}}
</style>
