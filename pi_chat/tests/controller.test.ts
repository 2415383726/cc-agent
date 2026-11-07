import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Blob as NativeBlob } from 'node:buffer'
import { gzipSync } from 'node:zlib'

vi.mock('../src/dify/transport', () => ({
  streamChat: vi.fn(),
  stopChat: vi.fn(),
  listMessages: vi.fn(),
  readAgentState: vi.fn(),
  listConversations: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  uploadFile: vi.fn(),
}))

import * as transport from '../src/dify/transport'
import { DifyController } from '../src/dify/controller'
import { SCHEMA } from '../src/contract/display'

const config = {
  baseUrl: '/v1',
  apiKey: 'app-test',
  user: 'u1',
  inputs: {},
}

function piEvent(type: string, seq: number, fields: Record<string, unknown> = {}) {
  return {
    schema: SCHEMA,
    schema_version: 1,
    type,
    run_id: 'run_1',
    seq,
    ts: seq,
    ...fields,
  }
}

async function* streamOf(items: unknown[]) {
  for (const item of items) yield item
}

function mockStream(items: unknown[]) {
  ;(transport.streamChat as any).mockResolvedValue({ events: streamOf(items) })
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(transport.readAgentState as any).mockResolvedValue(null)
})

describe('DifyController', () => {
  it('restores a persisted questionnaire when Dify history omits agent logs', async () => {
    const blob = globalThis.Blob
    globalThis.Blob = NativeBlob as typeof Blob
    try {
      const state = {
        schema_version: 1, session_id: 'conv', run_id: 'run_1', revision: 3,
        last_status: 'awaiting_user', last_answer: 'waiting',
        pending: { id: 'q1', kind: 'ask_user', questionnaire: {
          id: 'q1', questions: [{ id: 'city', type: 'text', question: '城市？', options: [], required: true }],
        } },
      }
      ;(transport.readAgentState as any).mockResolvedValue(
        'piagent-state:v1:gzip-base64:' + gzipSync(JSON.stringify(state)).toString('base64'),
      )
      ;(transport.listMessages as any).mockResolvedValue({
        records: [{ id: 'm1', query: 'ask me', answer: 'waiting', agent_thoughts: [] }],
        hasMore: false, firstId: 'm1',
      })
      const controller = new DifyController(config)
      await controller.loadConversation('conv')
      expect(controller.view.terminal?.status).toBe('awaiting_user')
      expect(controller.view.entries.find((entry) => entry.kind === 'question')).toMatchObject({
        pendingId: 'q1', status: 'waiting',
      })
      expect(transport.streamChat).not.toHaveBeenCalled()
    } finally {
      globalThis.Blob = blob
    }
  })

  it('restores every answer from text-only history', async () => {
    ;(transport.listMessages as any).mockResolvedValue({
      records: [
        { id: 'm1', query: 'q1', answer: 'a1', created_at: 1 },
        { id: 'm2', query: 'q2', answer: 'a2', created_at: 2 },
      ],
      hasMore: false,
      firstId: 'm1',
    })
    const controller = new DifyController(config)
    await controller.loadConversation('conv')
    expect(controller.view.entries.filter(
      (entry) => entry.kind === 'message' && entry.role === 'assistant',
    ).map((entry: any) => entry.text)).toEqual(['a1', 'a2'])
  })

  it('does not reuse a previous terminal if a new request ends before run.start', async () => {
    const controller = new DifyController(config)
    mockStream([
      { event: 'agent_log', data: { piagent: piEvent('run.state', 1, { status: 'completed', answer: 'old' }) } },
    ])
    await controller.send('old request')
    mockStream([{ event: 'message', answer: 'new partial' }])
    await controller.send('new request')
    expect(controller.view.terminal?.status).toBe('unknown')
    expect(controller.view.terminal?.answer).not.toBe('old')
  })

  it('projects agent logs, merges the Dify final answer and keeps one assistant message', async () => {
    mockStream([
      { event: 'message', answer: 'Hello', task_id: 'task_1', conversation_id: 'conv_1' },
      { event: 'agent_log', data: { piagent: piEvent('message.user', 0, { text: 'hi', message_id: 'u1' }) } },
      { event: 'agent_log', data: { piagent: piEvent('message.start', 1, { message_id: 'a1' }) } },
      { event: 'agent_log', data: { piagent: piEvent('message.delta', 2, { message_id: 'a1', delta: 'Hello' }) } },
      { event: 'agent_log', data: { piagent: piEvent('message.end', 3, { message_id: 'a1', text: 'Hello' }) } },
      { event: 'agent_log', data: { piagent: piEvent('run.state', 4, { status: 'completed', answer: 'Hello' }) } },
      { event: 'agent_log', data: { piagent: piEvent('run.done', 5, { status: 'completed' }) } },
      { event: 'message_end', conversation_id: 'conv_1' },
    ])
    const controller = new DifyController(config)
    await controller.send('hi')
    const assistants = controller.view.entries.filter(
      (entry) => entry.kind === 'message' && entry.role === 'assistant',
    )
    expect(assistants).toHaveLength(1)
    expect((assistants[0] as any).text).toBe('Hello')
    expect((assistants[0] as any).platformConfirmed).toBe(true)
    expect(controller.view.terminal?.status).toBe('completed')
    expect(controller.ui.running).toBe(false)
    expect(controller.ui.conversationId).toBe('conv_1')
  })

  it('discards stale history responses after switching conversations', async () => {
    let resolveA: (value: any) => void = () => {}
    let resolveB: (value: any) => void = () => {}
    const pageA = new Promise((resolve) => {
      resolveA = resolve
    })
    const pageB = new Promise((resolve) => {
      resolveB = resolve
    })
    ;(transport.listMessages as any).mockImplementation((_config: unknown, id: string) =>
      id === 'a' ? pageA : pageB,
    )
    const controller = new DifyController(config)
    const first = controller.loadConversation('a')
    const second = controller.loadConversation('b')
    resolveB({
      records: [{ id: 'mb', query: 'from B', answer: 'answer B' }],
      hasMore: false,
      firstId: 'mb',
    })
    await second
    resolveA({
      records: [{ id: 'ma', query: 'from A', answer: 'answer A' }],
      hasMore: false,
      firstId: 'ma',
    })
    await first
    const user = controller.view.entries.find(
      (entry) => entry.kind === 'message' && entry.role === 'user',
    ) as any
    expect(user.text).toBe('from B')
    expect(controller.ui.conversationId).toBe('b')
  })

  it('marks stop as best effort and calls the Dify stop endpoint', async () => {
    ;(transport.stopChat as any).mockResolvedValue(undefined)
    ;(transport.streamChat as any).mockImplementation(({ signal }: any) => ({
      events: (async function* () {
        yield { event: 'message', task_id: 'task_9', answer: 'partial' }
        await new Promise((resolve, reject) => {
          const timer = setTimeout(resolve, 30)
          signal.addEventListener('abort', () => {
            clearTimeout(timer)
            reject(new DOMException('aborted', 'AbortError'))
          })
        })
      })(),
    }))
    const controller = new DifyController(config)
    const pending = controller.send('long request')
    await new Promise((resolve) => setTimeout(resolve, 5))
    await controller.stop()
    await pending
    expect(transport.stopChat).toHaveBeenCalledWith(expect.anything(), 'task_9')
    expect(controller.view.terminal?.status).toBe('unknown')
    expect(controller.view.terminal?.error?.code).toBe('stopped_unconfirmed')
  })

  it('records Dify output files for viewing and download', async () => {
    mockStream([
      { event: 'message', answer: 'done', task_id: 't', conversation_id: 'c' },
      { event: 'message_file', id: 'f1', filename: 'report.pdf', url: 'https://files.test/report.pdf' },
      { event: 'message_end' },
    ])
    const controller = new DifyController(config)
    await controller.send('hi')
    expect(controller.view.outputs).toHaveLength(1)
    expect(controller.view.outputs[0].name).toBe('report.pdf')
    expect(controller.view.outputs[0].url).toContain('report.pdf')
  })

  it('does not resend when the stream ends without a terminal state', async () => {
    mockStream([{ event: 'message', answer: 'partial' }])
    const controller = new DifyController(config)
    await controller.send('hi')
    expect(transport.streamChat).toHaveBeenCalledTimes(1)
    expect(controller.view.terminal?.status).toBe('unknown')
    expect(controller.view.entries.some((entry) => entry.kind === 'note')).toBe(true)
  })

  it('ignores unsupported display versions but keeps Dify text', async () => {
    mockStream([
      {
        event: 'agent_log',
        data: { piagent: { ...piEvent('message.delta', 0), schema_version: 99, delta: 'future' } },
      },
      { event: 'message', answer: 'Dify text', task_id: 't', conversation_id: 'c' },
      { event: 'message_end' },
    ])
    const controller = new DifyController(config)
    await controller.send('hi')
    expect(controller.view.warnings.join(' ')).toContain('不受支持')
    expect(controller.view.entries.some((entry) => entry.kind === 'message' && (entry as any).text === 'Dify text')).toBe(true)
  })
})

