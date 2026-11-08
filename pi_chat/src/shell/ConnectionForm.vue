<script setup lang="ts">
import { ref } from 'vue'
import { defaultConfig, parseInputs } from '../dify/config'
import type { SessionCredentials } from '../dify/config'

/*
 * 最小连接表单（票 07/08）：服务地址 / API Key / 用户标识 / 应用输入 JSON。
 * 预填来自部署配置与会话凭据（defaultConfig）；提交时在本地校验并 emit connect。
 * 票 08 收尾：连接失败（conversationsError）时显示「连接失败…重试」提示；已连接时
 * 提供「收起」（emit close，父级收起表单）。
 */
const props = withDefaults(
  defineProps<{
    /** 最近一次连接失败的兜底信息（空串视为无）。 */
    connectionError?: string
    /** 已连接：显示「收起」按钮。 */
    connected?: boolean
  }>(),
  { connectionError: '', connected: false },
)
const emit = defineEmits<{ connect: [credentials: SessionCredentials]; close: [] }>()

const initial = defaultConfig()
const baseUrl = ref(initial.baseUrl || '/v1')
const apiKey = ref(initial.apiKey || '')
const user = ref(initial.user || 'pi-chat-user')
const inputsText = ref(initial.inputs && Object.keys(initial.inputs).length ? JSON.stringify(initial.inputs, null, 2) : '')
const error = ref('')

function submit(): void {
  error.value = ''
  if (!apiKey.value.trim()) {
    error.value = '请填写服务地址与 API Key。'
    return
  }
  let inputs: Record<string, unknown>
  try {
    inputs = parseInputs(inputsText.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    return
  }
  emit('connect', {
    baseUrl: baseUrl.value.trim() || '/v1',
    apiKey: apiKey.value.trim(),
    user: user.value.trim() || 'pi-chat-user',
    inputs,
  })
}
</script>

<template>
  <form class="pi-connect" data-testid="connection-form" @submit.prevent="submit">
    <h2 class="pi-connect-title">连接 Dify</h2>
    <p class="pi-connect-hint">
      填写 Dify 应用（服务型 API）凭据后开始对话；凭据只保存在本页会话中。
    </p>
    <label class="pi-connect-field">
      <span>服务地址</span>
      <input v-model="baseUrl" type="text" autocomplete="off" placeholder="/v1 或 https://…/v1" />
    </label>
    <label class="pi-connect-field">
      <span>API Key</span>
      <input v-model="apiKey" type="password" autocomplete="off" data-testid="form-api-key" placeholder="app-…" />
    </label>
    <label class="pi-connect-field">
      <span>用户标识</span>
      <input v-model="user" type="text" autocomplete="off" data-testid="form-user" />
    </label>
    <label class="pi-connect-field">
      <span>应用输入（JSON，可选）</span>
      <textarea v-model="inputsText" rows="3" data-testid="form-inputs" spellcheck="false" />
    </label>
    <p v-if="error" class="pi-connect-error" role="alert">{{ error }}</p>
    <p v-if="props.connectionError" class="pi-connect-error" role="alert" data-testid="connect-failed">
      连接失败：{{ props.connectionError }}。请检查服务地址与 API Key 后重试；也可在左侧会话列表点「重试」。
    </p>
    <div class="pi-connect-actions">
      <button
        v-if="props.connected"
        type="button"
        class="pi-connect-collapse"
        data-testid="connect-collapse"
        @click="emit('close')"
      >
        收起
      </button>
      <button type="button" class="pi-connect-submit" data-testid="connect-submit" @click="submit">
        连接
      </button>
    </div>
  </form>
</template>

<style>
/* 组件自有（非 vendor）：最小连接表单，令牌着色与圆角跟随 dsh 主题。 */
.pi-connect {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 420px;
  margin: 48px auto 0;
  padding: 24px;
  border: 0.5px solid var(--dsw-alias-border-l3);
  border-radius: var(--dsw-radius-lg);
  background: var(--dsw-alias-button-elevated-fill);
  color: var(--dsw-alias-label-primary);
}

.pi-connect-title {
  margin: 0;
  font-size: 16px;
  line-height: 24px;
  font-weight: 600;
}

.pi-connect-hint {
  margin: 0;
  color: var(--dsw-alias-label-secondary);
  font-size: 13px;
  line-height: 20px;
}

.pi-connect-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  line-height: 20px;
  color: var(--dsw-alias-label-secondary);
}

.pi-connect-field input,
.pi-connect-field textarea {
  box-sizing: border-box;
  width: 100%;
  padding: 7px 12px;
  border: 0.5px solid var(--dsw-alias-border-l4);
  border-radius: var(--dsw-radius-md);
  outline: none;
  background: transparent;
  color: var(--dsw-alias-label-primary);
  font-size: 14px;
  line-height: 22px;
  font-family: inherit;
  resize: vertical;
}

.pi-connect-field textarea {
  font-family: var(--ds-font-family-code, monospace);
  font-size: 13px;
}

.pi-connect-field input:focus-visible,
.pi-connect-field textarea:focus-visible {
  border-color: var(--dsw-alias-state-business-primary);
}

.pi-connect-error {
  margin: 0;
  color: var(--dsw-alias-state-error-primary);
  font-size: 12px;
  line-height: 18px;
}

.pi-connect-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.pi-connect-collapse {
  height: 34px;
  padding: 0 16px;
  border: 0.5px solid var(--dsw-alias-border-l3);
  border-radius: var(--dsw-radius-md);
  background: transparent;
  color: var(--dsw-alias-label-secondary);
  font-size: 14px;
  line-height: 22px;
  cursor: pointer;
}

@media (hover: hover) {
  .pi-connect-collapse:hover {
    background: var(--dsw-alias-interactive-bg-hover);
    color: var(--dsw-alias-label-primary);
  }
}

.pi-connect-submit {
  height: 34px;
  padding: 0 20px;
  border: none;
  border-radius: var(--dsw-radius-md);
  background: var(--dsw-alias-state-business-primary);
  color: var(--dsw-alias-label-primary-inverted);
  font-size: 14px;
  line-height: 22px;
  font-weight: 500;
  cursor: pointer;
}
</style>
