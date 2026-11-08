import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'

const fetchSpy = vi.fn(() => Promise.reject(new Error('unexpected network request')))

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
    json: async () => body,
  } as unknown as Response
}

/** SSE 流：推入给定事件后即关闭（正常收束）；带 signal 时 abort 提前关流（模拟断流）。 */
function sseResponse(events: unknown[], signal?: AbortSignal): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const item of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(item)}\n\n`))
      }
      const close = () => {
        try {
          controller.close()
        } catch {
          /* 已关闭 */
        }
      }
      if (signal) {
        if (signal.aborted) close()
        else signal.addEventListener('abort', close, { once: true })
        return
      }
      close()
    },
  })
  return { ok: true, status: 200, body: stream } as unknown as Response
}

/** 路由式 fetch 桩：记录各类请求次数与最近的 chat-messages init。 */
function useLiveFetch(options: {
  conversations?: unknown | Error
  upload?: unknown | Error
  onChat?: (init: RequestInit) => Response
}) {
  const counts = { chat: 0, stop: 0, upload: 0, conversations: 0 }
  let chatInit: RequestInit | null = null
  fetchSpy.mockImplementation((url: unknown, init: RequestInit = {}) => {
    const target = String(url)
    if (target.includes('/files/upload')) {
      counts.upload += 1
      return options.upload instanceof Error
        ? Promise.reject(options.upload)
        : Promise.resolve(jsonResponse(options.upload ?? { id: 'file_1', name: '报告.pdf', mime_type: 'application/pdf', size: 2048 }))
    }
    if (target.includes('/chat-messages/') && target.endsWith('/stop')) {
      counts.stop += 1
      return Promise.resolve(jsonResponse({ result: 'success' }))
    }
    if (target.endsWith('/chat-messages')) {
      counts.chat += 1
      chatInit = init
      return Promise.resolve(options.onChat ? options.onChat(init) : sseResponse([]))
    }
    if (target.includes('/conversations')) {
      counts.conversations += 1
      return options.conversations instanceof Error
        ? Promise.reject(options.conversations)
        : Promise.resolve(jsonResponse(options.conversations ?? { data: [], has_more: false }))
    }
    return Promise.reject(new Error(`unexpected fetch: ${target}`))
  })
  return {
    counts,
    chatInit: () => chatInit,
    chatBody: () => (chatInit ? JSON.parse(String(chatInit.body)) : null),
  }
}

/** 只做 UI 步骤：fetch 桩由各用例先经 useLiveFetch 设置（避免覆盖路由）。 */
async function enterConnectedLive(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('[data-testid="form-api-key"]').setValue('app-live-key')
  await wrapper.find('[data-testid="connect-submit"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  fetchSpy.mockClear()
  vi.stubGlobal('fetch', fetchSpy)
  window.history.replaceState({}, '', '/')
  // 票 07 的连接测试会写入会话凭据；清空避免用例间串味（凭据自动续连会抢跑表单步骤）。
  window.sessionStorage.clear()
})

describe('pi_chat 接线', () => {
  it('默认显示连接表单与空会话列表（未连接）', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="mode-badge"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('暂无历史会话')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('应用壳为三区布局：侧栏轨道、时间线滚动区、composer 区', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('[data-zone="sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-zone="timeline"]').exists()).toBe(true)
    expect(wrapper.find('[data-zone="composer"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('新会话')
  })

  it('连接表单校验：缺 API Key 提示；填写后提交触发会话列表刷新（失败有兜底态）', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const form = wrapper.find('[data-testid="connection-form"]')
    await form.find('[data-testid="connect-submit"]').trigger('click')
    expect(wrapper.text()).toContain('请填写服务地址与 API Key')
    expect(fetchSpy).not.toHaveBeenCalled()

    await form.find('[data-testid="form-api-key"]').setValue('app-test-key')
    await form.find('[data-testid="connect-submit"]').trigger('click')
    expect(fetchSpy).toHaveBeenCalled()
    await flushPromises()
    // fetch 桩始终拒绝：侧栏进入「加载失败重试」兜底态
    expect(wrapper.find('[data-testid="conversations-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('重试')
  })

  it('composer 可发送：点击发送即发起 Dify 请求', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('[data-testid="form-api-key"]').setValue('app-test-key')
    await wrapper.find('[data-testid="connect-submit"]').trigger('click')
    await flushPromises()
    const textarea = wrapper.find('[data-zone="composer"] textarea')
    await textarea.setValue('你好，Dify')
    const send = wrapper.find('[data-zone="composer"] [data-testid="composer-send"]')
    expect(send.attributes('disabled')).toBeUndefined()
    await send.trigger('click')
    await flushPromises()
    // fetch 桩拒绝 → 控制器进入错误终态（transport_failed）
    expect(wrapper.text()).toContain('你好，Dify')
    expect(fetchSpy).toHaveBeenCalled()
  })
})

describe('pi_chat：附件、停止与连接表单收尾（票 08）', () => {
  async function pickComposerFile(wrapper: ReturnType<typeof mount>, file: File): Promise<void> {
    const input = wrapper.find('[data-testid="composer-file-input"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
  }

  it('附件端到端：选择文件→files/upload→chip 元数据→发送带 local_file files[]→草稿与chips清空→消息区展示元数据', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const { counts, chatBody } = useLiveFetch({
      onChat: () =>
        sseResponse([
          { event: 'message', task_id: 'task_1', answer: '已收到附件', conversation_id: 'conv_live' },
          { event: 'message_end', conversation_id: 'conv_live' },
        ]),
    })
    await wrapper.find('[data-testid="form-api-key"]').setValue('app-live-key')
    await wrapper.find('[data-testid="connect-submit"]').trigger('click')
    await flushPromises()

    await pickComposerFile(wrapper, new File([new Uint8Array(2048)], '报告.pdf', { type: 'application/pdf' }))
    expect(counts.upload).toBe(1)
    const chips = wrapper.findAll('[data-testid="composer-file-chip"]')
    expect(chips).toHaveLength(1)
    expect(chips[0].text()).toContain('报告.pdf')
    expect(chips[0].text()).toContain('application/pdf')
    expect(chips[0].text()).toContain('2.0 KB')

    await wrapper.find('[data-zone="composer"] textarea').setValue('请看附件')
    await wrapper.find('[data-zone="composer"] [data-testid="composer-send"]').trigger('click')
    await flushPromises()

    // 请求体：local_file 传输方式 + 上传后的文件 id（无文件内容、无本地路径）
    const body = chatBody()
    expect(body.files).toEqual([{ type: 'document', transfer_method: 'local_file', upload_file_id: 'file_1' }])
    expect(body.query).toBe('请看附件')
    // 发送后清空草稿与待发送 chips
    expect((wrapper.find('[data-zone="composer"] textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.findAll('[data-testid="composer-file-chip"]')).toHaveLength(0)
    // 消息区的用户消息展示同一份安全元数据（无内容、无链接）
    const messageChips = wrapper.findAll('[data-testid="message-file-chip"]')
    expect(messageChips.length).toBeGreaterThanOrEqual(1)
    expect(messageChips[0].text()).toContain('报告.pdf')
    expect(messageChips[0].text()).toContain('application/pdf')
    expect(messageChips[0].text()).toContain('2.0 KB')
    expect(messageChips[0].find('a').exists()).toBe(false)
    // 可信终态到达后不再重发
    expect(counts.chat).toBe(1)
    expect(wrapper.text()).toContain('已收到附件')
  })

  it('附件上传失败：actionNote 兜底提示（侧栏），待发送列表为空', async () => {
    const wrapper = mount(App)
    await flushPromises()
    useLiveFetch({ upload: new Error('File Too Large') })
    await wrapper.find('[data-testid="form-api-key"]').setValue('app-live-key')
    await wrapper.find('[data-testid="connect-submit"]').trigger('click')
    await flushPromises()

    await pickComposerFile(wrapper, new File([new Uint8Array(4)], '坏.bin', { type: 'application/octet-stream' }))
    const note = wrapper.find('[data-testid="action-note"]')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('附件上传失败')
    expect(note.text()).toContain('File Too Large')
    expect(wrapper.findAll('[data-testid="composer-file-chip"]')).toHaveLength(0)
    // P3-4：同一失败即时反馈贴近 composer 附件行
    const composerNote = wrapper.find('[data-testid="composer-action-note"]')
    expect(composerNote.exists()).toBe(true)
    expect(composerNote.text()).toContain('附件上传失败')
    expect(composerNote.text()).toContain('File Too Large')
  })

  it('停止链路：composer 停止按钮→stop 端点+请求中止→「已请求停止」未确认终态，绝不自动重发，结束后恢复发送按钮', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const { counts, chatInit } = useLiveFetch({
      onChat: (init) =>
        sseResponse(
          [{ event: 'message', task_id: 'task_9', answer: '长任务运行中', conversation_id: 'conv_live' }],
          init.signal,
        ),
    })
    await enterConnectedLive(wrapper)
    await wrapper.find('[data-zone="composer"] textarea').setValue('长任务')
    await wrapper.find('[data-zone="composer"] [data-testid="composer-send"]').trigger('click')
    await flushPromises()

    // 运行中：发送按钮让位给停止按钮
    expect(wrapper.find('[data-zone="composer"] [data-testid="composer-send"]').exists()).toBe(false)
    const stop = wrapper.find('[data-zone="composer"] [data-testid="composer-stop"]')
    expect(stop.exists()).toBe(true)
    await stop.trigger('click')
    await flushPromises()

    expect(counts.stop).toBe(1)
    expect(String(fetchSpy.mock.calls.find((call) => String(call[0]).includes('/stop'))?.[0])).toBe(
      '/v1/chat-messages/task_9/stop',
    )
    // fetch abort：发起对话请求的 signal 已中止
    expect((chatInit() as unknown as { signal: AbortSignal }).signal.aborted).toBe(true)
    // 「已请求停止」提示（横幅 + 未确认终态说明）且绝不自动重发
    expect(wrapper.text()).toContain('已请求停止')
    expect(wrapper.text()).toContain('未确认')
    expect(counts.chat).toBe(1)
    // 运行结束：发送按钮恢复
    await flushPromises()
    expect(wrapper.find('[data-zone="composer"] [data-testid="composer-send"]').exists()).toBe(true)
    expect(wrapper.find('[data-zone="composer"] [data-testid="composer-stop"]').exists()).toBe(false)
  })

  it('连接表单收尾：inputs JSON 校验错误提示；连接成功后表单收起；「连接设置」可再展开，「收起」关闭', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const { counts } = useLiveFetch({})
    await wrapper.find('[data-testid="form-api-key"]').setValue('app-live-key')
    // JSON 语法错误：显示解析错误且不发起任何网络请求
    await wrapper.find('[data-testid="form-inputs"]').setValue('{bad json')
    await wrapper.find('[data-testid="connect-submit"]').trigger('click')
    expect(wrapper.find('[data-testid="connection-form"] [role="alert"]').exists()).toBe(true)
    expect(counts.conversations).toBe(0)
    // 合法 JSON 但不是对象：显示「应用输入必须是 JSON 对象」
    await wrapper.find('[data-testid="form-inputs"]').setValue('[1, 2]')
    await wrapper.find('[data-testid="connect-submit"]').trigger('click')
    expect(wrapper.text()).toContain('应用输入必须是 JSON 对象')
    expect(counts.conversations).toBe(0)

    // 连接成功：表单收起，实时会话视图出现
    await wrapper.find('[data-testid="form-inputs"]').setValue('{"city": "杭州"}')
    await wrapper.find('[data-testid="connect-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('你好，有什么可以帮忙的？')

    // 「连接设置」再展开；已连接表单带「收起」按钮，点击后关闭
    await wrapper.find('[data-testid="open-connect-form"]').trigger('click')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(true)
    const collapse = wrapper.find('[data-testid="connect-collapse"]')
    expect(collapse.exists()).toBe(true)
    await collapse.trigger('click')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(false)
  })

  it('连接失败：表单保持可见并显示连接失败重试提示（与侧栏重试并存）', async () => {
    const wrapper = mount(App)
    await flushPromises()
    useLiveFetch({ conversations: new Error('Unauthorized') })
    await wrapper.find('[data-testid="form-api-key"]').setValue('app-live-key')
    await wrapper.find('[data-testid="connect-submit"]').trigger('click')
    await flushPromises()

    const failed = wrapper.find('[data-testid="connect-failed"]')
    expect(failed.exists()).toBe(true)
    expect(failed.text()).toContain('连接失败')
    expect(failed.text()).toContain('Unauthorized')
    expect(failed.text()).toContain('重试')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(true)
    // 侧栏重试兜底同时可用
    expect(wrapper.find('[data-testid="conversations-error"]').exists()).toBe(true)
  })
})

describe('pi_chat：共享时间线渲染器（ADR-0010 同一契约与组件）', () => {
  function agentLog(type: string, seq: number, fields: Record<string, unknown>): unknown {
    return {
      event: 'agent_log',
      data: {
        piagent: {
          schema: 'piagent.display.v1',
          schema_version: 1,
          type,
          run_id: 'run_1',
          seq,
          ts: seq,
          ...fields,
        },
      },
    }
  }

  it('live 工具事件经共享组件渲染：ToolCard 出现（不再是占位级 JSON.stringify 时间线）', async () => {
    const wrapper = mount(App)
    await flushPromises()
    useLiveFetch({
      onChat: () =>
        sseResponse([
          { event: 'message', answer: '查一下', task_id: 't', conversation_id: 'conv_live' },
          agentLog('tool.start', 1, { tool_call_id: 'call_1', name: 'web_search', arguments: { query: '杭州天气' } }),
          agentLog('tool.end', 2, { tool_call_id: 'call_1', name: 'web_search', status: 'ok', result: '晴' }),
          { event: 'message_end', conversation_id: 'conv_live' },
        ]),
    })
    await enterConnectedLive(wrapper)
    await wrapper.find('[data-zone="composer"] textarea').setValue('查杭州天气')
    await wrapper.find('[data-zone="composer"] [data-testid="composer-send"]').trigger('click')
    await flushPromises()
    // 票据 04 同款：工具卡在折叠组内，展开后参数经 ToolCard 的 io 面渲染
    expect(wrapper.find('[data-testid="tool-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tool-toggle"]').exists()).toBe(true)
    await wrapper.find('[data-testid="tool-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="tool-input"]').text()).toContain('杭州天气')
  })

  it('live 问卷卡可交互：作答提交走 submitAnswers 通道（query=提交交互 + ask_user JSON 载荷）', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const { chatBody } = useLiveFetch({
      onChat: () =>
        sseResponse([
          { event: 'message', answer: '需要问卷', task_id: 't', conversation_id: 'conv_live' },
          agentLog('question.asked', 1, {
            questionnaire: {
              id: 'q1',
              pending_id: 'q1',
              questions: [{ id: 'city', type: 'text', question: '城市？', options: [], required: true }],
            },
          }),
        ]),
    })
    await enterConnectedLive(wrapper)
    await wrapper.find('[data-zone="composer"] textarea').setValue('问我')
    await wrapper.find('[data-zone="composer"] [data-testid="composer-send"]').trigger('click')
    await flushPromises()
    // 共享渲染器：问卷卡渲染（此前 live 分支不可交互）
    expect(wrapper.find('[data-testid="question-card"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('城市？')
    // 作答并提交：交互经 controller.submitAnswers → inputs.interaction 协议
    await wrapper.find('[data-testid="question-text-0"]').setValue('杭州')
    await wrapper.find('[data-testid="question-primary"]').trigger('click')
    await flushPromises()
    const body = chatBody()
    expect(body.query).toBe('提交交互')
    expect(JSON.parse(body.inputs.interaction)).toEqual({
      type: 'ask_user',
      pending_id: 'q1',
      answers: { city: '杭州' },
    })
  })
})
