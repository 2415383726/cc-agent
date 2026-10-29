import { describe, expect, it } from 'vitest'
import { findPiEvent, parseDisplayEvent } from '../src/contract/display'

const valid = {
  schema: 'piagent.display.v1',
  schema_version: 1,
  type: 'message.delta',
  run_id: 'run_1',
  seq: 2,
  ts: 1,
  message_id: 'a1',
  delta: 'hi',
}

describe('display contract', () => {
  it('accepts a well-formed event', () => {
    const result = parseDisplayEvent(valid)
    expect(result.problem).toBeUndefined()
    expect(result.event?.type).toBe('message.delta')
    expect(result.event?.delta).toBe('hi')
  })

  it('rejects unknown versions and malformed events safely', () => {
    expect(parseDisplayEvent({ ...valid, schema_version: 2 }).problem).toBe('unsupported-version')
    expect(parseDisplayEvent({ ...valid, seq: 'x' }).problem).toBe('malformed')
    expect(parseDisplayEvent(null).problem).toBe('not-an-object')
  })

  it('finds events nested in Dify log payloads and JSON strings', () => {
    expect(findPiEvent({ event: 'agent_log', data: { piagent: valid } })?.event?.run_id).toBe('run_1')
    expect(findPiEvent({ data: JSON.stringify({ piagent: valid }) })?.event?.type).toBe('message.delta')
    expect(findPiEvent({ data: { other: true } })).toBeNull()
  })
})
