<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { VisualizeBlock } from '../projection/visualize'
import { hasSandboxPolicy, loadKit, readHostTheme, type KitAssets } from '../visualize/kit'

const props = defineProps<{ block: VisualizeBlock; complete: boolean; status?: string; contentId: string }>()
const frame = ref<HTMLIFrameElement | null>(null)
const frameUrl = ref('')
const error = ref('')
const ready = ref(false)
const expanded = ref(false)
const closed = ref(false)
const height = ref(360)
const manuallyRequested = ref(false)
const canViewManually = computed(() => props.complete && !props.block.error &&
  (!props.status || props.status === 'unknown'))
const canRun = computed(() => props.complete && !props.block.error &&
  (props.status === 'completed' || (manuallyRequested.value && canViewManually.value)))
let ticket = 0
let abort: AbortController | null = null
let timer: ReturnType<typeof setTimeout> | undefined
let channel = ''
let initialized = false
let messages = 0
let windowStart = 0
let assets: KitAssets | null = null
let themeObserver: MutationObserver | null = null

const message = computed(() => {
  if (!props.complete) return props.status && props.status !== 'completed'
    ? '此轮未自动运行作品；回答未完整收齐。'
    : '作品生成中，完整回答收齐后再展示。'
  if (props.block.error) return props.block.error
  if (!canRun.value) return canViewManually.value
    ? '运行状态未确认；可点击查看已保存作品。'
    : '此轮未自动运行作品；需要已完成的可信运行。'
  return error.value || (closed.value ? '作品已关闭。' : '正在准备交互作品…')
})

function dispose() {
  ticket += 1
  if (frame.value?.contentWindow && channel) frame.value.contentWindow.postMessage({ type: 'pi-visualize:dispose', id: channel }, '*')
  abort?.abort()
  abort = null
  clearTimeout(timer)
  frameUrl.value = ''
  ready.value = false
  initialized = false
  channel = ''
  assets = null
  themeObserver?.disconnect()
  themeObserver = null
  window.removeEventListener('message', onMessage)
}

async function start() {
  dispose()
  error.value = ''
  closed.value = false
  expanded.value = false
  height.value = 360
  if (!canRun.value) return
  // This is a compatibility gate, not a polyfill for Connection-Allowlist.
  const chromium = navigator.userAgent.match(/(?:Chrome|Chromium)\/(\d+)/)
  if (!chromium || Number(chromium[1]) < 154) {
    error.value = '此浏览器尚未通过作品隔离验证。请使用受支持的 Chromium 154 或更新版本。'
    return
  }
  const current = ticket
  abort = new AbortController()
  timer = setTimeout(() => fail('作品初始化超时，已停止展示。'), 8000)
  try {
    const url = new URL(`${import.meta.env.BASE_URL}visualize/sandbox.html`, window.location.href)
    const response = await fetch(url, { signal: abort.signal, credentials: 'omit', cache: 'no-store', redirect: 'error' })
    if (current !== ticket) return
    if (!response.ok || !hasSandboxPolicy(response.headers)) {
      fail('部署尚未启用作品网络隔离；请联系维护者配置后再查看。')
      return
    }
    let prepared: KitAssets
    try { prepared = await loadKit(props.block.libraries) }
    catch (cause) {
      if (current !== ticket) return
      fail(cause instanceof Error ? cause.message : '本地可视化资源无法加载。')
      return
    }
    if (current !== ticket) return
    assets = prepared
    channel = [...crypto.getRandomValues(new Uint32Array(4))].map((part) => part.toString(16).padStart(8, '0')).join('')
    initialized = false
    messages = 0
    windowStart = Date.now()
    window.addEventListener('message', onMessage)
    themeObserver = new MutationObserver(() => {
      if (initialized && frame.value?.contentWindow) frame.value.contentWindow.postMessage({ type: 'pi-visualize:theme', id: channel, theme: readHostTheme() }, '*')
    })
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] })
    frameUrl.value = url.href
  } catch (cause) {
    if (current !== ticket || abort?.signal.aborted) return
    fail('无法加载作品隔离环境。请稍后重新打开会话。')
  }
}

