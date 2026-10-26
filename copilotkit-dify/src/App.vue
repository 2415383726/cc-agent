<template>
  <div class="drawer-app">
    <button
      type="button"
      class="config-toggle"
      :class="{ open: configOpen }"
      @click="configOpen = !configOpen"
    >
      连接配置
    </button>

    <aside v-if="configOpen" class="config-panel">
      <div class="config-panel-header">
        <div>
          <h2>连接配置</h2>
          <p>Demo 调试使用；业务系统接入时通过 props 传入这些参数。</p>
        </div>
        <button type="button" aria-label="关闭配置" @click="configOpen = false">
          <svg viewBox="0 0 20 20" fill="none" focusable="false" aria-hidden="true">
            <path d="M5.5 5.5 14.5 14.5" />
            <path d="M14.5 5.5 5.5 14.5" />
          </svg>
        </button>
      </div>

      <label>
        <span>Base URL</span>
        <input v-model.trim="config.baseUrl" placeholder="http://localhost/v1" />
      </label>

      <label>
        <span>API Key</span>
        <input v-model.trim="config.apiKey" type="password" placeholder="app-..." />
      </label>

      <label>
        <span>User</span>
        <input v-model.trim="config.user" placeholder="employee-001" />
      </label>

      <label>
        <span>Token</span>
        <input v-model.trim="config.token" type="password" placeholder="agent-token" />
      </label>

      <label>
        <span>Inputs JSON</span>
        <textarea v-model="inputsText" rows="8" placeholder='{"tenantId": "demo-tenant"}' />
      </label>

      <p v-if="configError" class="panel-error">{{ configError }}</p>
    </aside>

    <CcDifyAssistant
      ref="assistantRef"
      :dify="assistantDify"
      :catalog="catalog"
      title="干部人才系统助手"
      storage-key-prefix="copilotkit-dify-demo"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import CcDifyAssistant from './cc-assistant/components/shell/CcDifyAssistant.vue'
import {
  defaultAssistantCatalog,
  loadAssistantCatalog,
  type AssistantCatalog,
} from './cc-assistant/lib/assistantCatalog'

const STORAGE_KEY = 'copilotkit-dify-config'

function loadStoredConfig() {
  if (typeof window === 'undefined') return null
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || 'null')
  } catch (_) {
    return null
  }
}

const stored = loadStoredConfig()
const assistantRef = ref<InstanceType<typeof CcDifyAssistant> | null>(null)
const configOpen = ref(false)
const catalog = ref<AssistantCatalog>(defaultAssistantCatalog)
const config = reactive({
  baseUrl: stored?.baseUrl || '',
  apiKey: stored?.apiKey || '',
  user: stored?.user || `copilotkit-dify-${Math.random().toString(36).slice(2, 8)}`,
  token: stored?.token || '',
})
const inputsText = ref(JSON.stringify(stored?.inputs || {}, null, 2))

const parsedInputs = computed(() => {
  const text = String(inputsText.value || '').trim()
  if (!text) return {}
  return JSON.parse(text)
})

const configError = computed(() => {
  try {
    void parsedInputs.value
    return ''
  } catch (error: any) {
    return `Inputs JSON 无效: ${error?.message || error}`
  }
})

const assistantDify = computed(() => ({
  baseUrl: config.baseUrl,
  apiKey: config.apiKey,
  user: config.user,
  token: config.token,
  inputs: configError.value ? {} : parsedInputs.value,
}))

onMounted(async () => {
  catalog.value = await loadAssistantCatalog()
})

watch(
  [() => config.baseUrl, () => config.apiKey, () => config.token, () => config.user, () => inputsText.value],
  () => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        ...config,
        inputs: configError.value ? {} : parsedInputs.value,
      }),
    )
  },
  { deep: true, immediate: true },
)
</script>
