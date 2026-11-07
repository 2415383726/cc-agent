<script setup lang="ts">
import { computed } from 'vue'
import type { WorkbenchController } from '../dify/controller'
import TranscriptView from '../timeline/TranscriptView.vue'

/*
 * 实时会话状态视图（票 07）：只承担真实状态接线——错误、停止说明、警告、
 * 「更早」分页与空态。时间线条目由共享 TranscriptView 渲染（ADR-0010：
 * 回放与实时用同一契约与组件，本组件不再有第二套时间线渲染路径）；问卷/
 * 审批回调直接转接 DifyController 的 inputs.interaction 通道。
 */
const props = defineProps<{ controller: WorkbenchController }>()

const view = computed(() => props.controller.view)
const ui = computed(() => props.controller.ui)
</script>

<template>
  <div class="pi-live">
    <p v-if="ui.error" role="alert" class="pi-live-error">{{ ui.error }}</p>
    <p v-if="ui.stoppedNote" role="status" class="pi-live-error" data-testid="stopped-note">{{ ui.stoppedNote }}</p>
    <ul v-if="view.warnings.length" aria-label="警告" class="pi-live-warnings">
      <li v-for="warning in view.warnings" :key="warning">{{ warning }}</li>
    </ul>

    <button
      v-if="ui.hasMore"
      type="button"
      class="pi-live-earlier"
      data-testid="load-earlier"
      :disabled="ui.loadingHistory"
      @click="controller.loadMore()"
    >
      {{ ui.loadingHistory ? '加载中…' : '更早' }}
    </button>

    <p v-if="!view.entries.length">暂无消息；在下方输入开启对话，或从侧栏选择历史会话。</p>
    <TranscriptView
      v-else
      :entries="view.entries"
      :running="view.running"
      :outputs="view.outputs"
      :on-question-submit="(entry, answers) => controller.submitAnswers(entry, answers)"
      :on-question-cancel="(entry) => controller.cancelQuestion(entry)"
      :on-approval-submit="(entry, decision, scope) => controller.submitApproval(entry, decision, scope)"
    />
  </div>
</template>

<style>
/* 组件自有（非 vendor）：实时状态层的最小排版（错误横幅/警告/分页按钮）。 */
.pi-live {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pi-live-error {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--dsw-radius-md);
  background: var(--dsw-alias-interactive-bg-hover);
  color: var(--dsw-alias-state-error-primary);
  font-size: 13px;
  line-height: 20px;
}

.pi-live-warnings {
  margin: 0;
  padding-left: 18px;
  color: var(--dsw-alias-label-secondary);
  font-size: 13px;
  line-height: 20px;
}

.pi-live-earlier {
  align-self: flex-start;
  height: 28px;
  padding: 0 14px;
  border: 0.5px solid var(--dsw-alias-border-l3);
  border-radius: var(--dsw-radius-sm);
  background: transparent;
  color: var(--dsw-alias-label-secondary);
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
}

.pi-live-earlier:disabled {
  cursor: default;
  color: var(--dsw-alias-label-caption);
}

@media (hover: hover) {
  .pi-live-earlier:hover:not(:disabled) {
    background: var(--dsw-alias-interactive-bg-hover);
    color: var(--dsw-alias-label-primary);
  }
}
</style>
