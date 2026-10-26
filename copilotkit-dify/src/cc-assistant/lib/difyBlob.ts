interface DifyBlobChunk {
  id: string
  sequence: number
  totalLength: number
  blob: string
  end: boolean
  meta: Record<string, any>
}

interface DifyBlobState {
  id: string
  totalLength: number
  meta: Record<string, any>
  chunks: Map<number, string>
}

export interface DifyBlobActivity {
  messageId: string
  activityType: 'cc_agent.skill_artifact'
  content: {
    message: string
    skillName?: string
    scriptName?: string
    files: Array<{
      id: string
      name: string
      mime_type: string
      size: number
      status: 'attached'
      download_data_url?: string
    }>
  }
}

let artifactSeq = 0

export function createDifyBlobAccumulator() {
  const pending = new Map<string, DifyBlobState>()

  return {
    ingest(rawEvent: any): DifyBlobActivity | null {
      const chunk = extractDifyBlobChunk(rawEvent)
      if (!chunk) return null

      const state = pending.get(chunk.id) || {
        id: chunk.id,
        totalLength: chunk.totalLength,
        meta: {},
        chunks: new Map<number, string>(),
      }
      state.totalLength = chunk.totalLength || state.totalLength
      state.meta = { ...state.meta, ...chunk.meta }
      if (chunk.blob) {
        state.chunks.set(chunk.sequence, chunk.blob)
      }
      pending.set(chunk.id, state)

      if (!chunk.end) return null

      pending.delete(chunk.id)
      return blobStateToActivity(state)
    },
  }
}

export function isDifyBlobEvent(rawEvent: any): boolean {
  return Boolean(extractDifyBlobChunk(rawEvent))
}

function blobStateToActivity(state: DifyBlobState): DifyBlobActivity {
  const meta = state.meta || {}
  const name = stringValue(meta.filename || meta.output_filename || meta.name || state.id || 'generated_file')
  const mimeType = stringValue(meta.mime_type || meta.mime || meta.mimetype || 'application/octet-stream')
  const binary = sortedChunks(state.chunks)
    .map(decodeBase64ToBinary)
    .join('')
  const encoded = binary ? encodeBinaryToBase64(binary) : ''
  const file: DifyBlobActivity['content']['files'][number] = {
    id: state.id,
    name,
    mime_type: mimeType,
    size: state.totalLength || binary.length,
    status: 'attached',
  }
  if (encoded) {
    file.download_data_url = `data:${mimeType};base64,${encoded}`
  }

  return {
    messageId: `skill_artifact_${++artifactSeq}`,
    activityType: 'cc_agent.skill_artifact',
    content: {
      message: 'Generated files were attached to this chat response.',
      ...(meta.skill_name ? { skillName: stringValue(meta.skill_name) } : {}),
      ...(meta.script_name ? { scriptName: stringValue(meta.script_name) } : {}),
      files: [file],
    },
  }
}

function sortedChunks(chunks: Map<number, string>) {
  return [...chunks.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, value]) => value)
}

function extractDifyBlobChunk(rawEvent: any): DifyBlobChunk | null {
  const payload = findBlobPayload(rawEvent)
  if (!payload) return null

  const type = stringValue(payload.type || payload.event).toLowerCase()
  const message = payload.message && typeof payload.message === 'object' ? payload.message : {}
  const meta = payload.meta && typeof payload.meta === 'object' ? payload.meta : {}
  if (type === 'blob_chunk') {
    const id = stringValue(message.id || payload.id)
    if (!id) return null
    return {
      id,
      sequence: numberValue(message.sequence ?? payload.sequence),
      totalLength: numberValue(message.total_length ?? message.totalLength ?? payload.total_length ?? payload.totalLength),
      blob: stringValue(message.blob ?? payload.blob),
      end: Boolean(message.end ?? payload.end),
      meta,
    }
  }

  if (type === 'blob') {
    const blob = stringValue(message.blob ?? payload.blob)
    if (!blob) return null
    const id = stringValue(payload.id || meta.id || meta.filename || `blob_${artifactSeq + 1}`)
    return {
      id,
      sequence: 0,
      totalLength: numberValue(payload.total_length ?? payload.totalLength) || decodedLength(blob),
      blob,
      end: true,
      meta,
    }
  }

  return null
}

function findBlobPayload(rawEvent: any, depth = 0): Record<string, any> | null {
  if (!rawEvent || depth > 5) return null
  const event = parseMaybeJson(rawEvent) || rawEvent
  if (!event || typeof event !== 'object') return null
  if (Array.isArray(event)) {
    for (const item of event) {
      const found = findBlobPayload(item, depth + 1)
      if (found) return found
    }
    return null
  }

  const type = stringValue(event.type || event.event).toLowerCase()
  if (type === 'blob_chunk' || type === 'blob') return event

  for (const key of ['data', 'metadata', 'message', 'payload', 'result']) {
    const found = findBlobPayload((event as Record<string, any>)[key], depth + 1)
    if (found) return found
  }
  return null
}

function parseMaybeJson(value: unknown): any {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  try {
    return JSON.parse(trimmed)
  } catch (_) {
    return null
  }
}

function decodeBase64ToBinary(value: string) {
  if (!value) return ''
  try {
    return atob(value)
  } catch (_) {
    return ''
  }
}

function encodeBinaryToBase64(value: string) {
  try {
    return btoa(value)
  } catch (_) {
    return ''
  }
}

function decodedLength(value: string) {
  return decodeBase64ToBinary(value).length
}

function numberValue(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

function stringValue(value: unknown) {
  return value == null ? '' : String(value)
}
