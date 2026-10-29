export interface WorkbenchConfig {
  baseUrl: string
  apiKey: string
  user: string
  inputs: Record<string, unknown>
}

export interface DeploymentConfig {
  title?: string
  baseUrl?: string
  user?: string
  inputs?: Record<string, unknown>
}

const SESSION_KEY = 'pi-workbench-session-credentials'

declare global {
  interface Window {
    __PI_WORKBENCH__?: DeploymentConfig
  }
}

export function defaultConfig(): WorkbenchConfig {
  const deployment = typeof window !== 'undefined' ? window.__PI_WORKBENCH__ || {} : {}
  const stored = readSessionCredentials()
  return {
    baseUrl: stored.baseUrl || deployment.baseUrl || '/v1',
    apiKey: stored.apiKey || '',
    user: stored.user || deployment.user || 'pi-workbench-user',
    inputs: stored.inputs || deployment.inputs || {},
  }
}

export interface SessionCredentials {
  baseUrl: string
  apiKey: string
  user: string
  inputs: Record<string, unknown>
}

export function readSessionCredentials(): Partial<SessionCredentials> {
  if (typeof sessionStorage === 'undefined') return {}
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export function saveSessionCredentials(config: WorkbenchConfig): void {
  if (typeof sessionStorage === 'undefined') return
  sessionStorage.setItem(
    SESSION_KEY,
    JSON.stringify({
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
      user: config.user,
      inputs: config.inputs,
    }),
  )
}

export async function loadDeploymentConfig(): Promise<DeploymentConfig | null> {
  try {
    const response = await fetch('./config.json', { cache: 'no-store' })
    if (!response.ok) return null
    const payload = await response.json()
    return payload && typeof payload === 'object' ? payload : null
  } catch {
    return null
  }
}

export function parseInputs(text: string): Record<string, unknown> {
  const value = String(text || '').trim()
  if (!value) return {}
  const parsed = JSON.parse(value)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('应用输入必须是 JSON 对象。')
  }
  return parsed as Record<string, unknown>
}
