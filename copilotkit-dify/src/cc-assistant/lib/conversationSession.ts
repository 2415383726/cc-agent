export interface ConversationSessionConfig {
  baseUrl: string
  user: string
  stateId?: string
}

function normalizeBaseUrl(baseUrl: string) {
  return String(baseUrl || '').replace(/\/+$/, '')
}

export function conversationSessionKey(config: ConversationSessionConfig) {
  return [
    'copilotkit-dify-session',
    normalizeBaseUrl(config.baseUrl),
    String(config.user || ''),
  ].join(':')
}

function legacyConversationSessionKey(config: ConversationSessionConfig) {
  return [
    'copilotkit-dify-session',
    normalizeBaseUrl(config.baseUrl),
    String(config.user || ''),
    String(config.stateId || '1'),
  ].join(':')
}

export function loadConversationId(storage: Pick<Storage, 'getItem' | 'setItem'>, config: ConversationSessionConfig) {
  try {
    const key = conversationSessionKey(config)
    const current = String(storage.getItem(key) || '').trim()
    if (current) return current
    const legacy = String(storage.getItem(legacyConversationSessionKey(config)) || '').trim()
    if (legacy) storage.setItem(key, legacy)
    return legacy
  } catch (_) {
    return ''
  }
}

export function saveConversationId(storage: Pick<Storage, 'setItem'>, config: ConversationSessionConfig, conversationId: string) {
  const id = String(conversationId || '').trim()
  if (!id) return
  storage.setItem(conversationSessionKey(config), id)
}

export function clearConversationId(storage: Pick<Storage, 'removeItem'>, config: ConversationSessionConfig) {
  storage.removeItem(conversationSessionKey(config))
}
