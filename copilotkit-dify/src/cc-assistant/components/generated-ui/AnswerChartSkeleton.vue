<template>
  <section class="answer-chart-skeleton" data-testid="answer-chart-pending" aria-label="图表生成中" aria-busy="true">
    <header>
      <span class="answer-chart-skeleton__title" />
      <span class="answer-chart-skeleton__description" />
    </header>
    <div class="answer-chart-skeleton__plot" aria-hidden="true">
      <span v-for="height in bars" :key="height" :style="{ height: `${height}%` }" />
    </div>
    <p>正在整理数据并生成图表…</p>
  </section>
</template>

<script setup lang="ts">
const bars = [34, 58, 46, 76, 64, 88]
</script>

<style scoped>
.answer-chart-skeleton {
  width: min(100%, 960px);
  min-height: 360px;
  margin: 22px 0 26px;
  color: var(--cc-agent-muted, #6b7280);
  font-family: var(--cc-agent-font-family, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif);
}

.answer-chart-skeleton header {
  display: grid;
  gap: 9px;
  margin-bottom: 24px;
}

.answer-chart-skeleton__title,
.answer-chart-skeleton__description {
  display: block;
  overflow: hidden;
  border-radius: 999px;
  background: var(--cc-agent-surface-alt, #f1f4f8);
}

.answer-chart-skeleton__title {
  width: min(42%, 280px);
  height: 20px;
}

.answer-chart-skeleton__description {
  width: min(68%, 520px);
  height: 13px;
}

.answer-chart-skeleton__plot {
  height: 250px;
  display: flex;
  align-items: flex-end;
  gap: clamp(12px, 3vw, 34px);
  padding: 22px 6% 0;
  border-bottom: 1px dashed var(--cc-agent-muted-line, #e5e7eb);
  background: repeating-linear-gradient(to bottom, transparent 0, transparent 61px, var(--cc-agent-muted-line, #e5e7eb) 62px);
}

.answer-chart-skeleton__plot span {
  flex: 1;
  max-width: 86px;
  border-radius: 7px 7px 0 0;
  background: color-mix(in srgb, var(--cc-agent-primary, #4c91f7) 18%, transparent);
  animation: answer-chart-breathe 1.4s ease-in-out infinite alternate;
}

.answer-chart-skeleton p {
  margin: 12px 0 0;
  font-size: 12px;
}

@keyframes answer-chart-breathe {
  from { opacity: 0.42; }
  to { opacity: 0.82; }
}

@media (prefers-reduced-motion: reduce) {
  .answer-chart-skeleton__plot span { animation: none; }
}
</style>