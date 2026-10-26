import type { Message } from '@ag-ui/core'

export interface HistoryUploadedFile {
  id: string
  type?: string
  name?: string
  mimeType?: string
  size?: number
}

export const MISSING_ANSWER_NOTICE = '该历史轮次没有保存最终回复。'

function fileTypeFromMime(mimeType: string) {
  return String(mimeType || '').toLowerCase().startsWith('image/') ? 'image' : 'document'
}

function normalizeHistoryFile(file: Record<string, any>): HistoryUploadedFile {
  const mimeType = String(file.mime_type || file.mimeType || file.mime || '')
  return {
    id: String(file.id || file.upload_file_id || file.uploadFileId || ''),
    name: String(file.name || file.filename || file.document_name || ''),
    type: String(file.type || fileTypeFromMime(mimeType)),
    mimeType,
    size: file.size == null ? undefined : Number(file.size),
  }
}

export function isLikelyWorkflowPlaceholder(value: string) {
  const lines = value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^-{3,}$/.test(line))
  const normalized = lines
    .join('\n')
    .toLowerCase()
  if (!normalized) return true
  if (/^(token|id|task_id|conversation_id):(\n(token|id|task_id|conversation_id):)*$/.test(normalized)) return true
  if (normalized === 'token:\nid:') return true
  return false
}

function safeParseJson(value: any): any {
  if (typeof value !== 'string') return value
  const trimmed = value.trim()
  if (!trimmed || (!trimmed.startsWith('{') && !trimmed.startsWith('['))) return value
  try {
    return JSON.parse(trimmed)
  } catch (_) {
    return value
  }
}

function getPath(value: any, path: string[]): any {
  let current = value
  for (const key of path) {
    if (!current || typeof current !== 'object') return undefined
    current = current[key]
  }
  return current
}

function finalAnswerDataFromThought(thought: any): any {
  const candidates = [
    thought,
    thought?.data,
    thought?.data?.data,
    thought?.tool_process_data,
    safeParseJson(thought?.observation),
    safeParseJson(thought?.thought),
  ]

  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== 'object') continue
    const label = String(candidate.label || candidate.name || candidate.kind || thought?.label || thought?.tool || '')
    const kind = String(candidate.kind || getPath(candidate, ['data', 'kind']) || '')
    const isFinalAnswer = label === 'Final answer'
      || label === 'cc_agent.final_answer'
      || kind === 'cc_agent.final_answer'
    if (!isFinalAnswer) continue
    return candidate
  }
  return null
}

export function finalAnswerFromAgentThoughts(thoughts: any[]): string {
  if (!Array.isArray(thoughts)) return ''
  for (const thought of thoughts.slice().reverse()) {
    const data = finalAnswerDataFromThought(thought)
    if (!data) continue
    const answer = String(
      data.answer
      || getPath(data, ['data', 'answer'])
      || getPath(data, ['result', 'answer'])
      || getPath(data, ['payload', 'answer'])
      || '',
    ).trim()
    if (answer && !isLikelyWorkflowPlaceholder(answer)) return answer
  }
  return ''
}

export function historyRecordToMessages(record: Record<string, any>): Message[] {
  const id = String(record.id || record.message_id || Math.random().toString(36).slice(2, 10))
  const files = Array.isArray(record.message_files)
    ? record.message_files.map(normalizeHistoryFile).filter((file: HistoryUploadedFile) => file.id || file.name)
    : []
  const messages: Message[] = []
  const query = String(record.query || '').trim()
  const nativeAnswer = String(record.answer || record.error || '').trim()
  const answer = isLikelyWorkflowPlaceholder(nativeAnswer)
    ? finalAnswerFromAgentThoughts(record.agent_thoughts)
    : nativeAnswer

  if (query) {
    messages.push({
      id: `history:${id}:user`,
      role: 'user',
      content: query,
      ...(files.length ? { files } : {}),
    } as Message)

    if (files.length) {
      messages.push({
        id: `history:${id}:uploaded-files`,
        role: 'activity',
        activityType: 'cc_agent.uploaded_files',
        content: {
          source: 'history',
          files,
        },
      } as Message)
    }
  }

  const assistantText = isLikelyWorkflowPlaceholder(answer) ? MISSING_ANSWER_NOTICE : answer
  if (assistantText) {
    messages.push({
      id: `history:${id}:assistant:answer`,
      role: 'assistant',
      content: assistantText,
    } as Message)
  }

  return messages
}
