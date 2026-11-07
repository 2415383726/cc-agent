import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'

const fetchSpy = vi.fn(() => Promise.reject(new Error('回放模式不允许网络请求')))

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
  await wrapper.find('[data-testid="enter-live"]').trigger('click')
  await wrapper.find('[data-testid="form-api-key"]').setValue('app-live-key')
  await wrapper.find('[data-testid="connect-submit"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  fetchSpy.mockClear()
  vi.stubGlobal('fetch', fetchSpy)
  window.history.replaceState({}, '', '/')
  // 票 07 的连接测试会写入会话凭据；清空避免用例间串味（凭据惰性自动连线会抢跑表单步骤）。
  window.sessionStorage.clear()
})

describe('pi_chat replay shell', () => {
  it('默认渲染 process 场景，回放标注可见，且零网络请求', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('回放模式')
    // 完成态回合默认折叠：过程行（工具卡）藏进终态头，文本与技能名仍可见
    const header = wrapper.find('[data-testid="terminal-row"]')
    expect(header.exists()).toBe(true)
    expect(header.attributes('aria-expanded')).toBe('false')
    expect(wrapper.text()).toContain('已完成')
    await header.trigger('click')
    expect(wrapper.text()).toContain('lookup_order')
    expect(wrapper.text()).toContain('refund-policy')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('三个场景都在回放清单中可选，切换即渲染对应场景', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const select = wrapper.find('select')
    const optionText = select.findAll('option').map((option) => option.text())
    expect(optionText.some((text) => text.includes('工具、技能与压缩'))).toBe(true)
    expect(optionText.some((text) => text.includes('问卷暂停与答复'))).toBe(true)
    expect(optionText.some((text) => text.includes('工具审批与未知写操作'))).toBe(true)

    await select.setValue('questionnaire')
    await flushPromises()
    // 票据 05 后问卷场景渲染完整问卷卡：第 1 题眉题（question.header）与题干可见。
    expect(wrapper.text()).toContain('订单')
    expect(wrapper.text()).toContain('要退款的是哪个订单？')

    await select.setValue('approval')
    await flushPromises()
    expect(wrapper.text()).toContain('delete_record')
    expect(wrapper.text()).toContain('等待审批')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('?replay=<id> URL 参数选择对应场景', async () => {
    window.history.replaceState({}, '', '/?replay=approval')
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('delete_record')
    expect(wrapper.text()).toContain('等待审批')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('应用壳为三区布局：侧栏轨道、时间线滚动区、composer 区', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('[data-zone="sidebar"]').exists()).toBe(true)
    const timeline = wrapper.find('[data-zone="timeline"]')
    expect(timeline.exists()).toBe(true)
    expect(timeline.find('[aria-label="会话记录"]').exists()).toBe(true)
    const composer = wrapper.find('[data-zone="composer"]')
    expect(composer.exists()).toBe(true)
    expect(wrapper.text()).toContain('新会话')
    expect(wrapper.text()).toContain('回放模式')
  })

  it('composer 可输入文本，发送为禁用占位，输入不发网络请求', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const textarea = wrapper.find('[data-zone="composer"] textarea')
    expect(textarea.exists()).toBe(true)
    expect(textarea.attributes('disabled')).toBeUndefined()
    await textarea.setValue('你好，pi chat')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('你好，pi chat')
    expect(wrapper.text()).not.toContain('回放模式不允许网络请求')

    const send = wrapper.find('[data-zone="composer"] [data-testid="composer-send"]')
    expect(send.exists()).toBe(true)
    expect(send.attributes('disabled')).toBeDefined()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('问卷回放可完整交互：作答、翻页、跳过、提交全程本地闭环', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const select = wrapper.find('select')
    await select.setValue('questionnaire')
    await flushPromises()

    // 第 1 题（必填单选）：选第二个选项，自动翻页。
    await wrapper.findAll('[role="radio"]')[1].trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('2 / 3')
    // 第 2 题（multi，min1/max2）：勾选两项后翻页。
    const checkboxes = wrapper.findAll('[role="checkbox"]')
    await checkboxes[0].trigger('click')
    await checkboxes[1].trigger('click')
    await wrapper.find('[data-testid="question-primary"]').trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('3 / 3')
    // 第 3 题（text 选填）：跳过即提交。
    await wrapper.findAll('button').find((button) => button.text() === '跳过')!.trigger('click')

    // 回放闭环：question.answered 落记录 → 卡片只读回显 + 用户答复气泡 + 回放终态。
    await flushPromises()
    expect(wrapper.find('[data-testid="question-review-status"]').text()).toBe('已回答')
    expect(wrapper.text()).toContain('谢谢，问卷已提交')
    expect(wrapper.text()).toContain('订单 B-2099')
    expect(wrapper.text()).toContain('到货损坏, 商品错误')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('问卷取消走回放本地闭环并渲染取消态', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const select = wrapper.find('select')
    await select.setValue('questionnaire')
    await flushPromises()
    await wrapper.find('[data-testid="card-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="question-review-status"]').text()).toBe('已取消')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('审批回放批准路径闭环：阻断态可操作，scope 随决定提交，卡片回显已批准', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('select').setValue('approval')
    await flushPromises()
    // 等待态：阻断提示醒目，scope 默认 once，卡可直接操作（工具名/参数可见）。
    expect(wrapper.find('[data-testid="approval-blocked"]').text()).toContain('阻断')
    expect(wrapper.find('[data-testid="approval-args"]').text()).toContain('"record": "stale-14"')
    expect(wrapper.find('[data-testid="approval-scope-once"]').attributes('aria-checked')).toBe('true')
    // 切到 session 后批准：scope 随决定一并提交。
    await wrapper.find('[data-testid="approval-scope-session"]').trigger('click')
    await wrapper.find('[data-testid="approval-approve"]').trigger('click')
    await flushPromises()
    // 回放闭环：卡片只读回显已批准（本会话范围），终态落记录。
    expect(wrapper.find('[data-testid="approval-echo"]').text()).toContain('已批准')
    expect(wrapper.find('[data-testid="approval-echo"]').text()).toContain('本会话范围')
    expect(wrapper.find('[data-testid="approval-approve"]').exists()).toBe(false)
    // 终态行（已完成）+ 助手收尾消息落记录；terminal.answer 不直接进 DOM（与问卷流同款）。
    expect(wrapper.text()).toContain('回放模式下已应用审批')
    expect(wrapper.text()).toContain('已完成')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('审批回放拒绝路径闭环：卡片呈现未执行非执行态', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('select').setValue('approval')
    await flushPromises()
    await wrapper.find('[data-testid="approval-reject"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已拒绝')
    expect(wrapper.find('[data-testid="approval-echo"]').text()).toContain('未执行')
    expect(wrapper.find('[data-testid="approval-approve"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="approval-reject"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('操作已被拒绝，没有产生变更。')
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('pi_chat 实时模式接线', () => {
  it('默认仍是回放模式；进入实时模式后显示连接表单与实时徽标', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('回放模式')
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('实时模式')
    // 侧栏切到实时控制器：无凭据时列表为空态
    expect(wrapper.find('[data-testid="conversation-item"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('暂无历史会话')
  })

  it('连接表单校验：缺 API Key 提示；填写后提交触发会话列表刷新（失败有兜底态）', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
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

  it('实时模式可切回回放模式，回放内容不受影响', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(true)
    await wrapper.find('[data-testid="back-replay"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('回放模式')
    // 回放内容不受影响：折叠头在，展开后过程行如常
    expect(wrapper.find('[data-testid="terminal-row"]').exists()).toBe(true)
    await wrapper.find('[data-testid="terminal-row"]').trigger('click')
    expect(wrapper.text()).toContain('lookup_order')
    expect(wrapper.find('[data-testid="connection-form"]').exists()).toBe(false)
  })

  it('实时模式 composer 可发送：点击发送即发起 Dify 请求', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
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

describe('pi_chat 实时模式：附件、停止与连接表单收尾（票 08）', () => {
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
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
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
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
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
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
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
    expect(wrapper.text()).toContain('暂无消息')

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
    await wrapper.find('[data-testid="enter-live"]').trigger('click')
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

describe('pi_chat 实时模式：共享时间线渲染器（ADR-0010 同一契约与组件）', () => {
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
