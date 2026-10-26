import type { DifyAgentConfig } from './DifyAgUiAgent'

export interface CcDifyAssistantDifyConfig {
  baseUrl: string
  apiKey: string
  user: string
  token?: string
  inputs?: Record<string, unknown>
}

export interface CcDifyAssistantUiConfig {
  drawerWidth?: string
  drawerMaxWidth?: string
  defaultSidebarCollapsed?: boolean
}

export interface CcDifyAssistantProps {
  dify: CcDifyAssistantDifyConfig
  catalog?: unknown
  title?: string
  storageKeyPrefix?: string
  ui?: CcDifyAssistantUiConfig
}

export const DEFAULT_ASSISTANT_STORAGE_KEY_PREFIX = 'cc-dify-assistant'

export function normalizeDifyAssistantConfig(input: Partial<CcDifyAssistantDifyConfig> = {}): DifyAgentConfig {
  return {
    baseUrl: cleanString(input.baseUrl).replace(/\/+$/, ''),
    apiKey: cleanString(input.apiKey),
    user: cleanString(input.user),
    token: cleanString(input.token),
    inputs: isRecord(input.inputs) ? input.inputs : {},
  }
}

export function validateDifyAssistantConfig(config: Pick<DifyAgentConfig, 'baseUrl' | 'apiKey' | 'user'>) {
  if (!cleanString(config.baseUrl)) return '请先配置 Dify Base URL'
  if (!cleanString(config.apiKey)) return '请先配置 Dify API Key'
  if (!cleanString(config.user)) return '请先配置 Dify User'
  return ''
}

export function assistantFloatingDockStorageKey(prefix?: string) {
  return `${cleanString(prefix) || DEFAULT_ASSISTANT_STORAGE_KEY_PREFIX}:floating-dock`
}

export function assistantUiStyle(ui: CcDifyAssistantUiConfig = {}) {
  const style: Record<string, string> = {}
  const drawerWidth = cleanString(ui.drawerWidth)
  const drawerMaxWidth = cleanString(ui.drawerMaxWidth)
  if (drawerWidth) style['--cc-agent-drawer-width'] = drawerWidth
  if (drawerMaxWidth) style['--cc-agent-drawer-max-width'] = drawerMaxWidth
  return style
}

function cleanString(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
