<script setup lang="ts">
import { computed, ref } from 'vue'
import type { FileRef } from '../projection/transcript'

const props = defineProps<{
  running: boolean
  stopping: boolean
  disabled?: boolean
  upload: (file: File) => Promise<FileRef | null>
}>()

const emit = defineEmits<{
  send: [text: string, files: FileRef[]]
  stop: []
}>()

const draft = ref('')
const files = ref<FileRef[]>([])
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const canSend = computed(
  () =>
    !props.running &&
    !props.stopping &&
    !props.disabled &&
    !uploading.value &&
    Boolean(draft.value.trim() || files.value.length),
)

async function onPick(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || [])
  input.value = ''
  if (!selected.length) return
  uploading.value = true
  try {
    for (const file of selected) {
      const uploaded = await props.upload(file)
      if (uploaded?.id) files.value.push(uploaded)
    }
  } finally {
    uploading.value = false
  }
}

function submit() {
  if (!canSend.value) return
  emit('send', draft.value.trim(), files.value.slice())
  draft.value = ''
  files.value = []
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}

function removeFile(index: number) {
  files.value.splice(index, 1)
}
</script>

<template>
  <div class="pi-composer">
    <div v-if="files.length || uploading" class="pi-file-chips pi-composer-files">
      <span v-for="(file, index) in files" :key="file.id || index" class="pi-file-chip">
        {{ file.name || file.id }}
        <button type="button" class="pi-chip-remove" :aria-label="`Remove ${file.name || 'file'}`" @click="removeFile(index)">×</button>
      </span>
      <span v-if="uploading" class="pi-file-chip">Uploading…</span>
    </div>
    <div class="pi-composer-row">
      <button
        type="button"
        class="pi-icon-button"
        title="Attach a file"
        :disabled="running || uploading"
        @click="fileInput?.click()"
      >
        +
      </button>
      <input ref="fileInput" type="file" multiple hidden @change="onPick" />
      <textarea
        v-model="draft"
        class="pi-composer-input"
        rows="1"
        :placeholder="disabled ? 'Answer the pending question or approval above' : 'Ask the Pi agent…'"
        :disabled="disabled"
        aria-label="Message"
        @keydown="onKeydown"
      ></textarea>
      <button
        v-if="running || stopping"
        type="button"
        class="pi-button pi-button-danger pi-stop-button"
        :disabled="stopping"
        @click="emit('stop')"
      >
        {{ stopping ? 'Stopping…' : 'Stop' }}
      </button>
      <button
        v-else
        type="button"
        class="pi-button pi-button-primary pi-send-button"
        :disabled="!canSend"
        @click="submit"
      >
        Send
      </button>
    </div>
    <p class="pi-composer-hint">
      Enter to send · Shift+Enter for a new line · one active request per conversation
    </p>
  </div>
</template>
