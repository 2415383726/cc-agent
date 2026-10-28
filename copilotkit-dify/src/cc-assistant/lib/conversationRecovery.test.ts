import { gzipSync } from 'node:zlib'
import { describe, expect, it } from 'vitest'
import { decodeConversationRecovery } from './conversationRecovery'

describe('conversation recovery projection', () => {
  it('restores a v1 pending question without exposing history or permissions', async () => {
    const state = { revision: 7, history: [{ content: 'private history' }],
      permissions: { allowed_tools: { write: 'conversation' } },
      last_execution_metadata: { run_id: 'r', finish_reason: 'awaiting_user', question: {
        id: 'pending', question: 'Continue?', purpose: 'permission', options: [
          { label: 'Allow', value: 'allow_once' }], fields: [{ name: 'count', type: 'number' }],
      } } }
    const encoded = 'ccagent-state:v1:gzip-base64:' + gzipSync(JSON.stringify(state)).toString('base64')
    const restored = await decodeConversationRecovery(encoded)
    expect(restored).toMatchObject({ revision: 7, runId: 'r', status: 'awaiting_user',
      question: { id: 'pending', question: 'Continue?', fields: [{ name: 'count', type: 'number' }] } })
    expect(JSON.stringify(restored)).not.toContain('private history')
    expect(restored).not.toHaveProperty('permissions')
  })

  it('rejects a malformed state instead of claiming no pending interaction exists', async () => {
    await expect(decodeConversationRecovery('broken')).rejects.toThrow()
  })
})
