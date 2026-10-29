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
    error.value = 'Dify API base URL is required.'
    return
  }
  if (!apiKey.value.trim()) {
    error.value = 'A Dify app API key is required.'
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
  <section class="pi-config-panel" aria-label="Dify connection">
    <header class="pi-config-header">
      <div>
        <h2>Dify connection</h2>
        <p class="pi-muted pi-small">
          The key is kept in session storage for this tab only. Prefer a same-origin proxy in production.
        </p>
      </div>
      <button type="button" class="pi-icon-button" aria-label="Close connection settings" @click="emit('close')">×</button>
    </header>
    <label class="pi-field">
      <span>API base URL</span>
      <input v-model="baseUrl" type="text" placeholder="/v1" autocomplete="off" />
    </label>
    <label class="pi-field">
      <span>App API key</span>
      <input v-model="apiKey" type="password" placeholder="app-..." autocomplete="off" />
    </label>
    <label class="pi-field">
      <span>End user</span>
      <input v-model="user" type="text" autocomplete="off" />
    </label>
    <label class="pi-field">
      <span>App inputs (JSON)</span>
      <textarea v-model="inputsText" rows="4" spellcheck="false"></textarea>
    </label>
    <p v-if="error" class="pi-form-error" role="alert">{{ error }}</p>
    <div class="pi-form-actions">
      <button type="button" class="pi-button pi-button-ghost" @click="emit('close')">Cancel</button>
      <button type="button" class="pi-button pi-button-primary" @click="save">Save connection</button>
    </div>
    <p class="pi-muted pi-small">
      The Dify app node must map query, model, tools, files, interaction, agent_state and conversation
      variables. The workbench never assumes arbitrary web inputs reach the plugin.
    </p>
  </section>
</template>
