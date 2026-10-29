export interface DifyConfig {
  baseUrl: string
  apiKey: string
  user: string
  inputs: Record<string, unknown>
}

export interface UploadedFile {
  id: string
  type?: string
  name?: string
  mimeType?: string
  size?: number
}

export interface StreamChatRequest extends DifyConfig {
  conversationId: string
  query: string
  files?: UploadedFile[]
  signal?: AbortSignal
}

export interface DifyStreamResult {
  events: AsyncIterable<Record<string, any>>
}

function base(baseUrl: string): string {
  return String(baseUrl || '').replace(/\/+$/, '')
}

function auth(config: DifyConfig): Record<string, string> {
  return { Authorization: `Bearer ${config.apiKey}` }
}

async function assertOk(response: Response, message: string): Promise<void> {
  if (response.ok) return
  const text = await response.text().catch(() => '')
  let detail = ''
  try {
    detail = JSON.parse(text)?.message || ''
  } catch {
    detail = ''
  }
  throw new Error(detail || `${message} (${response.status})`)
}

export async function* streamDifySse(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      while (true) {
        const boundary = buffer.indexOf('\n\n')
        if (boundary < 0) break
        const chunk = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const lines = chunk
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean)
        const dataLines = lines.filter((line) => line.startsWith('data:'))
        if (!dataLines.length) continue
        const payload = dataLines.map((line) => line.slice(5).trim()).join('\n')
        if (!payload || payload === '[DONE]') continue
        try {
          yield JSON.parse(payload)
        } catch {
          continue
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function streamChat(request: StreamChatRequest): Promise<DifyStreamResult> {
  const response = await fetch(`${base(request.baseUrl)}/chat-messages`, {
    method: 'POST',
    headers: { ...auth(request), 'Content-Type': 'application/json' },
    signal: request.signal,
    body: JSON.stringify({
      inputs: request.inputs || {},
      query: request.query,
      response_mode: 'streaming',
      user: request.user,
      conversation_id: request.conversationId || '',
      auto_generate_name: true,
      files: (request.files || [])
        .filter((file) => file.id)
        .map((file) => ({
          type: file.type || (String(file.mimeType || '').startsWith('image/') ? 'image' : 'document'),
          transfer_method: 'local_file',
          upload_file_id: file.id,
        })),
    }),
  })
  await assertOk(response, 'Dify chat request failed')
  if (!response.body) throw new Error('Dify streaming response body is empty')
  return { events: streamDifySse(response.body) }
}

export async function stopChat(
  config: DifyConfig,
  taskId: string,
): Promise<void> {
  const response = await fetch(
    `${base(config.baseUrl)}/chat-messages/${encodeURIComponent(taskId)}/stop`,
    {
      method: 'POST',
      headers: { ...auth(config), 'Content-Type': 'application/json' },
      body: JSON.stringify({ user: config.user }),
    },
  )
  await assertOk(response, 'Dify stop request failed')
}

export async function uploadFile(config: DifyConfig, file: File): Promise<UploadedFile> {
  const form = new FormData()
  form.append('file', file)
  form.append('user', config.user)
  const response = await fetch(`${base(config.baseUrl)}/files/upload`, {
    method: 'POST',
    headers: auth(config),
    body: form,
  })
  await assertOk(response, 'Dify file upload failed')
  const data = await response.json()
  const mimeType = String(data.mime_type || data.mimeType || file.type || '')
  return {
    id: String(data.id || data.upload_file_id || ''),
    name: String(data.name || file.name || ''),
    type: String(data.type || (mimeType.startsWith('image/') ? 'image' : 'document')),
    mimeType,
    size: Number(data.size || file.size || 0),
  }
}

export interface DifyMessageRecord {
  id?: string
  query?: string
  answer?: string
  created_at?: number
  message_files?: Array<Record<string, unknown>>
  agent_thoughts?: Array<Record<string, unknown>>
}

export async function listMessages(
  config: DifyConfig,
  conversationId: string,
  options: { limit?: number; firstId?: string } = {},
): Promise<{ records: DifyMessageRecord[]; hasMore: boolean; firstId: string }> {
  const params = new URLSearchParams({
    conversation_id: conversationId,
    user: config.user,
    limit: String(options.limit || 20),
  })
  if (options.firstId) params.set('first_id', options.firstId)
  const response = await fetch(`${base(config.baseUrl)}/messages?${params.toString()}`, {
    headers: auth(config),
  })
  await assertOk(response, 'Dify history request failed')
  const payload = await response.json()
  const records: DifyMessageRecord[] = Array.isArray(payload.data)
    ? payload.data.slice().sort((left: any, right: any) => Number(left.created_at || 0) - Number(right.created_at || 0))
    : []
  return {
    records,
    hasMore: Boolean(payload.has_more),
    firstId: String(records[0]?.id || ''),
  }
}

export interface DifyConversation {
  id: string
  name: string
  updatedAt: number
}

export async function listConversations(
  config: DifyConfig,
  options: { limit?: number } = {},
): Promise<DifyConversation[]> {
  const params = new URLSearchParams({
    user: config.user,
    limit: String(options.limit || 20),
    sort_by: '-updated_at',
  })
  const response = await fetch(`${base(config.baseUrl)}/conversations?${params.toString()}`, {
    headers: auth(config),
  })
  await assertOk(response, 'Dify conversation request failed')
  const payload = await response.json()
  return Array.isArray(payload.data)
    ? payload.data
        .map((item: any) => ({
          id: String(item.id || ''),
          name: String(item.name || 'Untitled'),
          updatedAt: Number(item.updated_at || item.created_at || 0),
        }))
        .filter((item: DifyConversation) => item.id)
    : []
}
