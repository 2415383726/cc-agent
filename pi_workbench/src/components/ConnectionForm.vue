<script setup lang="ts">
import { ref } from 'vue'
import { parseInputs, type WorkbenchConfig } from '../dify/config'

const props = defineProps<{ config: WorkbenchConfig }>()
const emit = defineEmits<{
  save: [config: WorkbenchConfig]
  close: []
}>()

const baseUrl = ref(props.config.baseUrl)
const apiKey = ref(props.config.apiKey)
const user = ref(props.config.user)
const inputsText = ref(JSON.stringify(props.config.inputs || {}, null, 2))
const error = ref('')

function save() {
  error.value = ''
  if (!baseUrl.value.trim()) {
    error.value = '请填写 Dify API 地址。'
    return
  }
  if (!apiKey.value.trim()) {
    error.value = '请填写 Dify 应用 API Key。'
    return
  }
  let inputs: Record<string, unknown> = {}
  try {
    inputs = parseInputs(inputsText.value)
  } catch (exception) {
    error.value = (exception as Error).message
    return
  }
  emit('save', {
    baseUrl: baseUrl.value.trim(),
    apiKey: apiKey.value.trim(),
    user: user.value.trim() || 'pi-workbench-user',
    inputs,
  })
}
</script>

<template>
  <section class="pi-config-panel" aria-label="Dify 连接">
    <header class="pi-config-header">
      <div>
        <h2>Dify 连接</h2>
        <p class="pi-muted pi-small">
          API Key 只保存在当前标签页的 sessionStorage 中。生产环境建议使用同源代理，避免把密钥暴露在浏览器里。
        </p>
      </div>
      <button type="button" class="pi-icon-button" aria-label="关闭连接设置" @click="emit('close')">×</button>
    </header>
    <label class="pi-field">
      <span>API 地址</span>
      <input v-model="baseUrl" type="text" placeholder="/v1" autocomplete="off" />
    </label>
    <label class="pi-field">
      <span>应用 API Key</span>
      <input v-model="apiKey" type="password" placeholder="app-..." autocomplete="off" />
    </label>
    <label class="pi-field">
      <span>终端用户</span>
      <input v-model="user" type="text" autocomplete="off" />
    </label>
    <label class="pi-field">
      <span>应用输入（JSON）</span>
      <textarea v-model="inputsText" rows="4" spellcheck="false"></textarea>
    </label>
    <p v-if="error" class="pi-form-error" role="alert">{{ error }}</p>
    <div class="pi-form-actions">
      <button type="button" class="pi-button pi-button-ghost" @click="emit('close')">取消</button>
      <button type="button" class="pi-button pi-button-primary" @click="save">保存连接</button>
    </div>
    <p class="pi-muted pi-small">
      Dify 应用节点必须显式映射 query、model、tools、files、interaction、agent_state 和会话变量。工作台不会假定任意网页输入会自动到达插件。
    </p>
  </section>
</template>
