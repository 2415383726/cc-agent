export interface DifySessionThreadInput {
  user?: string
  conversationId?: string
  threadKey?: string
}

function sanitizeThreadPart(value: string) {
  return value.trim().replace(/[^a-zA-Z0-9_.:-]+/g, '_') || 'anonymous'
}

export function chatThreadIdForDifySession(input: DifySessionThreadInput) {
  const threadKey = input.threadKey || (input.conversationId ? `conversation:${input.conversationId}` : 'draft:new')
  return `copilotkit-dify:${sanitizeThreadPart(input.user || '')}:${sanitizeThreadPart(threadKey)}`
}