describe('DifyController 会话管理（重命名/删除/列表）', () => {
  beforeEach(() => {
    ;(transport.renameConversation as any).mockReset()
    ;(transport.deleteConversation as any).mockReset()
  })

  function withConversations(items: Array<Record<string, unknown>>) {
    ;(transport.listConversations as any).mockResolvedValue(items)
  }

  it('重命名成功：列表条目即时更新并随后刷新列表', async () => {
    ;(transport.listConversations as any)
      .mockResolvedValueOnce([
        { id: 'conv_1', name: '旧名字', updated_at: 100 },
        { id: 'conv_2', name: '另一个', updated_at: 90 },
      ])
      .mockResolvedValueOnce([
        { id: 'conv_1', name: '新名字', updated_at: 120 },
        { id: 'conv_2', name: '另一个', updated_at: 90 },
      ])
    ;(transport.renameConversation as any).mockResolvedValue({ id: 'conv_1', name: '新名字' })
    const controller = new DifyController(config)
    await controller.refreshConversations()
    const ok = await controller.renameConversation('conv_1', ' 新名字 ')
    expect(ok).toBe(true)
    expect(transport.renameConversation).toHaveBeenCalledWith(expect.anything(), 'conv_1', '新名字')
    expect(controller.ui.conversations.find((item) => item.id === 'conv_1')?.name).toBe('新名字')
    expect(controller.ui.actionNote).toBe('')
    expect(transport.listConversations).toHaveBeenCalledTimes(2)
  })

  it('重命名失败：兜底提示写入 actionNote，列表保持原样', async () => {
    withConversations([{ id: 'conv_1', name: '旧名字', updated_at: 100 }])
    ;(transport.renameConversation as any).mockRejectedValue(new Error('Permission Denied'))
    const controller = new DifyController(config)
    await controller.refreshConversations()
    const ok = await controller.renameConversation('conv_1', '新名字')
    expect(ok).toBe(false)
    expect(controller.ui.actionNote).toContain('重命名失败')
    expect(controller.ui.actionNote).toContain('Permission Denied')
    expect(controller.ui.conversations.find((item) => item.id === 'conv_1')?.name).toBe('旧名字')
  })

  it('空名字不发起重命名请求', async () => {
    const controller = new DifyController(config)
    expect(await controller.renameConversation('conv_1', '   ')).toBe(false)
    expect(transport.renameConversation).not.toHaveBeenCalled()
  })

  it('删除成功：条目移除并刷新列表', async () => {
    ;(transport.listConversations as any)
      .mockResolvedValueOnce([
        { id: 'conv_1', name: 'A', updated_at: 100 },
        { id: 'conv_2', name: 'B', updated_at: 90 },
      ])
      .mockResolvedValueOnce([{ id: 'conv_2', name: 'B', updated_at: 90 }])
    ;(transport.deleteConversation as any).mockResolvedValue(undefined)
    const controller = new DifyController(config)
    await controller.refreshConversations()
    const ok = await controller.deleteConversation('conv_1')
    expect(ok).toBe(true)
    expect(transport.deleteConversation).toHaveBeenCalledWith(expect.anything(), 'conv_1')
    expect(controller.ui.conversations.map((item) => item.id)).toEqual(['conv_2'])
    expect(controller.ui.actionNote).toBe('')
    expect(transport.listConversations).toHaveBeenCalledTimes(2)
  })

  it('删除当前会话：回到新会话状态，且陈旧流结果被丢弃', async () => {
    ;(transport.listConversations as any).mockResolvedValue([])
    ;(transport.deleteConversation as any).mockResolvedValue(undefined)
    let releaseStream: (() => void) | null = null
    ;(transport.streamChat as any).mockImplementation(() => ({
      events: (async function* () {
        await new Promise<void>((resolve) => {
          releaseStream = resolve
        })
        yield { event: 'message', answer: '迟到的回答', conversation_id: 'conv_1' }
        yield { event: 'message_end' }
      })(),
    }))
    const controller = new DifyController(config)
    controller.ui.conversations = [{ id: 'conv_1', name: 'A', updatedAt: 100 }]
    controller.ui.conversationId = 'conv_1'
    const pending = controller.send('问题')
    await new Promise((resolve) => setTimeout(resolve, 5))
    const ok = await controller.deleteConversation('conv_1')
    expect(ok).toBe(true)
    expect(controller.ui.conversationId).toBe('')
    expect(controller.view.entries).toHaveLength(0)
    releaseStream?.()
    await pending
    // 陈旧票据：删除后迟到的流事件不得进入视图
    expect(controller.view.entries).toHaveLength(0)
    expect(controller.ui.running).toBe(false)
  })

  it('删除失败：兜底提示写入 actionNote', async () => {
    ;(transport.deleteConversation as any).mockRejectedValue(new Error('Server Error'))
    const controller = new DifyController(config)
    const ok = await controller.deleteConversation('conv_1')
    expect(ok).toBe(false)
    expect(controller.ui.actionNote).toContain('删除失败')
    expect(controller.ui.actionNote).toContain('Server Error')
  })

  it('列表加载失败：conversationsError 记录错误，成功后清除', async () => {
    ;(transport.listConversations as any).mockRejectedValueOnce(new Error('Unauthorized'))
      .mockResolvedValueOnce([{ id: 'conv_1', name: 'A', updated_at: 1 }])
    const controller = new DifyController(config)
    await controller.refreshConversations()
    expect(controller.ui.conversationsError).toContain('Unauthorized')
    await controller.refreshConversations()
    expect(controller.ui.conversationsError).toBe('')
    expect(controller.ui.conversations.map((item) => item.id)).toEqual(['conv_1'])
  })
})
