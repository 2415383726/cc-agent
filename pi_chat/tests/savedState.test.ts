import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { Blob as NativeBlob } from 'node:buffer'
import { gzipSync } from 'node:zlib'
import { eventsFromSavedState } from '../src/projection/savedState'
import { applyEvent, newView } from '../src/projection/transcript'

const browserBlob = globalThis.Blob
const encode = (state: unknown) =>
  'piagent-state:v1:gzip-base64:' + gzipSync(JSON.stringify(state)).toString('base64')

beforeEach(() => { globalThis.Blob = NativeBlob as typeof Blob })
afterEach(() => { globalThis.Blob = browserBlob })

describe('saved-state display recovery', () => {
  it('restores a separate approval card without granting authorization', async () => {
    const events = await eventsFromSavedState(encode({
      schema_version: 1, session_id: 'conv', run_id: 'r1', revision: 2,
      last_status: 'awaiting_approval',
      pending: {
        kind: 'approval', id: 'p1', tool_call_id: 't1', tool_name: 'save_demo',
        arguments: { text: 'example' }, source: 'mcp', scope_options: ['once', 'session'],
      },
    }), 'conv')
    const view = newView()
    for (const event of events) applyEvent(view, event)
    expect(view.entries.find((entry) => entry.kind === 'approval')).toMatchObject({
      pendingId: 'p1', tool: 'save_demo', status: 'waiting',
    })
    expect(view.terminal?.status).toBe('awaiting_approval')
    expect(events.map((event) => event.type)).toEqual(['approval.requested', 'run.state'])
  })

  it('rejects another conversation instead of displaying its pending interaction', async () => {
    await expect(eventsFromSavedState(encode({
      schema_version: 1, session_id: 'other', pending: { kind: 'approval', id: 'p1' },
    }), 'conv')).rejects.toThrow('不属于当前会话')
  })

  it('rejects an oversized inflated payload even when it compresses into a small string', async () => {
    const value = encode({ schema_version: 1, session_id: 'conv', text: 'A'.repeat(4 * 1024 * 1024) })
    expect(value.length).toBeLessThan(190_000)
    await expect(eventsFromSavedState(value, 'conv')).rejects.toThrow('超过读取限制')
  })

  it('rejects unsupported state versions', async () => {
    await expect(eventsFromSavedState(encode({
      schema_version: 2, session_id: 'conv',
    }), 'conv')).rejects.toThrow()
  })
})
