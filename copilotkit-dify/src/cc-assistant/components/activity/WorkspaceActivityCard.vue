<template>
  <section v-if="generatedFiles.length" class="generated-file-container">
    <header class="generated-file-header">
      <svg class="header-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path
          d="M4.5 3.75A2.25 2.25 0 0 1 6.75 1.5h5.19c.6 0 1.17.24 1.59.66l2.31 2.31c.42.42.66.99.66 1.59v8.19a2.25 2.25 0 0 1-2.25 2.25h-7.5A2.25 2.25 0 0 1 4.5 14.25V3.75Zm8.25-.31V5.5c0 .41.34.75.75.75h2.06L12.75 3.44ZM7.25 9a.75.75 0 0 0 0 1.5h5.5a.75.75 0 0 0 0-1.5h-5.5Zm0 3a.75.75 0 0 0 0 1.5h3.5a.75.75 0 0 0 0-1.5h-3.5Z"
        />
      </svg>
      <span>{{ title }}</span>
    </header>

    <div class="generated-files-list">
      <article
        v-for="file in generatedFiles"
        :key="file.key"
        :class="['file-card', `is-${file.statusKind}`, { 'has-error': file.statusKind === 'error' }]"
      >
        <div class="file-icon-wrapper" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path
              d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7l-5-5Z"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path d="M14 2v5h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M8 13h8M8 17h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </div>

        <div class="file-info">
          <span class="file-name" :title="file.name">{{ file.name }}</span>
          <span class="file-meta">
            <span>{{ file.sizeLabel }}</span>
            <span v-if="file.extension" class="dot-divider">·</span>
            <span v-if="file.extension">{{ file.extension }}</span>
            <span class="dot-divider">·</span>
            <span class="file-status">{{ file.statusLabel }}</span>
          </span>
          <small v-if="file.error" class="file-error-message">{{ file.error }}</small>
        </div>

        <a
          v-if="file.downloadHref"
          class="download-button"
          :href="file.downloadHref"
          :download="file.name"
          target="_blank"
          rel="noopener noreferrer"
          :title="file.actionLabel"
          :aria-label="`${file.actionLabel}: ${file.name}`"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              d="M10.75 2.75a.75.75 0 0 0-1.5 0v8.61L6.3 8.24a.75.75 0 1 0-1.1 1.02l4.25 4.5a.75.75 0 0 0 1.1 0l4.25-4.5a.75.75 0 1 0-1.1-1.02l-2.95 3.12V2.75Z"
            />
            <path
              d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z"
            />
          </svg>
        </a>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, inject, unref } from 'vue'
import { normalizeFileView } from '../../lib/fileView'

type GeneratedFileStatus = 'ready' | 'local' | 'attached' | 'error'

interface GeneratedFileView {
  key: string
  name: string
  extension: string
  mimeType: string
  sizeLabel: string
  statusKind: GeneratedFileStatus
  statusLabel: string
  downloadHref: string
  actionLabel: string
  error: string
}

const props = defineProps<{
  content?: {
    message?: string
    files?: any[]
  }
}>()

const difyBaseUrl = inject<any>('difyBaseUrl', '')

const title = computed(() => String(props.content?.message || 'File generated'))

const generatedFiles = computed<GeneratedFileView[]>(() => {
  const rawFiles = Array.isArray(props.content?.files) ? props.content.files : []
  const baseUrl = String(unref(difyBaseUrl) || '')

  return rawFiles.map((rawFile, index) => toGeneratedFileView(rawFile, index, baseUrl))
})

function toGeneratedFileView(rawFile: any, index: number, baseUrl: string): GeneratedFileView {
  const normalized = normalizeFileView(rawFile, index, baseUrl)
  const rawStatus = String(rawFile?.status || '').toLowerCase()
  const statusKind = getStatusKind(rawStatus, normalized.href)

  return {
    key: normalized.key,
    name: normalized.name,
    extension: getExtension(normalized.name),
    mimeType: normalized.mimeType,
    sizeLabel: formatBytes(rawFile?.size, normalized.sizeLabel),
    statusKind,
    statusLabel: getStatusLabel(statusKind),
    downloadHref: normalized.href,
    actionLabel: normalized.href ? 'Download' : 'No download available',
    error: statusKind === 'error' ? String(rawFile?.error || '') : '',
  }
}

function getStatusKind(status: string, href: string): GeneratedFileStatus {
  if (status === 'upload_failed') return 'error'
  if (status === 'attached') return 'attached'
  if (href) return 'ready'
  return 'local'
}

function getStatusLabel(status: GeneratedFileStatus) {
  if (status === 'error') return 'Upload failed'
  if (status === 'ready') return 'Download ready'
  if (status === 'attached') return 'Attached to chat'
  return 'Saved in workspace'
}

function getExtension(filename: string) {
  const match = filename.match(/\.([^.]+)$/)
  return match ? match[1].toUpperCase() : ''
}

function formatBytes(value: unknown, fallback: string) {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes <= 0) return fallback || '0 B'

  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }

  const precision = unitIndex === 0 ? 0 : 1
  return `${size.toFixed(precision)} ${units[unitIndex]}`
}
</script>

<style scoped>
.generated-file-container {
  align-self: flex-start;
  width: fit-content;
  min-width: 300px;
  max-width: 90%;
  margin: 8px auto 8px 0;
}

.generated-file-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  padding-left: 4px;
  color: #475569;
  font-size: 12px;
  font-weight: 500;
}

.header-icon {
  width: 16px;
  height: 16px;
  color: #64748b;
}

.generated-files-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #f8fafc;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.file-card:hover {
  border-color: #cbd5e1;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
}

.file-icon-wrapper {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: #e0e7ff;
  color: #4f46e5;
}

.file-icon-wrapper svg {
  width: 22px;
  height: 22px;
}

.file-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.file-name {
  overflow: hidden;
  color: #1e293b;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  align-items: center;
  min-width: 0;
  color: #64748b;
  font-size: 12px;
}

.dot-divider {
  margin: 0 6px;
  color: #94a3b8;
  font-weight: 600;
}

.file-status {
  color: #16a34a;
  font-weight: 500;
}

.download-button {
  flex: none;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid #cbd5e1;
  border-radius: 50%;
  background: #fff;
  color: #475569;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.download-button:hover {
  border-color: #94a3b8;
  background: #f1f5f9;
  color: #1e293b;
  transform: scale(1.05);
}

.download-button svg {
  width: 18px;
  height: 18px;
}

.file-card.has-error {
  border-color: #fca5a5;
  background: #fef2f2;
}

.file-card.has-error .file-icon-wrapper {
  background: #fee2e2;
  color: #dc2626;
}

.file-card.has-error .file-status {
  color: #dc2626;
}

.file-error-message {
  color: #b91c1c;
  font-size: 12px;
}
</style>
