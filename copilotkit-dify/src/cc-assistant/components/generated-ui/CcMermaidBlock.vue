<template>
  <div class="cc-mermaid-block" data-testid="mermaid-block">
    <div class="cc-mermaid-block__inner">
      <div v-if="loading" class="cc-mermaid-block__spinner">
        <div class="cc-mermaid-block__spinner-dot" />
      </div>
      <div v-else-if="renderedSvg" v-html="renderedSvg" />
      <pre v-else class="cc-mermaid-block__source">{{ code }}</pre>
      <p v-if="errorMessage" class="cc-mermaid-block__error">{{ errorMessage }}</p>
      <button
        v-if="renderedSvg"
        class="cc-mermaid-block__fullscreen-btn"
        aria-label="全屏预览"
        title="全屏预览"
        @click="openFullscreen"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 3 21 3 21 9" />
          <polyline points="9 21 3 21 3 15" />
          <line x1="21" y1="3" x2="14" y2="10" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
      </button>
    </div>

    <Teleport to="body">
      <div v-if="fullscreenOpen" class="cc-mermaid-overlay" @click.self="closeFullscreen">
        <div class="cc-mermaid-overlay__body">
          <header class="cc-mermaid-overlay__header">
            <h3>流程图预览</h3>
            <button class="cc-mermaid-overlay__close" @click="closeFullscreen" aria-label="关闭全屏">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </header>
          <div ref="modalDiagramRef" class="cc-mermaid-overlay__diagram">
            <div
              v-if="fullscreenSvg"
              class="cc-mermaid-overlay__canvas"
              v-html="fullscreenSvg"
            />
            <div v-else class="cc-mermaid-block__spinner">
              <div class="cc-mermaid-block__spinner-dot" />
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  code: string
}>()

const renderedSvg = ref('')
const errorMessage = ref('')
const loading = ref(true)
const fullscreenOpen = ref(false)
const fullscreenSvg = ref('')
const modalDiagramRef = ref<HTMLElement>()
const diagramId = `cc-mermaid-${hashCode(props.code)}`

onMounted(async () => {
  await doRender()
})

watch(
  () => props.code,
  async () => {
    await doRender()
  },
)

async function doRender() {
  const code = props.code
  if (!code.trim()) return
  loading.value = true
  errorMessage.value = ''

  const cached = svgCache.get(code)
  if (cached) {
    renderedSvg.value = cached
    loading.value = false
    return
  }

  try {
    const svg = await renderCached(code, diagramId)
    renderedSvg.value = svg
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '流程图语法无法渲染。'
  } finally {
    loading.value = false
  }
}

async function openFullscreen() {
  fullscreenOpen.value = true
  document.body.style.overflow = 'hidden'
  fullscreenSvg.value = renderedSvg.value
  await nextTick()
  const svg = modalDiagramRef.value?.querySelector('svg')
  if (svg) {
    svg.removeAttribute('width')
    svg.removeAttribute('height')
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet')
  }
}

function closeFullscreen() {
  fullscreenOpen.value = false
  document.body.style.overflow = ''
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape' && fullscreenOpen.value) closeFullscreen()
}

onMounted(() => {
  document.addEventListener('keydown', handleEscape)
})

onBeforeUnmount(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', handleEscape)
})
</script>

<script lang="ts">
// Module-level Mermaid singleton: initialized once and cached globally.

let mermaidInit = false
const svgCache = new Map<string, string>()

async function ensureMermaid(): Promise<typeof import('mermaid')> {
  const mermaid = await import('mermaid')
  if (!mermaidInit) {
    mermaid.default.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'default' })
    mermaidInit = true
  }
  return mermaid
}

async function renderCached(code: string, id: string): Promise<string> {
  const cached = svgCache.get(code)
  if (cached) return cached
  const mermaid = await ensureMermaid()
  const result = await mermaid.default.render(id, code)
  svgCache.set(code, result.svg)
  return result.svg
}

function hashCode(str: string): string {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash).toString(36)
}
</script>

<style scoped>
.cc-mermaid-block {
  width: min(100%, 960px);
  margin: 10px 0;
  border: 1px solid var(--cc-agent-line, #e2e8f0);
  border-radius: 8px;
  background: #ffffff;
  color: #172033;
  overflow: hidden;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.cc-mermaid-block__inner {
  position: relative;
  padding: 12px 14px;
  overflow-x: auto;
}

.cc-mermaid-block__spinner {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

.cc-mermaid-block__spinner-dot {
  width: 20px;
  height: 20px;
  border: 2px solid #d1d5db;
  border-top-color: transparent;
  border-radius: 50%;
  animation: cc-mermaid-spin 0.6s linear infinite;
}

.cc-mermaid-block__source {
  margin: 0;
  padding: 10px;
  border-radius: 7px;
  background: #f8fafc;
  color: #334155;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.55;
  overflow-x: auto;
  white-space: pre-wrap;
}

.cc-mermaid-block__error {
  margin: 10px 0 0;
  color: #b91c1c;
  font-size: 13px;
  line-height: 1.5;
}

.cc-mermaid-block__fullscreen-btn {
  position: absolute;
  top: 6px;
  right: 14px;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.9);
  color: #6b7280;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}

.cc-mermaid-block__inner:hover .cc-mermaid-block__fullscreen-btn {
  opacity: 1;
}
</style>

<!-- unscoped: SVG injected via innerHTML needs global styles -->
<style>
.cc-mermaid-overlay__diagram svg {
  width: 100% !important;
  height: 100% !important;
  max-width: 100% !important;
  max-height: 100% !important;
}

.cc-mermaid-overlay__canvas {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cc-mermaid-block__fullscreen-btn:hover {
  background: #e5e7eb;
  color: #111827;
}

/* Overlay */
.cc-mermaid-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
  animation: cc-mermaid-fade-in 0.15s ease-out;
}

.cc-mermaid-overlay__body {
  width: calc(100vw - 32px);
  height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.28);
  overflow: hidden;
  animation: cc-mermaid-scale-in 0.18s ease-out;
}

.cc-mermaid-overlay__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}

.cc-mermaid-overlay__header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}

.cc-mermaid-overlay__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 8px;
  background: #f3f4f6;
  color: #6b7280;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.cc-mermaid-overlay__close:hover {
  background: #e5e7eb;
  color: #111827;
}

.cc-mermaid-overlay__diagram {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 640px) {
  .cc-mermaid-overlay__body {
    width: 100vw;
    height: 100vh;
    border-radius: 0;
  }

  .cc-mermaid-overlay__diagram {
    padding: 12px;
  }
}

@keyframes cc-mermaid-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes cc-mermaid-scale-in {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}

@keyframes cc-mermaid-spin {
  to { transform: rotate(360deg); }
}
</style>
