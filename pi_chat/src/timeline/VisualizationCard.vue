<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { buildFrameDoc, HEIGHT_MESSAGE_TYPE } from '../vendor/dshv/shell'
import type { ToolEntry } from '../projection/transcript'

/*
 * visualize 交互卡片（沙箱化 iframe）。DOM 蓝图：dsh-visualize VisualizeCard
 * （BSD-3-Clause，见 vendor/dshv/NOTICE.md）——header（title + mode 徽标）+
 * iframe[sandbox=allow-scripts]（不透明源，无法触达宿主页面），srcdoc 由
 * vendor shell 组装：CSP default-src 'none'（纯内网零网络）、主题桥
 * （宿主 --dsw-* 计算值 → 卡内 --dsh-viz-* 变量）、高度桥（frame 内
 * ResizeObserver → postMessage scrollHeight，按 mode 封顶，超出卡内滚动）。
 * 片段缺失（历史未持久化等）时降级为占位说明，不渲染空框。
 */
const props = defineProps<{ entry: ToolEntry }>()

const visual = computed(() => {
  const payload = props.entry.visual
  return payload && payload.fragment.trim() !== '' ? payload : null
})

const MIN_HEIGHT = 48
/** 高度上限；超出上限卡内滚动（对齐上游 HEIGHT_CAP）。 */
const HEIGHT_CAP: Record<string, number> = { inline: 800, wide: 1200 }

/* 初始高度与上游一致（48px 最小值）：帧内 reporter 在脚本末尾同步上报一次，
   首帧即抬升，避免占位闪烁。 */
const height = ref(MIN_HEIGHT)
const frame = ref<HTMLElement | null>(null)

const reportToken = computed(() => props.entry.callId || props.entry.id)

/* 主题桥：从宿主根元素读 --dsw-* 计算值，注入卡内 --dsh-viz-* 变量。
   读不到（测试环境等）时字段缺省，卡内 fallback 生效。 */
function bridgeTheme(): Record<string, string> {
  if (typeof window === 'undefined' || typeof getComputedStyle !== 'function') return {}
  const styles = getComputedStyle(document.documentElement)
  const read = (token: string, fallback: string): string => {
    const value = styles.getPropertyValue(token).trim()
    return value !== '' ? value : fallback
  }
  return {
    foreground: read('--dsw-alias-label-primary', ''),
    'muted-foreground': read('--dsw-alias-label-secondary', ''),
    border: read('--dsw-alias-border-l3', ''),
    primary: read('--dsw-alias-state-business-primary', ''),
    'primary-foreground': read('--dsw-alias-label-primary-inverted', '#ffffff'),
    card: read('--dsw-alias-interactive-bg-hover', ''),
    background: 'transparent',
  }
}

const srcdoc = computed(() => {
  const payload = visual.value
  if (!payload) return ''
  return buildFrameDoc({
    fragment: payload.fragment,
    title: payload.title,
    themeVars: bridgeTheme(),
    colorScheme: 'light',
    reportToken: reportToken.value,
  })
})

function onMessage(event: MessageEvent): void {
  const report = event.data as { type?: unknown; token?: unknown; height?: unknown } | null
  if (!report || report.type !== HEIGHT_MESSAGE_TYPE) return
  if (report.token !== reportToken.value) return
  if (typeof report.height !== 'number' || !Number.isFinite(report.height)) return
  const mode = visual.value?.mode ?? 'inline'
  height.value = Math.max(MIN_HEIGHT, Math.min(Math.ceil(report.height), HEIGHT_CAP[mode] ?? 800))
}

onMounted(() => {
  window.addEventListener('message', onMessage)
})
onBeforeUnmount(() => {
  window.removeEventListener('message', onMessage)
})
</script>

<template>
  <figure class="pi-viz" data-testid="visualize-card" :data-viz-mode="visual?.mode ?? 'inline'">
    <figcaption class="pi-viz-header">
      <span class="pi-viz-title" data-testid="visualize-title">{{ visual?.title ?? 'Visualization' }}</span>
      <span v-if="visual" class="pi-viz-mode">{{ visual.mode }}</span>
      <span v-if="visual?.size_bytes" class="pi-viz-size">{{ Math.ceil(visual.size_bytes / 1024) }} KB</span>
      <span v-else class="pi-viz-missing" data-testid="visualize-missing">
        该可视化未随当前会话记录保存，仅显示结果摘要。
      </span>
    </figcaption>
    <iframe
      v-if="visual"
      class="pi-viz-frame"
      sandbox="allow-scripts"
      :srcdoc="srcdoc"
      :style="{ height: `${height}px` }"
      :title="visual.title"
      data-testid="visualize-frame"
      ref="frame"
    ></iframe>
  </figure>
</template>

<style>
/* 组件自有（非 vendor）：卡片外框。header 沿用上游卡头语言（12px 弱化行）；
   inline 模式随内容列宽，wide 模式外扩到 composer 卡宽度轴（内容宽 +32px）。 */
.pi-viz {
  margin: 0;
  min-width: 0;
  max-width: 100%;
}

.pi-viz[data-viz-mode='wide'] {
  width: calc(100% + 32px);
  margin-inline: -16px;
}

.pi-viz-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 2px 0 6px;
  overflow: hidden;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.pi-viz-title {
  flex-shrink: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  color: var(--dsw-alias-label-primary, #0b0b0c);
}

.pi-viz-mode {
  flex: none;
  padding: 0 7px;
  border: 0.5px solid var(--dsw-alias-border-l3, rgba(0, 0, 0, 0.12));
  border-radius: 4px;
  color: var(--dsw-alias-label-tertiary, #909094);
  font-family: var(--ds-font-family-code, ui-monospace, monospace);
}

.pi-viz-size,
.pi-viz-missing {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--dsw-alias-label-tertiary, #909094);
}

.pi-viz-frame {
  display: block;
  width: 100%;
  border: 0;
  border-radius: var(--dsw-radius-md, 12px);
  background: transparent;
}
</style>
