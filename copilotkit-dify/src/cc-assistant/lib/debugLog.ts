export function copilotDifyDebugEnabled() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem('copilotkitDifyDebug') === '1'
}

export function copilotDifyDebugConsoleEnabled() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem('copilotkitDifyDebugConsole') === '1'
}

declare global {
  interface Window {
    __copilotkitDifyDebug?: Array<{
      at: string
      label: string
      payload: Record<string, unknown>
    }>
  }
}

function safeJson(value: unknown) {
  try {
    return JSON.stringify(value)
  } catch (error: any) {
    return JSON.stringify({
      unserializable: true,
      message: error?.message || String(error),
    })
  }
}

export function copilotDifyDebug(label: string, payload: Record<string, unknown> = {}) {
  if (!copilotDifyDebugEnabled()) return
  const entry = {
    at: new Date().toISOString(),
    label,
    payload,
  }
  window.__copilotkitDifyDebug = [...(window.__copilotkitDifyDebug || []), entry].slice(-100)
  if (copilotDifyDebugConsoleEnabled()) {
    console.info(`[copilotkit-dify] ${label} ${safeJson(payload)}`)
  }
}
