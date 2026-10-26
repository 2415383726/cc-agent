<template>
  <section class="answer-chart" data-testid="answer-chart" :aria-label="spec.meta.title">
    <header class="answer-chart__header">
      <div class="answer-chart__heading">
        <h3>{{ spec.meta.title }}</h3>
        <p v-if="spec.meta.description">{{ spec.meta.description }}</p>
      </div>
      <div ref="menuRef" class="answer-chart__menu">
        <button
          type="button"
          class="answer-chart__menu-trigger"
          aria-label="图表操作"
          :aria-expanded="menuOpen"
          @click="menuOpen = !menuOpen"
          @keydown.esc="closeMenu"
        >
          <span aria-hidden="true">•••</span>
        </button>
        <div v-if="menuOpen" class="answer-chart__menu-popover" role="menu">
          <button type="button" role="menuitem" @click="downloadSvg">下载 PNG</button>
          <button type="button" role="menuitem" @click="downloadCsv">下载 CSV</button>
        </div>
      </div>
    </header>

    <div class="answer-chart__plot-wrap">
      <div ref="chartRef" class="answer-chart__plot" :class="{ ready }" :style="{ height: `${chartHeight}px` }" />
    </div>
    <footer v-if="spec.meta.footer" class="answer-chart__footer">{{ spec.meta.footer }}</footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, RadarChart, ScatterChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ECharts } from 'echarts/core'
import type { ChartSpec } from '../../lib/chartSpec'
import {
  ANSWER_CHART_PALETTE,
  buildChartOption,
  chartSpecToCsv,
  suggestedChartHeight,
  type ChartTheme,
} from '../../lib/chartRendering'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  RadarChart,
  ScatterChart,
  AriaComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
])

const props = withDefaults(defineProps<{
  spec: ChartSpec
  isRunning?: boolean
}>(), {
  isRunning: false,
})

const chartRef = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const chartInstance = shallowRef<ECharts | null>(null)
const menuOpen = ref(false)
const ready = ref(false)
const chartHeight = computed(() => suggestedChartHeight(props.spec))
const specFingerprint = computed(() => JSON.stringify(props.spec))
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (!chartRef.value) return
  chartInstance.value = echarts.init(chartRef.value, undefined, { renderer: 'canvas' })
  renderChart()
  ready.value = true
  resizeObserver = new ResizeObserver(() => chartInstance.value?.resize())
  resizeObserver.observe(chartRef.value)
  document.addEventListener('pointerdown', handleOutsidePointer)
  document.addEventListener('keydown', handleEscape)
})

watch(specFingerprint, renderChart)

onBeforeUnmount(() => {
  if (resizeObserver && chartRef.value) resizeObserver.unobserve(chartRef.value)
  resizeObserver?.disconnect()
  chartInstance.value?.dispose()
  document.removeEventListener('pointerdown', handleOutsidePointer)
  document.removeEventListener('keydown', handleEscape)
})

function renderChart() {
  if (!chartInstance.value || !chartRef.value) return
  chartInstance.value.setOption(buildChartOption(props.spec, readTheme(chartRef.value)), true)
}

function readTheme(element: HTMLElement): ChartTheme {
  const styles = getComputedStyle(element)
  const value = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback
  return {
    text: value('--cc-agent-text', '#111827'),
    muted: value('--cc-agent-muted', '#6B7280'),
    grid: value('--cc-agent-muted-line', '#E5E7EB'),
    surface: value('--cc-agent-surface', '#FFFFFF'),
    palette: ANSWER_CHART_PALETTE,
    reducedMotion: props.isRunning || globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false,
  }
}

function downloadSvg() {
  const url = chartInstance.value?.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: readTheme(chartRef.value!).surface })
  if (url) downloadUrl(url, `${safeFileName(props.spec.meta.title)}.png`)
  closeMenu()
}

function downloadCsv() {
  const blob = new Blob([chartSpecToCsv(props.spec)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  downloadUrl(url, `${safeFileName(props.spec.meta.title)}.csv`)
  URL.revokeObjectURL(url)
  closeMenu()
}

function downloadUrl(url: string, name: string) {
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function safeFileName(value: string): string {
  return value.replace(/[\\/:*?"<>|]/g, '-').trim() || '图表'
}

function closeMenu() {
  menuOpen.value = false
}

function handleOutsidePointer(event: PointerEvent) {
  if (menuOpen.value && !menuRef.value?.contains(event.target as Node)) closeMenu()
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') closeMenu()
}
</script>

<style scoped>
.answer-chart {
  width: min(100%, 960px);
  margin: 22px 0 26px;
  color: var(--cc-agent-text, #111827);
  background: var(--cc-agent-surface, #ffffff);
  font-family: var(--cc-agent-font-family, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif);
}

.answer-chart__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}

.answer-chart__heading {
  min-width: 0;
}

.answer-chart__heading h3 {
  margin: 0;
  color: var(--cc-agent-text, #111827);
  font-size: clamp(17px, 2vw, 20px);
  font-weight: 750;
  line-height: 1.35;
  letter-spacing: -0.015em;
}

.answer-chart__heading p {
  max-width: 760px;
  margin: 7px 0 0;
  color: var(--cc-agent-muted, #6b7280);
  font-size: 14px;
  line-height: 1.65;
}

.answer-chart__menu {
  position: relative;
  flex: 0 0 auto;
}

.answer-chart__menu-trigger {
  display: inline-flex;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 999px;
  background: var(--cc-agent-surface-alt, #f4f5f6);
  color: var(--cc-agent-muted, #6b7280);
  cursor: pointer;
  font: inherit;
  letter-spacing: 2px;
}

.answer-chart__menu-trigger:hover,
.answer-chart__menu-trigger[aria-expanded="true"] {
  background: var(--cc-agent-primary-soft, #eef5fc);
  color: var(--cc-agent-primary, #4c91f7);
}

.answer-chart__menu-trigger:focus-visible,
.answer-chart__menu-popover button:focus-visible {
  outline: 2px solid var(--cc-agent-focus, #4c91f7);
  outline-offset: 2px;
}

.answer-chart__menu-popover {
  position: absolute;
  z-index: 20;
  top: 44px;
  right: 0;
  display: grid;
  width: 132px;
  padding: 6px;
  border: 1px solid var(--cc-agent-line, #e5e7eb);
  border-radius: 10px;
  background: var(--cc-agent-surface, #ffffff);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.14);
}

.answer-chart__menu-popover button {
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--cc-agent-text, #111827);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  padding: 8px 10px;
  text-align: left;
}

.answer-chart__menu-popover button:hover {
  background: var(--cc-agent-surface-alt, #f6f8fb);
}

.answer-chart__plot-wrap {
  width: 100%;
  min-width: 0;
}

.answer-chart__plot {
  width: 100%;
  min-height: 300px;
  opacity: 0;
  transition: opacity 0.18s ease-out;
}

.answer-chart__plot.ready {
  opacity: 1;
}

.answer-chart__footer {
  margin-top: 8px;
  color: color-mix(in srgb, var(--cc-agent-muted, #6b7280) 74%, transparent);
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 720px) {
  .answer-chart {
    margin: 18px 0 22px;
  }

  .answer-chart__header {
    gap: 12px;
    margin-bottom: 12px;
  }

  .answer-chart__heading p {
    font-size: 13px;
  }

  .answer-chart__plot {
    max-height: 420px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .answer-chart *,
  .answer-chart *::before,
  .answer-chart *::after {
    scroll-behavior: auto !important;
    transition: none !important;
  }
}
</style>