import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  deleteConversation,
  listConversations,
  listMessages,
  renameConversation,
  stopChat,
  streamChat,
  uploadFile,
} from './difyTransport'

function streamFromLines(lines: string[]) {
  const encoder = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) {
        controller.enqueue(encoder.encode(line))
      }
      controller.close()
    },
  })
}

describe('difyTransport', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    fetchMock.mockReset()
  })

  it('posts streaming chat requests with the expected payload', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: streamFromLines(['data: {"event":"message","answer":"hello"}\n\n']),
    })

    const result = await streamChat({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      query: 'hello',
      inputs: {
        state_id: '1',
        token: 'tenant-token',
        user_id: 'employee-42',
        user_prompt_response: {
          promptId: 'call_1',
          answer: 'Continue',
        },
      },
    })

    const [, requestInit] = fetchMock.mock.calls[0]
    const body = JSON.parse(String(requestInit.body))

    expect(body).toMatchObject({
      query: 'hello',
      response_mode: 'streaming',
      user: 'tester',
      conversation_id: 'conv_1',
      files: [],
      inputs: {
        state_id: '1',
        token: 'tenant-token',
        user_id: 'employee-42',
        user_prompt_response: {
          promptId: 'call_1',
          answer: 'Continue',
        },
      },
    })

    const events: any[] = []
    for await (const event of result.events) {
      events.push(event)
    }
    expect(events).toEqual([{ event: 'message', answer: 'hello' }])
  })

  it('loads Dify conversations for the configured user', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 2,
        has_more: true,
        data: [
          {
            id: 'conv_1',
            name: 'First chat',
            status: 'normal',
            introduction: '',
            created_at: 100,
            updated_at: 200,
          },
        ],
      }),
    })

    const conversations = await listConversations({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      lastId: 'conv_0',
      limit: 2,
      sortBy: '-updated_at',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost/v1/conversations?user=tester&limit=2&last_id=conv_0&sort_by=-updated_at',
      expect.objectContaining({
        method: 'GET',
        headers: { Authorization: 'Bearer app-test' },
      }),
    )
    expect(conversations).toEqual({
      hasMore: true,
      lastId: 'conv_1',
      conversations: [
        expect.objectContaining({
          id: 'conv_1',
          name: 'First chat',
          updatedAt: 200,
        }),
      ],
    })
  })

  it('renames and deletes conversations with the configured user', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'conv_1',
          name: 'Renamed',
          status: 'normal',
          created_at: 100,
          updated_at: 300,
        }),
      })
      .mockResolvedValueOnce({ ok: true })

    const renamed = await renameConversation({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      name: 'Renamed',
    })
    await deleteConversation({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
    })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://localhost/v1/conversations/conv_1/name',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ user: 'tester', name: 'Renamed', auto_generate: false }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://localhost/v1/conversations/conv_1',
      expect.objectContaining({
        method: 'DELETE',
        body: JSON.stringify({ user: 'tester' }),
      }),
    )
    expect(renamed).toMatchObject({ id: 'conv_1', name: 'Renamed', updatedAt: 300 })
  })

  it('posts chat files using Dify local_file payload shape', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: streamFromLines(['data: {"event":"message","answer":"hello"}\n\n']),
    })

    await streamChat({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: '',
      query: 'summarize this',
      inputs: {},
      files: [
        { id: 'upload_1', type: 'document', name: 'brief.pdf' },
        { id: 'upload_2', type: 'image', name: 'chart.png' },
      ],
    })

    const [, requestInit] = fetchMock.mock.calls[0]
    const body = JSON.parse(String(requestInit.body))

    expect(body.files).toEqual([
      { type: 'document', transfer_method: 'local_file', upload_file_id: 'upload_1' },
      { type: 'image', transfer_method: 'local_file', upload_file_id: 'upload_2' },
    ])
  })

  it('uploads files to Dify and returns normalized metadata', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'upload_1', name: 'notes.md', size: 12, mime_type: 'text/markdown' }),
    })

    const file = new File(['hello'], 'notes.md', { type: 'text/markdown' })
    const uploaded = await uploadFile({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      file,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost/v1/files/upload',
      expect.objectContaining({
        method: 'POST',
        headers: { Authorization: 'Bearer app-test' },
        body: expect.any(FormData),
      }),
    )
    expect(uploaded).toMatchObject({
      id: 'upload_1',
      name: 'notes.md',
      type: 'document',
      mimeType: 'text/markdown',
      size: 12,
    })
  })

  it('posts stop requests to the Dify stop endpoint', async () => {
    fetchMock.mockResolvedValue({ ok: true })

    await stopChat({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      taskId: 'task_1',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost/v1/chat-messages/task_1/stop',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer app-test',
        }),
        body: JSON.stringify({ user: 'tester' }),
      }),
    )
  })

  it('loads conversation history and maps Dify records to chat messages in chronological order', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 2,
        has_more: true,
        data: [
          {
            id: 'msg_2',
            query: 'second question',
            answer: 'second answer',
            created_at: 200,
            message_files: [],
          },
          {
            id: 'msg_1',
            query: 'first question',
            answer: 'first answer',
            created_at: 100,
            message_files: [
              { id: 'file_1', name: 'brief.pdf', type: 'document', mime_type: 'application/pdf', size: 123 },
            ],
          },
        ],
      }),
    })

    const history = await listMessages({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      limit: 2,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost/v1/messages?conversation_id=conv_1&user=tester&limit=2',
      expect.objectContaining({
        method: 'GET',
        headers: { Authorization: 'Bearer app-test' },
      }),
    )
    expect(history.hasMore).toBe(true)
    expect(history.firstId).toBe('msg_1')
    expect(history.messages.map((message: any) => [message.role, message.content])).toEqual([
      ['user', 'first question'],
      ['activity', expect.any(Object)],
      ['assistant', 'first answer'],
      ['user', 'second question'],
      ['assistant', 'second answer'],
    ])
    expect((history.messages[0] as any).files).toEqual([
      expect.objectContaining({
        id: 'file_1',
        name: 'brief.pdf',
        type: 'document',
        mimeType: 'application/pdf',
        size: 123,
      }),
    ])
    expect(history.messages[1]).toMatchObject({
      id: 'history:msg_1:uploaded-files',
      role: 'activity',
      activityType: 'cc_agent.uploaded_files',
      content: {
        source: 'history',
        files: [
          expect.objectContaining({
            id: 'file_1',
            name: 'brief.pdf',
            type: 'document',
            mimeType: 'application/pdf',
            size: 123,
          }),
        ],
      },
    })
  })

  it('keeps Dify history chronological when the API already returns oldest records first', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 2,
        has_more: false,
        data: [
          {
            id: 'msg_1',
            query: 'first question',
            answer: 'first answer',
            created_at: 100,
            message_files: [],
          },
          {
            id: 'msg_2',
            query: 'second question',
            answer: 'second answer',
            created_at: 200,
            message_files: [],
          },
        ],
      }),
    })

    const history = await listMessages({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      limit: 2,
    })

    expect(history.firstId).toBe('msg_1')
    expect(history.messages.map((message: any) => [message.role, message.content])).toEqual([
      ['user', 'first question'],
      ['assistant', 'first answer'],
      ['user', 'second question'],
      ['assistant', 'second answer'],
    ])
  })

  it('restores only query and native Dify answer while ignoring AG-UI history thoughts', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 1,
        has_more: false,
        data: [
          {
            id: 'msg_agui',
            query: 'what time is it?',
            answer: 'It is Saturday.',
            created_at: 300,
            message_files: [],
            agent_thoughts: [
              { event: 'agent_log', data: { data: { type: 'RUN_STARTED', threadId: 'thread-1', runId: 'run-1' } } },
              { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_START', messageId: 'answer_1', role: 'assistant' } } },
              { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_CONTENT', messageId: 'answer_1', delta: 'It is Saturday.' } } },
              { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_END', messageId: 'answer_1' } } },
              { event: 'agent_log', data: { data: { type: 'TOOL_CALL_START', toolCallId: 'call_1', toolCallName: 'current_time' } } },
              { event: 'agent_log', data: { data: { type: 'TOOL_CALL_ARGS', toolCallId: 'call_1', delta: '{"timezone":"Asia/Shanghai"}' } } },
              { event: 'agent_log', data: { data: { type: 'TOOL_CALL_RESULT', toolCallId: 'call_1', content: '2026-06-06 12:00:00' } } },
              { event: 'agent_log', data: { data: { type: 'TOOL_CALL_END', toolCallId: 'call_1' } } },
              {
                event: 'agent_log',
                data: {
                  data: {
                    type: 'ACTIVITY_SNAPSHOT',
                    messageId: 'activity_1',
                    activityType: 'cc_agent.permission_decision',
                    content: { toolName: 'current_time', decision: 'allow_conversation' },
                  },
                },
              },
              { event: 'agent_log', data: { data: { type: 'RUN_FINISHED', result: { answer: 'It is Saturday.' } } } },
            ],
          },
        ],
      }),
    })

    const history = await listMessages({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      limit: 1,
    })

    expect(history.messages.map((message: any) => [message.role, message.content || ''])).toEqual([
      ['user', 'what time is it?'],
      ['assistant', 'It is Saturday.'],
    ])
    expect(history.messages.every((message) => String(message.id).startsWith('history:msg_agui:'))).toBe(true)
    expect(history.messages.filter((message) => message.role === 'assistant' && message.content === 'It is Saturday.')).toHaveLength(1)
  })

  it('shows a missing-answer notice instead of rebuilding text from AG-UI chunks', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 1,
        has_more: false,
        data: [
          {
            id: 'msg_empty_answer',
            query: 'summarize',
            answer: '',
            created_at: 400,
            message_files: [],
            agent_thoughts: [
              { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_CONTENT', messageId: 'answer_1', delta: 'summary ' } } },
              { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_CONTENT', messageId: 'answer_1', delta: 'done' } } },
            ],
          },
        ],
      }),
    })

    const history = await listMessages({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      limit: 1,
    })

    expect(history.messages.map((message: any) => [message.role, message.content])).toEqual([
      ['user', 'summarize'],
      ['assistant', '该历史轮次没有保存最终回复。'],
    ])
    expect(history.messages[1].id).toBe('history:msg_empty_answer:assistant:answer')
  })

  it('falls back to the cc_agent final-answer finish log when native Dify answer is empty', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 1,
        has_more: false,
        data: [
          {
            id: 'msg_finish_log',
            query: '今天星期几？',
            answer: '',
            created_at: 410,
            message_files: [],
            agent_thoughts: [
              { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_CONTENT', delta: 'ignored chunk' } } },
              {
                label: 'Final answer',
                data: {
                  kind: 'cc_agent.final_answer',
                  answer: '今天是星期六。',
                  finish_reason: 'final',
                },
              },
            ],
          },
        ],
      }),
    })

    const history = await listMessages({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      limit: 1,
    })

    expect(history.messages.map((message: any) => [message.role, message.content])).toEqual([
      ['user', '今天星期几？'],
      ['assistant', '今天是星期六。'],
    ])
  })

  it('shows a missing-answer notice for Dify workflow answer placeholders', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 1,
        has_more: false,
        data: [
          {
            id: 'msg_placeholder_answer',
            query: '今天星期几',
            answer: '\n\n\n-----------------\ntoken:\n\nid:',
            created_at: 450,
            message_files: [],
            agent_thoughts: [
              { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_CONTENT', messageId: 'answer_1', delta: '今天是' } } },
              { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_CONTENT', messageId: 'answer_1', delta: '星期六。' } } },
            ],
          },
        ],
      }),
    })

    const history = await listMessages({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      limit: 1,
    })

    expect(history.messages.map((message: any) => [message.role, message.content])).toEqual([
      ['user', '今天星期几'],
      ['assistant', '该历史轮次没有保存最终回复。'],
    ])
  })

  it('does not restore native Dify tool traces in compact history mode', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 1,
        has_more: false,
        data: [
          {
            id: 'msg_native_trace',
            query: 'read file',
            answer: 'Read complete.',
            created_at: 500,
            message_files: [],
            agent_thoughts: [
              {
                id: 'thought_1',
                tool: 'read_file',
                tool_input: '{"url":"workspace://uploaded/PLAN.md"}',
                observation: 'File content preview',
              },
            ],
          },
        ],
      }),
    })

    const history = await listMessages({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      limit: 1,
    })

    expect(history.messages.map((message: any) => [message.role, message.content || ''])).toEqual([
      ['user', 'read file'],
      ['assistant', 'Read complete.'],
    ])
  })

  it('does not render Dify workflow answer placeholders as assistant content', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        limit: 1,
        has_more: false,
        data: [
          {
            id: 'msg_placeholder_only',
            query: '今天星期几',
            answer: 'token:\n\nid:',
            created_at: 550,
            message_files: [],
            agent_thoughts: [],
          },
        ],
      }),
    })

    const history = await listMessages({
      baseUrl: 'http://localhost/v1/',
      apiKey: 'app-test',
      user: 'tester',
      conversationId: 'conv_1',
      limit: 1,
    })

    expect(history.messages.map((message: any) => [message.role, message.content || ''])).toEqual([
      ['user', '今天星期几'],
      ['assistant', '该历史轮次没有保存最终回复。'],
    ])
  })
})
