import { describe, expect, it, vi } from 'vitest'
import { CC_AGENT_ACTIVITY_TYPES, createCcActivityRenderers } from './activityRenderers'

vi.mock('@copilotkit/vue/v2', () => ({
  createA2UIMessageRenderer: vi.fn(() => ({ activityType: 'a2ui.message' })),
}))

describe('activity renderers', () => {
  it('registers A2UI plus the operational cc_agent activity renderer set', () => {
    const renderers = createCcActivityRenderers()

    expect(renderers[0]).toEqual({ activityType: 'a2ui.message' })
    expect(renderers.slice(1).map((renderer: any) => renderer.activityType)).toEqual(CC_AGENT_ACTIVITY_TYPES)
    expect(CC_AGENT_ACTIVITY_TYPES).not.toContain('cc_agent.ui_surface')
  })
})
