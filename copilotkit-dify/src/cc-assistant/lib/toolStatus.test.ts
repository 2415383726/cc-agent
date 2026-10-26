import { describe, expect, it } from 'vitest'
import { toolDisplayLabel, toolDisplayState } from './toolStatus'

describe('toolStatus', () => {
  it('shows permission tool results as waiting instead of complete', () => {
    const result = 'Executing current_time requires user permission.'

    expect(toolDisplayState('complete', result)).toBe('waiting_permission')
    expect(toolDisplayLabel('complete', result)).toBe('等待授权')
  })

})
