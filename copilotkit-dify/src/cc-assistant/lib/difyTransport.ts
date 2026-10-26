import { streamDifySse } from './difySse'
import type { Message } from '@ag-ui/core'
import { copilotDifyDebug } from './debugLog'
import { historyRecordToMessages } from './difyHistoryMessages'

export interface DifyStreamChatRequest {
  baseUrl: string
  apiKey: string
  user: string
  conversationId: string
  query: string
  inputs: Record<string, unknown>
  files?: DifyUploadedFile[]
  signal?: AbortSignal
}

export interface DifyUploadedFile {
  id: string
  type?: string
  name?: string
  mimeType?: string
  size?: number
}

export interface DifyUploadFileRequest {
  baseUrl: string
  apiKey: string
  user: string
  file: File
}

export interface DifyStopChatRequest {
  baseUrl: string
  apiKey: string
  user: string
  taskId: string
}

export interface DifyConversation {
  id: string
  name: string
  status: string
  introduction: string
  inputs: Record<string, unknown>
  createdAt: number
  updatedAt: number
}

export interface DifyListConversationsRequest {
  baseUrl: string
  apiKey: string
  user: string
  limit?: number
  lastId?: string
  sortBy?: string
}

export interface DifyListConversationsResult {
  conversations: DifyConversation[]
  hasMore: boolean
  lastId: string
}

export interface DifyRenameConversationRequest {
  baseUrl: string
  apiKey: string
  user: string
  conversationId: string
  name?: string
  autoGenerate?: boolean
}

export interface DifyDeleteConversationRequest {
  baseUrl: string
  apiKey: string
  user: string
  conversationId: string
}

export interface DifyListMessagesRequest {
  baseUrl: string
  apiKey: string
  user: string
  conversationId: string
  limit?: number
  firstId?: string
}

export interface DifyStreamChatResult {
  response: {
    conversationId: string
    taskId: string
  }
  events: AsyncIterable<Record<string, any>>
}

export interface DifyListMessagesResult {
  messages: Message[]
  hasMore: boolean
  firstId: string
}

function normalizedBaseUrl(baseUrl: string) {
  return String(baseUrl || '').replace(/\/+$/, '')
}

function fileTypeFromMime(mimeType: string) {
  return String(mimeType || '').toLowerCase().startsWith('image/') ? 'image' : 'document'
}

function normalizeFiles(files: DifyUploadedFile[] = []) {
  return files
    .filter((file) => file?.id)
    .map((file) => ({
      type: file.type || fileTypeFromMime(file.mimeType || ''),
      transfer_method: 'local_file',
      upload_file_id: file.id,
    }))
}

function normalizeConversation(record: Record<string, any>): DifyConversation {
  return {
    id: String(record.id || ''),
    name: String(record.name || '新会话'),
    status: String(record.status || 'normal'),
    introduction: String(record.introduction || ''),
    inputs: record.inputs && typeof record.inputs === 'object' ? record.inputs : {},
    createdAt: Number(record.created_at || record.createdAt || 0),
    updatedAt: Number(record.updated_at || record.updatedAt || record.created_at || record.createdAt || 0),
  }
}

async function assertOk(response: Response, message: string) {
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `${message}: ${response.status}`)
  }
}

