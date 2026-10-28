import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DifyAgUiAgent } from './DifyAgUiAgent'
import * as transport from './difyTransport'
import { createConversationCoordinator, loadPendingHistory } from './conversationCoordinator'

function streamFromEvents(events: any[]) {
  const encoder = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))
      }
      controller.close()
    },
  })
}

describe('DifyAgUiAgent', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(transport, 'loadConversationRecovery').mockResolvedValue(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    fetchMock.mockReset()
  })

  it('resumes interrupts by sending the user response as the Dify query', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: streamFromEvents([
        {
          event: 'agent_log',
          data: {
            data: {
              type: 'RUN_FINISHED',
              result: { answer: 'done', executionMetadata: { finishReason: 'stop' } },
            },
          },
        },
      ]),
    })

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      token: 'tenant-token',
      inputs: {},
    })

    agent.addMessage({
      id: 'user_1',
      role: 'user',
      content: 'old user question',
    } as any)

    await agent.runAgent({
      forwardedProps: {
        command: {
          resume: {
            promptId: 'call_1',
            answer: 'Continue',
          },
          interruptEvent: {
            id: 'call_1',
          },
        },
      },
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, requestInit] = fetchMock.mock.calls[0]
    const body = JSON.parse(String(requestInit.body))
    expect(body.query).toBe('Continue')
    expect(body.inputs.token).toBe('tenant-token')
    expect(body.inputs.user_id).toBeUndefined()
    expect(body.inputs.user_prompt_response).toMatchObject({
      promptId: 'call_1',
      answer: 'Continue',
    })
    expect(body.inputs.state_id).toBeUndefined()
  })

  it('does not let an older A history response overwrite a newer A selection', async () => {
    const sessions = createConversationCoordinator(() => 'tester')
    sessions.select('a')
    const first = sessions.currentTicket()!
    const agent = new DifyAgUiAgent({ baseUrl: 'http://localhost/v1', apiKey: 'app-test', user: 'tester' }, 'default', undefined, {
      onConversationIdChange: sessions.conversationChanged,
    })
    agent.threadId = first.threadId
    let resolveOld!: (value: transport.DifyListMessagesResult) => void
    const oldResponse = new Promise<transport.DifyListMessagesResult>(resolve => { resolveOld = resolve })
    vi.spyOn(transport, 'listMessages').mockReturnValueOnce(oldResponse).mockResolvedValueOnce({
      messages: [{ id: 'new', role: 'assistant', content: 'new response' }], hasMore: false, firstId: 'new',
    })
    const oldLoad = loadPendingHistory(first, sessions.currentTicket, async () => agent)
    await Promise.resolve()
    sessions.select('b')
    sessions.select('a')
    const latest = sessions.currentTicket()!
    const current = await loadPendingHistory(latest, sessions.currentTicket, async () => agent)
    sessions.historyLoaded({ ...latest, result: current?.result })
    resolveOld({ messages: [{ id: 'old', role: 'assistant', content: 'old response' }], hasMore: false, firstId: 'old' })

    expect(await oldLoad).toBeNull()
    expect(agent.messages.map(message => message.content)).toEqual(['new response'])
  })

  it('does not mark a background history response as loaded after leaving its ticket', async () => {
    const sessions = createConversationCoordinator(() => 'tester')
    sessions.select('a')
    const ticket = sessions.currentTicket()!
    const agent = new DifyAgUiAgent({ baseUrl: 'http://localhost/v1', apiKey: 'app-test', user: 'tester' }, 'default', undefined, {
      onConversationIdChange: sessions.conversationChanged,
    })
    agent.threadId = ticket.threadId
    let resolve!: (value: transport.DifyListMessagesResult) => void
    vi.spyOn(transport, 'listMessages').mockReturnValueOnce(new Promise(value => { resolve = value }))
    const loading = loadPendingHistory(ticket, sessions.currentTicket, async () => agent)
    await Promise.resolve()
    sessions.select('b')
    resolve({ messages: [{ id: 'old', role: 'assistant', content: 'old response' }], hasMore: false, firstId: 'old' })

    expect(await loading).toBeNull()
    expect(agent.messages).toEqual([])
    sessions.select('a')
    expect(sessions.historyLoading.value).toBe(true)
  })

  it('keeps a late native start intact after closing a live fallback segment', async () => {
    const start = { type: 'RUN_STARTED', runId: 'native-run', threadId: 'native-thread', extension: { trace: 'keep' } }
    vi.spyOn(transport, 'streamChat').mockResolvedValue({
      response: { conversationId: '', taskId: '' },
      events: (async function* () {
        yield { event: 'message', answer: 'fallback prefix' }
        yield start
        yield { type: 'RUN_FINISHED', runId: 'native-run', threadId: 'native-thread', result: { answer: 'done' } }
      })(),
    })
    const events: any[] = []
    const agent = new DifyAgUiAgent({ baseUrl: 'http://localhost/v1', apiKey: 'app-test', user: 'tester' })
    agent.subscribe({ onEvent: ({ event }) => { events.push(event) } })
    agent.addMessage({ id: 'q', role: 'user', content: 'question' })

    await agent.runAgent()

    expect(events.filter(event => event.type === 'RUN_STARTED')[1]).toEqual(start)
    const nativeIndex = events.findIndex(event => event.type === 'RUN_STARTED' && event.runId === start.runId)
    expect(events[nativeIndex - 1].type).toBe('RUN_FINISHED')
  })

  it('restores a pending interaction while loading history and can resume its exact prompt', async () => {
    vi.spyOn(transport, 'listMessages').mockResolvedValue({ messages: [], hasMore: false, firstId: '' })
    vi.mocked(transport.loadConversationRecovery).mockResolvedValue({ revision: 7, runId: 'old',
      status: 'awaiting_user', question: { id: 'pending', question: 'Continue?', purpose: 'permission',
        options: [{ label: 'Allow', value: 'allow_once' }], fields: [], allowCustomInput: false, multiSelect: false } })
    const agent = new DifyAgUiAgent({ baseUrl: '/v1', apiKey: 'key', user: 'u' })
    await agent.loadHistory('conv')
    expect(agent.state.recovery).toMatchObject({ revision: 7, question: { id: 'pending' } })
    fetchMock.mockResolvedValue({ ok: true, body: streamFromEvents([
      { type: 'RUN_STARTED', runId: 'new', threadId: 'default' },
      { type: 'RUN_FINISHED', runId: 'new', threadId: 'default', result: { answer: 'done' } },
    ]) })
    agent.setMessages([{ id: 'answer', role: 'user', content: 'allow_once' }])
    await agent.runAgent()
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.inputs.user_prompt_response.promptId).toBe('pending')
    expect(agent.state.recovery).toBeNull()
  })

  it('keeps history available when recovery cannot be read', async () => {
    vi.spyOn(transport, 'listMessages').mockResolvedValue({ messages: [{ id: 'a', role: 'assistant', content: 'saved' }], hasMore: false, firstId: '' })
    vi.mocked(transport.loadConversationRecovery).mockRejectedValue(new Error('unavailable'))
    const agent = new DifyAgUiAgent({ baseUrl: '/v1', apiKey: 'key', user: 'u' })
    await agent.loadHistory('conv')
    expect(agent.messages[0].content).toBe('saved')
    expect(agent.state.recoveryAvailable).toBe(false)
  })

  it('does not let a late recovery response overwrite the latest selection of the same conversation', async () => {
    vi.spyOn(transport, 'listMessages').mockResolvedValue({ messages: [], hasMore: false, firstId: '' })
    let older!: (value: any) => void
    let newer!: (value: any) => void
    vi.mocked(transport.loadConversationRecovery)
      .mockImplementationOnce(() => new Promise(resolve => { older = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { newer = resolve }))
    const agent = new DifyAgUiAgent({ baseUrl: '/v1', apiKey: 'key', user: 'u' })
    const first = agent.loadHistory('conv')
    const second = agent.loadHistory('conv')
    newer({ revision: 8, runId: 'new', status: 'completed', question: null })
    await second
    older({ revision: 7, runId: 'old', status: 'completed', question: null })
    expect(await first).toMatchObject({ loaded: false })
    expect(agent.state.recovery.runId).toBe('new')
  })

  it('replaces inputs when config is updated from assistant props', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: streamFromEvents([{ event: 'message', answer: 'ok' }]),
    })

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      token: 'first-token',
      inputs: { tenantId: 'tenant-1', module: 'cadre' },
    })

    agent.updateConfig({
      token: 'second-token',
      inputs: { module: 'archive' },
    })
    agent.addMessage({ id: 'u1', role: 'user', content: 'hello' } as any)
    await agent.runAgent()

    const [, requestInit] = fetchMock.mock.calls[0]
    const body = JSON.parse(String(requestInit.body))
    expect(body.inputs).toEqual({
      module: 'archive',
      token: 'second-token',
    })
  })

  it('passes native AG-UI events through without re-normalizing them', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: 'conv_1',
        taskId: 'task_1',
      },
      events: [
        { event: 'agent_log', data: { data: { type: 'RUN_STARTED', threadId: 'thread-1', runId: 'run-1' } } },
        { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' } } },
        { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'hello' } } },
        { event: 'agent_log', data: { data: { type: 'TEXT_MESSAGE_END', messageId: 'm1' } } },
        { event: 'agent_log', data: { data: { type: 'RUN_FINISHED', threadId: 'thread-1', runId: 'run-1', result: { answer: 'hello' } } } },
      ],
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const events: any[] = []
    agent.subscribe({
      onEvent: ({ event }: any) => {
        events.push(event)
      },
    } as any)

    agent.addMessage({ id: 'u1', role: 'user', content: 'hello' } as any)
    await agent.runAgent()

    expect(events.map(event => event.type)).toEqual([
      'RUN_STARTED',
      'TEXT_MESSAGE_START',
      'TEXT_MESSAGE_CONTENT',
      'TEXT_MESSAGE_END',
      'RUN_FINISHED',
    ])
  })

  it('emits skill artifact activity for Dify blob chunks inside native AG-UI streams', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: 'conv_1',
        taskId: 'task_1',
      },
      events: [
        { event: 'agent_log', data: { data: { type: 'RUN_STARTED', threadId: 'thread-1', runId: 'run-1' } } },
        {
          type: 'blob_chunk',
          message: {
            id: 'blob_1',
            sequence: 0,
            total_length: 6,
            blob: 'cmVw',
            end: false,
          },
          meta: {
            filename: 'report.md',
            mime_type: 'text/markdown',
          },
        },
        {
          type: 'blob_chunk',
          message: {
            id: 'blob_1',
            sequence: 1,
            total_length: 6,
            blob: 'b3J0',
            end: false,
          },
          meta: {
            filename: 'report.md',
            mime_type: 'text/markdown',
          },
        },
        {
          type: 'blob_chunk',
          message: {
            id: 'blob_1',
            sequence: 2,
            total_length: 6,
            blob: '',
            end: true,
          },
          meta: {
            filename: 'report.md',
            mime_type: 'text/markdown',
          },
        },
        { event: 'agent_log', data: { data: { type: 'RUN_FINISHED', threadId: 'thread-1', runId: 'run-1', result: { answer: 'done' } } } },
      ],
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const events: any[] = []
    agent.subscribe({
      onEvent: ({ event }: any) => {
        events.push(event)
      },
    } as any)

    agent.addMessage({ id: 'u1', role: 'user', content: 'build report' } as any)
    await agent.runAgent()

    expect(events.map(event => event.type)).toEqual([
      'RUN_STARTED',
      'ACTIVITY_SNAPSHOT',
      'RUN_FINISHED',
    ])
    expect(events[1]).toMatchObject({
      type: 'ACTIVITY_SNAPSHOT',
      activityType: 'cc_agent.skill_artifact',
      content: {
        files: [
          {
            id: 'blob_1',
            name: 'report.md',
            mime_type: 'text/markdown',
            size: 6,
            status: 'attached',
            download_data_url: 'data:text/markdown;base64,cmVwb3J0',
          },
        ],
      },
    })
  })

  it('does not synthesize RUN_STARTED for empty Dify metadata before native AG-UI starts', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: 'conv_1',
        taskId: 'task_1',
      },
      events: [
        { event: 'workflow_started', task_id: 'task_1', conversation_id: 'conv_1' },
        { event: 'agent_log', data: { data: { type: 'RUN_STARTED', threadId: 'thread-1', runId: 'run-1' } } },
        { event: 'agent_log', data: { data: { type: 'RUN_FINISHED', threadId: 'thread-1', runId: 'run-1', result: { answer: 'hello' } } } },
      ],
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const events: any[] = []
    agent.subscribe({
      onEvent: ({ event }: any) => {
        events.push(event)
      },
    } as any)

    agent.addMessage({ id: 'u1', role: 'user', content: 'hello' } as any)
    await agent.runAgent()

    expect(events.map(event => event.type)).toEqual([
      'RUN_STARTED',
      'RUN_FINISHED',
    ])
  })

  it('ignores legacy Dify message events after native AG-UI finishes', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: 'conv_1',
        taskId: 'task_1',
      },
      events: [
        { event: 'agent_log', data: { data: { type: 'RUN_STARTED', threadId: 'thread-1', runId: 'run-1' } } },
        { event: 'agent_log', data: { data: { type: 'RUN_FINISHED', threadId: 'thread-1', runId: 'run-1', result: { answer: 'done' } } } },
        { event: 'message', answer: 'late duplicate text', conversation_id: 'conv_1' },
      ],
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const events: any[] = []
    agent.subscribe({
      onEvent: ({ event }: any) => {
        events.push(event)
      },
    } as any)

    agent.addMessage({ id: 'u1', role: 'user', content: 'hello' } as any)
    await agent.runAgent()

    expect(events.map(event => event.type)).toEqual([
      'RUN_STARTED',
      'RUN_FINISHED',
    ])
  })

  it('emits an interrupt custom event when RUN_FINISHED carries interrupt outcome', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: streamFromEvents([
        {
          event: 'agent_log',
          data: {
            data: JSON.stringify({
              type: 'RUN_FINISHED',
              result: {
                answer: 'Which account?',
                executionMetadata: {
                  finishReason: 'awaiting_user',
                },
              },
              outcome: {
                type: 'interrupt',
                interrupts: [
                  {
                    id: 'call_1',
                    toolCallId: 'call_1',
                    message: 'Which account?',
                    metadata: {
                      purpose: 'clarification',
                      options: [{ label: 'A', value: 'a', description: '' }],
                      fields: [{ name: 'reason', label: 'Reason', type: 'textarea', required: true }],
                      allowCustomInput: true,
                      multiSelect: false,
                    },
                  },
                ],
              },
            }),
          },
        },
      ]),
    })

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      stateId: '1',
      user: 'tester',
      token: 'tenant-token',
      inputs: {},
    })

    const customEvents: any[] = []
    const finalized = vi.fn()

    agent.subscribe({
      onCustomEvent: ({ event }) => {
        customEvents.push(event)
      },
      onRunFinalized: finalized,
    })

    agent.addMessage({
      id: 'user_1',
      role: 'user',
      content: 'ask me a question',
    } as any)

    await agent.runAgent()

    expect(finalized).toHaveBeenCalled()
    expect(customEvents).toHaveLength(1)
    expect(customEvents[0]).toMatchObject({
      name: 'on_interrupt',
      value: {
        id: 'call_1',
        question: 'Which account?',
        purpose: 'clarification',
        options: [{ label: 'A', value: 'a', description: '' }],
        fields: [{ name: 'reason', label: 'Reason', type: 'textarea', required: true }],
        allowCustomInput: true,
        multiSelect: false,
      },
    })
  })

  it('converts pending permission option text into an interrupt resume request', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        body: streamFromEvents([
          {
            event: 'agent_log',
            data: {
              data: JSON.stringify({
                type: 'RUN_FINISHED',
                result: {
                  answer: '允许执行这个操作吗？',
                  executionMetadata: {
                    finishReason: 'awaiting_user',
                  },
                },
                outcome: {
                  type: 'interrupt',
                  interrupts: [
                    {
                      id: 'call_1',
                      toolCallId: 'call_1',
                      message: '允许执行这个操作吗？',
                      metadata: {
                        purpose: 'permission',
                        options: [
                          { label: '允许一次', value: 'allow_once' },
                          { label: '当前会话始终允许', value: 'allow_conversation' },
                          { label: '拒绝', value: 'deny' },
                        ],
                        allowCustomInput: false,
                        multiSelect: false,
                      },
                    },
                  ],
                },
              }),
            },
          },
        ]),
      })
      .mockResolvedValueOnce({
        ok: true,
        body: streamFromEvents([
          {
            event: 'agent_log',
            data: {
              data: {
                type: 'RUN_FINISHED',
                result: { answer: 'done', executionMetadata: { finishReason: 'stop' } },
              },
            },
          },
        ]),
      })

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })

    agent.addMessage({ id: 'u1', role: 'user', content: '今天星期几' } as any)
    await agent.runAgent()
    agent.addMessage({ id: 'u2', role: 'user', content: '当前会话始终允许' } as any)
    await agent.runAgent()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [, secondRequestInit] = fetchMock.mock.calls[1]
    const body = JSON.parse(String(secondRequestInit.body))
    expect(body.query).toBe('当前会话始终允许')
    expect(body.inputs.user_prompt_response).toMatchObject({
      promptId: 'call_1',
      purpose: 'permission',
      selectedValues: ['allow_conversation'],
      selectedLabels: ['当前会话始终允许'],
      answer: '当前会话始终允许',
    })
  })

  it('passes conversation id returned from one run into the next transport request', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy
      .mockResolvedValueOnce({
        response: {
          conversationId: 'conv_1',
          taskId: 'task_1',
        },
        events: streamFromEvents([
          { event: 'message', answer: 'hello' },
        ]),
      } as any)
      .mockResolvedValueOnce({
        response: {
          conversationId: 'conv_1',
          taskId: 'task_2',
        },
        events: streamFromEvents([
          { event: 'message', answer: 'world' },
        ]),
      } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      stateId: '1',
      user: 'tester',
      token: 'tenant-token',
      inputs: {},
    })

    agent.addMessage({ id: 'u1', role: 'user', content: 'first' } as any)
    await agent.runAgent()
    agent.addMessage({ id: 'u2', role: 'user', content: 'second' } as any)
    await agent.runAgent()

    expect(streamChatSpy).toHaveBeenNthCalledWith(1, expect.objectContaining({
      conversationId: '',
      query: 'first',
      inputs: expect.objectContaining({
        token: 'tenant-token',
      }),
    }))
    expect(streamChatSpy).toHaveBeenNthCalledWith(2, expect.objectContaining({
      conversationId: 'conv_1',
      query: 'second',
    }))
  })

  it('uses conversation id from AG-UI final state ref when transport response omits it', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy
      .mockResolvedValueOnce({
        response: {
          conversationId: '',
          taskId: 'task_1',
        },
        events: [
          { event: 'agent_log', data: { data: { type: 'RUN_STARTED', threadId: 'thread-1', runId: 'run-1' } } },
          {
            event: 'agent_log',
            data: {
              data: {
                type: 'RUN_FINISHED',
                threadId: 'thread-1',
                runId: 'run-1',
                result: {
                  answer: 'hello',
                  state_ref: { conversation_id: 'conv_state' },
                },
              },
            },
          },
        ],
      } as any)
      .mockResolvedValueOnce({
        response: {
          conversationId: '',
          taskId: 'task_2',
        },
        events: [
          { event: 'agent_log', data: { data: { type: 'RUN_STARTED', threadId: 'thread-1', runId: 'run-2' } } },
          { event: 'agent_log', data: { data: { type: 'RUN_FINISHED', threadId: 'thread-1', runId: 'run-2', result: { answer: 'world' } } } },
        ],
      } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })

    agent.addMessage({ id: 'u1', role: 'user', content: 'first' } as any)
    await agent.runAgent()
    agent.addMessage({ id: 'u2', role: 'user', content: 'second' } as any)
    await agent.runAgent()

    expect(streamChatSpy).toHaveBeenNthCalledWith(2, expect.objectContaining({
      conversationId: 'conv_state',
      query: 'second',
    }))
  })

  it('lets cloned agents use config updates made after cloning', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: '',
        taskId: '',
      },
      events: [
        { event: 'message', answer: 'ok' },
      ],
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      stateId: '1',
      user: 'tester',
      inputs: {},
    })
    const cloned = agent.clone()

    agent.updateConfig({
      baseUrl: 'https://remote.example/v1',
    })

    cloned.addMessage({ id: 'u1', role: 'user', content: 'hello' } as any)
    await cloned.runAgent()

    expect(streamChatSpy).toHaveBeenCalledWith(expect.objectContaining({
      baseUrl: 'https://remote.example/v1',
    }))
  })

  it('forwards files attached to the latest user message', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: '',
        taskId: '',
      },
      events: [
        { event: 'message', answer: 'ok' },
      ],
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      stateId: '1',
      user: 'tester',
      inputs: {},
    })

    agent.addMessage({
      id: 'u1',
      role: 'user',
      content: 'summarize',
      files: [{ id: 'upload_1', type: 'document', name: 'brief.pdf' }],
    } as any)
    await agent.runAgent()

    expect(streamChatSpy).toHaveBeenCalledWith(expect.objectContaining({
      query: expect.stringContaining('summarize'),
      files: [{ id: 'upload_1', type: 'document', name: 'brief.pdf' }],
    }))
  })

  it('emits uploaded files activity after synthesized RUN_STARTED for legacy Dify streams', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: '',
        taskId: '',
      },
      events: [
        { event: 'message', answer: 'ok' },
      ],
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const events: any[] = []
    agent.subscribe({
      onEvent: ({ event }: any) => {
        events.push(event)
      },
    } as any)

    agent.addMessage({
      id: 'u1',
      role: 'user',
      content: 'summarize',
      files: [{ id: 'upload_1', type: 'document', name: 'brief.pdf', size: 123 }],
    } as any)
    await agent.runAgent()

    expect(events.slice(0, 2)).toMatchObject([
      { type: 'RUN_STARTED' },
      {
        type: 'ACTIVITY_SNAPSHOT',
        activityType: 'cc_agent.uploaded_files',
        content: {
          source: 'user_message',
          files: [{ id: 'upload_1', type: 'document', name: 'brief.pdf', size: 123 }],
        },
      },
    ])
  })

  it('emits uploaded files activity after native RUN_STARTED without duplicating RUN_STARTED', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: 'conv_1',
        taskId: 'task_1',
      },
      events: [
        { event: 'agent_log', data: { data: { type: 'RUN_STARTED', threadId: 'thread-1', runId: 'run-1' } } },
        { event: 'agent_log', data: { data: { type: 'RUN_FINISHED', threadId: 'thread-1', runId: 'run-1', result: { answer: 'done' } } } },
      ],
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const events: any[] = []
    agent.subscribe({
      onEvent: ({ event }: any) => {
        events.push(event)
      },
    } as any)

    agent.addMessage({
      id: 'u1',
      role: 'user',
      content: 'summarize',
      files: [{ id: 'upload_1', type: 'document', name: 'brief.pdf' }],
    } as any)
    await agent.runAgent()

    expect(events.map(event => event.type)).toEqual([
      'RUN_STARTED',
      'ACTIVITY_SNAPSHOT',
      'RUN_FINISHED',
    ])
    expect(events[1]).toMatchObject({
      activityType: 'cc_agent.uploaded_files',
      content: {
        source: 'user_message',
        files: [{ id: 'upload_1', type: 'document', name: 'brief.pdf' }],
      },
    })
  })

  it('does not emit uploaded files activity for interrupt resume runs', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: '',
        taskId: '',
      },
      events: streamFromEvents([
        { event: 'message', answer: 'ok' },
      ]),
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const events: any[] = []
    agent.subscribe({
      onEvent: ({ event }: any) => {
        events.push(event)
      },
    } as any)

    agent.addMessage({
      id: 'u1',
      role: 'user',
      content: 'summarize',
      files: [{ id: 'upload_1', type: 'document', name: 'brief.pdf' }],
    } as any)
    await agent.runAgent({
      forwardedProps: {
        command: {
          resume: {
            promptId: 'call_1',
            answer: 'Continue',
          },
        },
      },
    })

    expect(events.some(event => event.type === 'ACTIVITY_SNAPSHOT' && event.activityType === 'cc_agent.uploaded_files')).toBe(false)
  })

  it('forwards files from CopilotKit multimodal attachment content', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: '',
        taskId: '',
      },
      events: streamFromEvents([
        { event: 'message', answer: 'ok' },
      ]),
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      stateId: '1',
      user: 'tester',
      inputs: {},
    })

    agent.addMessage({
      id: 'u1',
      role: 'user',
      content: [
        { type: 'text', text: 'summarize this file' },
        {
          type: 'document',
          source: { type: 'url', value: 'dify-file://upload_1', mimeType: 'application/pdf' },
          metadata: {
            filename: 'brief.pdf',
            difyUploadedFile: {
              id: 'upload_1',
              type: 'document',
              name: 'brief.pdf',
              mimeType: 'application/pdf',
              size: 123,
            },
          },
        },
      ],
    } as any)
    await agent.runAgent()

    expect(streamChatSpy).toHaveBeenCalledWith(expect.objectContaining({
      query: expect.stringContaining('summarize this file'),
      files: [{
        id: 'upload_1',
        type: 'document',
        name: 'brief.pdf',
        mimeType: 'application/pdf',
        size: 123,
      }],
    }))
  })

  it('sanitizes non-cloneable message attachment metadata before running', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: '',
        taskId: '',
      },
      events: streamFromEvents([
        { event: 'message', answer: 'ok' },
      ]),
    } as any)
    const uploadedProxy = new Proxy({
      id: 'upload_1',
      type: 'document',
      name: 'brief.pdf',
      mimeType: 'application/pdf',
      size: 123,
    }, {})

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })

    agent.addMessage({
      id: 'u1',
      role: 'user',
      content: [
        { type: 'text', text: 'summarize this file' },
        {
          type: 'document',
          source: { type: 'url', value: 'dify-file://upload_1', mimeType: 'application/pdf' },
          metadata: {
            filename: 'brief.pdf',
            difyUploadedFile: uploadedProxy,
          },
        },
      ],
    } as any)

    await expect(agent.runAgent()).resolves.toBeDefined()
    expect(streamChatSpy).toHaveBeenCalledWith(expect.objectContaining({
      query: 'summarize this file',
      files: [{ id: 'upload_1', type: 'document', name: 'brief.pdf', mimeType: 'application/pdf', size: 123 }],
    }))
  })

  it('loads history into messages and continues the same Dify conversation', async () => {
    const listMessagesSpy = vi.spyOn(transport, 'listMessages')
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    listMessagesSpy.mockResolvedValue({
      messages: [
        { id: 'history:user:msg_1', role: 'user', content: 'old question' },
        { id: 'history:assistant:msg_1', role: 'assistant', content: 'old answer' },
      ],
      hasMore: false,
      firstId: 'msg_1',
    } as any)
    streamChatSpy.mockResolvedValue({
      response: {
        conversationId: 'conv_1',
        taskId: 'task_2',
      },
      events: streamFromEvents([
        { event: 'message', answer: 'new answer' },
      ]),
    } as any)

    const onConversationIdChange = vi.fn()
    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      stateId: '1',
      user: 'tester',
      inputs: {},
    }, 'default', undefined, { onConversationIdChange })

    await agent.loadHistory('conv_1')
    agent.addMessage({ id: 'u2', role: 'user', content: 'new question' } as any)
    await agent.runAgent()

    expect(listMessagesSpy).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 'conv_1',
      user: 'tester',
    }))
    expect(agent.messages.slice(0, 2)).toEqual([
      expect.objectContaining({ role: 'user', content: 'old question' }),
      expect.objectContaining({ role: 'assistant', content: 'old answer' }),
    ])
    expect(streamChatSpy).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 'conv_1',
      query: 'new question',
    }))
    expect(onConversationIdChange).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 'conv_1',
      threadId: expect.any(String),
    }))
  })

  it('starts a new conversation by clearing local messages and conversation state', () => {
    const onConversationIdChange = vi.fn()
    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    }, 'default', undefined, { onConversationIdChange })

    agent.setConversationId('conv_1')
    agent.addMessage({ id: 'u1', role: 'user', content: 'old' } as any)
    agent.startNewConversation()

    expect(agent.getConversationId()).toBe('')
    expect(agent.messages).toEqual([])
    expect(onConversationIdChange).toHaveBeenLastCalledWith(expect.objectContaining({
      conversationId: '',
      threadId: expect.any(String),
    }))
  })

  it('reports run status changes for the running thread', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: streamFromEvents([
        { event: 'message', answer: 'done', conversation_id: 'conv_1' },
      ]),
    })
    const onRunStatusChange = vi.fn()
    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    }, 'default', undefined, { onRunStatusChange })
    agent.threadId = 'thread-1'

    agent.addMessage({ id: 'u1', role: 'user', content: 'hello' } as any)
    await agent.runAgent()

    expect(onRunStatusChange).toHaveBeenNthCalledWith(1, {
      conversationId: '',
      threadId: 'thread-1',
      running: true,
    })
    expect(onRunStatusChange).toHaveBeenLastCalledWith({
      conversationId: 'conv_1',
      threadId: 'thread-1',
      running: false,
    })
  })

  it('selects a Dify conversation by loading its history', async () => {
    const listMessagesSpy = vi.spyOn(transport, 'listMessages')
    listMessagesSpy.mockResolvedValue({
      messages: [
        { id: 'history:user:msg_1', role: 'user', content: 'old question' },
      ],
      hasMore: false,
      firstId: 'msg_1',
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })

    const result = await agent.selectConversation('conv_1')

    expect(result.loaded).toBe(true)
    expect(agent.getConversationId()).toBe('conv_1')
    expect(agent.messages).toEqual([
      expect.objectContaining({ role: 'user', content: 'old question' }),
    ])
    expect(listMessagesSpy).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 'conv_1',
      user: 'tester',
    }))
  })

  it('notifies subscribers when history messages are loaded', async () => {
    const listMessagesSpy = vi.spyOn(transport, 'listMessages')
    listMessagesSpy.mockResolvedValue({
      messages: [
        { id: 'history:conv_1:user', role: 'user', content: 'old question' },
        { id: 'history:conv_1:assistant', role: 'assistant', content: 'old answer' },
      ],
      hasMore: false,
      firstId: 'msg_1',
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const onMessagesChanged = vi.fn()
    agent.subscribe({ onMessagesChanged })

    await agent.selectConversation('conv_1')

    expect(onMessagesChanged).toHaveBeenCalledWith(expect.objectContaining({
      messages: [
        expect.objectContaining({ role: 'user', content: 'old question' }),
        expect.objectContaining({ role: 'assistant', content: 'old answer' }),
      ],
      agent,
    }))
  })

  it('sanitizes workflow placeholder answers before loading history into the UI', async () => {
    const listMessagesSpy = vi.spyOn(transport, 'listMessages')
    listMessagesSpy.mockResolvedValue({
      messages: [
        { id: 'history:conv_1:user', role: 'user', content: 'old question' },
        { id: 'history:conv_1:assistant', role: 'assistant', content: 'token:\n\nid:' },
      ],
      hasMore: false,
      firstId: 'msg_1',
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })

    await agent.selectConversation('conv_1')

    expect(agent.messages).toEqual([
      expect.objectContaining({ role: 'user', content: 'old question' }),
      expect.objectContaining({
        role: 'assistant',
        content: '该历史轮次没有保存最终回复。',
        metadata: expect.objectContaining({ originalPlaceholderContent: 'token:\n\nid:' }),
      }),
    ])
  })

  it('loads history messages before notifying conversation id change', async () => {
    const listMessagesSpy = vi.spyOn(transport, 'listMessages')
    listMessagesSpy.mockResolvedValue({
      messages: [
        { id: 'history:conv_1:user', role: 'user', content: 'old question' },
      ],
      hasMore: false,
      firstId: 'msg_1',
    } as any)

    let messageCountAtConversationChange = -1
    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    }, 'default', undefined, {
      onConversationIdChange: () => {
        messageCountAtConversationChange = agent.messages.length
      },
    })

    await agent.selectConversation('conv_1')

    expect(messageCountAtConversationChange).toBe(1)
  })

  it('loads selected history into the visible thread clone instead of the source agent', async () => {
    const listMessagesSpy = vi.spyOn(transport, 'listMessages')
    listMessagesSpy.mockResolvedValue({
      messages: [
        { id: 'history:conv_1:user', role: 'user', content: 'old question' },
        { id: 'history:conv_1:assistant', role: 'assistant', content: 'old answer' },
      ],
      hasMore: false,
      firstId: 'msg_1',
    } as any)

    const sourceAgent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })
    const visibleAgent = sourceAgent.clone()
    visibleAgent.threadId = 'visible-thread'
    visibleAgent.setMessages([])

    await visibleAgent.selectConversation('conv_1')

    expect(sourceAgent.messages).toEqual([])
    expect(visibleAgent.messages).toEqual([
      expect.objectContaining({ role: 'user', content: 'old question' }),
      expect.objectContaining({ role: 'assistant', content: 'old answer' }),
    ])
    expect(visibleAgent.getConversationId()).toBe('conv_1')
  })

  it('posts the Dify stop request before aborting the local stream', () => {
    const stopChatSpy = vi.spyOn(transport, 'stopChat').mockResolvedValue()
    const abort = vi.fn()
    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })

    ;(agent as any).currentTaskId = 'task_1'
    ;(agent as any).abortController = { abort }

    agent.abortRun()

    expect(stopChatSpy).toHaveBeenCalledWith({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      taskId: 'task_1',
    })
    expect(abort).toHaveBeenCalled()
    expect(stopChatSpy.mock.invocationCallOrder[0]).toBeLessThan(abort.mock.invocationCallOrder[0])
    expect((agent as any).currentTaskId).toBe('')
  })

  it('clears pending permission state when selecting another conversation', async () => {
    const streamChatSpy = vi.spyOn(transport, 'streamChat')
    const listMessagesSpy = vi.spyOn(transport, 'listMessages')
    streamChatSpy
      .mockResolvedValueOnce({
        response: {
          conversationId: 'conv_old',
          taskId: 'task_old',
        },
        events: [
          {
            event: 'agent_log',
            data: {
              data: JSON.stringify({
                type: 'RUN_FINISHED',
                result: {
                  answer: 'Allow current_time?',
                  executionMetadata: {
                    finishReason: 'awaiting_user',
                  },
                },
                outcome: {
                  type: 'interrupt',
                  interrupts: [
                    {
                      id: 'call_1',
                      toolCallId: 'call_1',
                      message: 'Allow current_time?',
                      metadata: {
                        purpose: 'permission',
                        options: [
                          { label: 'Always allow', value: 'allow_conversation', description: '' },
                        ],
                        allowCustomInput: false,
                        multiSelect: false,
                      },
                    },
                  ],
                },
              }),
            },
          },
        ],
      } as any)
      .mockResolvedValueOnce({
        response: {
          conversationId: 'conv_new',
          taskId: 'task_new',
        },
        events: [
          { event: 'message', answer: 'normal reply' },
        ],
      } as any)
    listMessagesSpy.mockResolvedValue({
      messages: [
        { id: 'history:conv_new:user', role: 'user', content: 'old question' },
      ],
      hasMore: false,
      firstId: 'msg_1',
    } as any)

    const agent = new DifyAgUiAgent({
      baseUrl: 'http://localhost/v1',
      apiKey: 'app-test',
      user: 'tester',
      inputs: {},
    })

    agent.addMessage({ id: 'u1', role: 'user', content: 'what day is it?' } as any)
    await agent.runAgent()
    expect((agent as any).pendingInterrupt).toMatchObject({
      purpose: 'permission',
      options: [{ label: 'Always allow', value: 'allow_conversation', description: '' }],
    })
    await agent.selectConversation('conv_new')
    expect((agent as any).pendingInterrupt).toBeNull()
    agent.addMessage({ id: 'u2', role: 'user', content: 'Always allow' } as any)
    await agent.runAgent()

    expect(streamChatSpy).toHaveBeenNthCalledWith(2, expect.objectContaining({
      conversationId: 'conv_new',
      query: 'Always allow',
      inputs: expect.not.objectContaining({
        user_prompt_response: expect.anything(),
      }),
    }))
  })
  it('resumes a permission raised through the real Dify fallback stream', async () => {
    const final = { event: 'agent_finished', answer: 'Allow?', execution_metadata: {
      finish_reason: 'awaiting_user', question: { id: 'fallback-call', purpose: 'permission',
        question: 'Allow?', options: [{ label: '允许一次', value: 'allow_once' }], fields: [],
        allowCustomInput: false, multiSelect: false } } }
    fetchMock.mockResolvedValueOnce({ ok: true, body: streamFromEvents([
      { event: 'workflow_finished', data: { outputs: { result: final } } },
    ]) }).mockResolvedValueOnce({ ok: true, body: streamFromEvents([
      { event: 'workflow_finished', data: { outputs: { result: { event: 'agent_finished', answer: 'done' } } } },
    ]) })
    const agent = new DifyAgUiAgent({ baseUrl: 'http://localhost/v1', apiKey: 'app-test', user: 'tester' })
    agent.addMessage({ id: 'u1', role: 'user', content: 'do it' } as any)
    await agent.runAgent()
    agent.addMessage({ id: 'u2', role: 'user', content: '允许一次' } as any)
    await agent.runAgent()
    const body = JSON.parse(String(fetchMock.mock.calls[1][1].body))
    expect(body.inputs.user_prompt_response).toMatchObject({ promptId: 'fallback-call', selectedValues: ['allow_once'] })
  })

})