function fail(text: string) {
  dispose()
  error.value = text
}

function onMessage(event: MessageEvent) {
  if (!frame.value || !frameUrl.value || event.source !== frame.value.contentWindow) return
  const data = event.data
  if (!data || typeof data !== 'object' || Array.isArray(data)) return
  if (Date.now() - windowStart > 1000) { messages = 0; windowStart = Date.now() }
  if (++messages > 40) return
  if (data.type === 'pi-visualize:shell-ready' && !initialized) {
    initialized = true
    frame.value.contentWindow?.postMessage({ type: 'pi-visualize:init', id: channel, source: props.block.source, theme: readHostTheme(), assets }, '*')
    return
  }
  if (data.id !== channel) return
  if (data.type === 'pi-visualize:ready') {
    ready.value = true
    clearTimeout(timer)
  } else if (data.type === 'pi-visualize:resize' && Number.isFinite(data.height)) {
    height.value = Math.min(1200, Math.max(200, Math.ceil(data.height)))
  } else if (data.type === 'pi-visualize:error' && typeof data.message === 'string' && data.message.length <= 500) {
    fail('作品运行出错，已停止展示。文字说明仍可阅读。')
  }
}

function close() {
  dispose()
  closed.value = true
}

function viewSavedArtwork() {
  if (!canViewManually.value) return
  manuallyRequested.value = true
  void start()
}

watch([() => props.contentId, () => props.block.source, () => props.complete, () => props.status], () => {
  manuallyRequested.value = false
  void start()
}, { immediate: true })
onBeforeUnmount(dispose)
</script>

<template>
  <section class="pi-visualize" :class="{ 'is-expanded': expanded }" :aria-label="block.title" :data-content-id="`${contentId}:${block.digest}`">
    <div class="pi-visualize-header">
      <strong>{{ block.title }}</strong>
      <div v-if="frameUrl || (canViewManually && !manuallyRequested)" class="pi-visualize-actions">
        <button v-if="canViewManually && !manuallyRequested" type="button" @click="viewSavedArtwork">查看作品</button>
        <template v-if="frameUrl">
          <button type="button" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起' : '展开' }}</button>
          <button type="button" @click="close">关闭作品</button>
        </template>
      </div>
    </div>
    <p class="pi-visualize-description">{{ block.description }}</p>
    <p v-if="canViewManually && manuallyRequested" class="pi-visualize-status">运行状态未确认；仅查看已保存的本地作品。</p>
    <p v-if="!ready" class="pi-visualize-status" role="status">{{ message }}</p>
    <iframe v-if="frameUrl" ref="frame" :src="frameUrl" :title="block.title"
      sandbox="allow-scripts" credentialless referrerpolicy="no-referrer"
      :style="{ height: `${expanded ? Math.max(height, 680) : Math.min(height, 560)}px` }" />
  </section>
</template>

<style scoped>
.pi-visualize { margin: 16px 0; padding: 16px; border: 1px solid var(--border); border-radius: 12px; min-width: 0; }
.pi-visualize-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.pi-visualize-header strong { overflow-wrap: anywhere; font-size: 14px; line-height: 1.5; }
.pi-visualize-actions { display: flex; gap: 8px; }
.pi-visualize-actions button { min-height: 36px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text); font-size: 13px; }
.pi-visualize-actions button:hover { background: var(--panel-strong); }
.pi-visualize-actions button:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.pi-visualize-description, .pi-visualize-status { margin: 8px 0 12px; color: var(--muted-strong); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.pi-visualize iframe { display: block; width: 100%; border: 0; background: var(--bg); }
@media (max-width: 480px) { .pi-visualize { padding: 12px; } }
</style>
