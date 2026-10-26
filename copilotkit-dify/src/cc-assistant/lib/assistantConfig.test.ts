import { describe, expect, it } from 'vitest'
import {
  DEFAULT_ASSISTANT_STORAGE_KEY_PREFIX,
  assistantFloatingDockStorageKey,
  assistantUiStyle,
  normalizeDifyAssistantConfig,
  validateDifyAssistantConfig,
} from './assistantConfig'

describe('assistant config', () => {
  it('normalizes the host Dify config without injecting cc_agent internal fields', () => {
    const inputs = {
      tenantId: 'tenant-1',
      module: 'cadre',
    }
    const config = normalizeDifyAssistantConfig({
      baseUrl: ' https://dify.example/v1/ ',
      apiKey: ' app-xxx ',
      user: ' user-1 ',
      token: ' agent-token ',
      inputs,
    })

    expect(config).toEqual({
      baseUrl: 'https://dify.example/v1',
      apiKey: 'app-xxx',
      user: 'user-1',
      token: 'agent-token',
      inputs,
    })
    expect(config.inputs).toBe(inputs)
    expect(config).not.toHaveProperty('stateId')
    expect(config.inputs).not.toHaveProperty('show_tool_calls')
    expect(config.inputs).not.toHaveProperty('capability_mode')
    expect(config.inputs).not.toHaveProperty('app_skills_yaml')
    expect(config.inputs).not.toHaveProperty('state_id')
  })

  it('keeps token as a first-class agent auth field and leaves inputs optional', () => {
    const config = normalizeDifyAssistantConfig({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-local',
      user: 'employee-001',
      token: 'jwt-token',
    })

    expect(config.token).toBe('jwt-token')
    expect(config.inputs).toEqual({})
  })

  it('generates floating dock storage keys from the provided prefix', () => {
    expect(DEFAULT_ASSISTANT_STORAGE_KEY_PREFIX).toBe('cc-dify-assistant')
    expect(assistantFloatingDockStorageKey('cadre-system-assistant')).toBe('cadre-system-assistant:floating-dock')
    expect(assistantFloatingDockStorageKey('')).toBe('cc-dify-assistant:floating-dock')
  })

  it('maps optional UI sizing to scoped custom properties', () => {
    expect(assistantUiStyle({
      drawerWidth: '80vw',
      drawerMaxWidth: '1280px',
      defaultSidebarCollapsed: false,
    })).toEqual({
      '--cc-agent-drawer-width': '80vw',
      '--cc-agent-drawer-max-width': '1280px',
    })
  })
  it('validates required host-visible Dify fields', () => {
    expect(validateDifyAssistantConfig(normalizeDifyAssistantConfig({
      baseUrl: 'https://dify.example/v1',
      apiKey: 'app-xxx',
      user: 'u1',
    }))).toBe('')

    expect(validateDifyAssistantConfig(normalizeDifyAssistantConfig({
      baseUrl: '',
      apiKey: 'app-xxx',
      user: 'u1',
    }))).toBe('请先配置 Dify Base URL')
  })
})