export async function listMessages(request: DifyListMessagesRequest): Promise<DifyListMessagesResult> {
  const params = new URLSearchParams({
    conversation_id: request.conversationId,
    user: request.user,
    limit: String(request.limit || 20),
  })
  if (request.firstId) params.set('first_id', request.firstId)

  const response = await fetch(`${normalizedBaseUrl(request.baseUrl)}/messages?${params.toString()}`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${request.apiKey}`,
    },
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `Dify messages request failed: ${response.status}`)
  }

  const data = await response.json()
  const records = Array.isArray(data.data) ? sortHistoryRecordsChronologically(data.data) : []
  copilotDifyDebug('history.raw.records', {
    conversationId: request.conversationId,
    count: records.length,
    records: records.map((record: any) => ({
      id: record?.id || record?.message_id || '',
      query: String(record?.query || '').slice(0, 120),
      answer: String(record?.answer || '').slice(0, 300),
      answerJson: JSON.stringify(record?.answer ?? ''),
      answerLength: String(record?.answer || '').length,
      files: Array.isArray(record?.message_files) ? record.message_files.length : 0,
      thoughts: Array.isArray(record?.agent_thoughts) ? record.agent_thoughts.length : 0,
      thoughtLabels: Array.isArray(record?.agent_thoughts)
        ? record.agent_thoughts.slice(-5).map((thought: any) => (
          thought?.label
          || thought?.data?.label
          || thought?.data?.data?.label
          || thought?.tool
          || thought?.event
          || ''
        ))
        : [],
    })),
  })
  const messages = records.flatMap(historyRecordToMessages)
  copilotDifyDebug('history.converted.messages', {
    conversationId: request.conversationId,
    count: messages.length,
    messages: messages.map((message: any) => ({
      id: message?.id,
      role: message?.role,
      content: typeof message?.content === 'string' ? message.content.slice(0, 300) : message?.content,
      contentJson: JSON.stringify(message?.content ?? ''),
      activityType: message?.activityType,
      metadata: message?.metadata,
    })),
  })
  return {
    messages,
    hasMore: Boolean(data.has_more),
    firstId: String(records[0]?.id || records[0]?.message_id || ''),
  }
}

function sortHistoryRecordsChronologically(records: Record<string, any>[]) {
  return records
    .slice()
    .sort((a, b) => historyRecordTime(a) - historyRecordTime(b))
}

function historyRecordTime(record: Record<string, any>) {
  const value = record.created_at ?? record.createdAt ?? record.created ?? 0
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : 0
}

export async function listConversations(request: DifyListConversationsRequest): Promise<DifyListConversationsResult> {
  const params = new URLSearchParams({
    user: request.user,
    limit: String(request.limit || 20),
  })
  if (request.lastId) params.set('last_id', request.lastId)
  if (request.sortBy) params.set('sort_by', request.sortBy)

  const response = await fetch(`${normalizedBaseUrl(request.baseUrl)}/conversations?${params.toString()}`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${request.apiKey}`,
    },
  })

  await assertOk(response, 'Dify conversations request failed')
  const data = await response.json()
  const conversations = Array.isArray(data.data)
    ? data.data.map(normalizeConversation).filter((conversation: DifyConversation) => conversation.id)
    : []
  return {
    conversations,
    hasMore: Boolean(data.has_more),
    lastId: conversations[conversations.length - 1]?.id || '',
  }
}

export async function renameConversation(request: DifyRenameConversationRequest): Promise<DifyConversation> {
  const response = await fetch(`${normalizedBaseUrl(request.baseUrl)}/conversations/${encodeURIComponent(request.conversationId)}/name`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${request.apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user: request.user,
      name: request.name || '',
      auto_generate: Boolean(request.autoGenerate),
    }),
  })

  await assertOk(response, 'Dify conversation rename failed')
  return normalizeConversation(await response.json())
}

export async function deleteConversation(request: DifyDeleteConversationRequest): Promise<void> {
  const response = await fetch(`${normalizedBaseUrl(request.baseUrl)}/conversations/${encodeURIComponent(request.conversationId)}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${request.apiKey}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ user: request.user }),
  })

  await assertOk(response, 'Dify conversation delete failed')
}

export async function uploadFile(request: DifyUploadFileRequest): Promise<DifyUploadedFile> {
  const formData = new FormData()
  formData.append('file', request.file)
  formData.append('user', request.user)

  const response = await fetch(`${normalizedBaseUrl(request.baseUrl)}/files/upload`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${request.apiKey}`,
    },
    body: formData,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `Dify file upload failed: ${response.status}`)
  }

  const data = await response.json()
  const mimeType = String(data.mime_type || data.mimeType || request.file.type || '')
  return {
    id: String(data.id || data.upload_file_id || ''),
    name: String(data.name || request.file.name || ''),
    type: fileTypeFromMime(mimeType),
    mimeType,
    size: Number(data.size || request.file.size || 0),
  }
}

export async function streamChat(request: DifyStreamChatRequest): Promise<DifyStreamChatResult> {
  const response = await fetch(`${normalizedBaseUrl(request.baseUrl)}/chat-messages`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${request.apiKey}`,
      'Content-Type': 'application/json',
    },
    signal: request.signal,
    body: JSON.stringify({
      inputs: request.inputs,
      query: request.query,
      response_mode: 'streaming',
      user: request.user,
      conversation_id: request.conversationId || '',
      auto_generate_name: true,
      files: normalizeFiles(request.files),
    }),
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `Dify request failed: ${response.status}`)
  }

  if (!response.body) {
    throw new Error('Dify streaming response body is empty')
  }

  return {
    response: {
      conversationId: '',
      taskId: '',
    },
    events: streamDifySse(response.body),
  }
}

export async function stopChat(request: DifyStopChatRequest): Promise<void> {
  await fetch(`${normalizedBaseUrl(request.baseUrl)}/chat-messages/${request.taskId}/stop`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${request.apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ user: request.user }),
  })
}
