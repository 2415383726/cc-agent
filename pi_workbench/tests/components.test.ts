import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AskUserForm from '../src/components/AskUserForm.vue'
import ApprovalCard from '../src/components/ApprovalCard.vue'
import TranscriptEntry from '../src/components/TranscriptEntry.vue'
import type { Questionnaire } from '../src/projection/transcript'

const questionnaire: Questionnaire = {
  id: 'q1',
  pending_id: 'q1',
  title: 'Details',
  questions: [
    {
      id: 'color',
      question: 'Pick a color',
      type: 'single',
      required: true,
      options: [
        { id: 'red', label: 'Red' },
        { id: 'blue', label: 'Blue' },
      ],
    },
    {
      id: 'tags',
      question: 'Pick tags',
      type: 'multi',
      required: true,
      options: [
        { id: 'a', label: 'A' },
        { id: 'b', label: 'B' },
      ],
    },
    { id: 'notes', question: 'Notes', type: 'text', required: false },
  ],
}

describe('AskUserForm', () => {
  it('validates required answers before submitting', async () => {
    const wrapper = mount(AskUserForm, {
      props: { questionnaire, status: 'waiting' },
    })
    await wrapper.findAll('button').find((button) => button.text().includes('提交答案'))!.trigger('click')
    expect(wrapper.find('[role="alert"]').text()).toContain('Pick a color')
    expect(wrapper.emitted('submit')).toBeFalsy()
  })

  it('submits single, multi and text answers', async () => {
    const wrapper = mount(AskUserForm, {
      props: { questionnaire, status: 'waiting' },
    })
    const radios = wrapper.findAll('input[type="radio"]')
    await radios[1].setValue()
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)
    await wrapper.find('textarea').setValue('note text')
    await wrapper.findAll('button').find((button) => button.text().includes('提交答案'))!.trigger('click')
    const emitted = wrapper.emitted('submit')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({ color: 'blue', tags: ['a', 'b'], notes: 'note text' })
  })

  it('disables submission while submitting', () => {
    const wrapper = mount(AskUserForm, {
      props: { questionnaire, status: 'waiting', submitting: true },
    })
    const submit = wrapper.findAll('button').find((button) => button.text().includes('提交中'))!
    expect(submit.attributes('disabled')).toBeDefined()
  })

  it('renders historical answers instead of an active form', () => {
    const wrapper = mount(AskUserForm, {
      props: {
        questionnaire,
        status: 'answered',
        answers: { color: 'red', tags: ['a'], notes: 'done' },
      },
    })
    expect(wrapper.find('fieldset').exists()).toBe(false)
    expect(wrapper.text()).toContain('Red')
    expect(wrapper.text()).toContain('done')
  })
})

describe('ApprovalCard', () => {
  const entry: any = {
    id: 'approval_1',
    kind: 'approval',
    pendingId: 'p1',
    toolCallId: 'call_1',
    tool: 'delete_record',
    arguments: { record: 'x' },
    source: 'mcp',
    status: 'waiting',
    ts: 0,
  }

  it('requires a separate decision and carries scope', async () => {
    const wrapper = mount(ApprovalCard, { props: { entry } })
    await wrapper.find('select').setValue('session')
    await wrapper.findAll('button').find((button) => button.text().includes('批准'))!.trigger('click')
    expect(wrapper.emitted('decide')?.[0]).toEqual(['approve', 'session'])
    expect(wrapper.text()).toContain('不是问卷作答')
  })

  it('shows rejection as a resolved non-executed state', () => {
    const wrapper = mount(ApprovalCard, {
      props: { entry: { ...entry, status: 'rejected' } },
    })
    expect(wrapper.text()).toContain('未执行')
  })
})

it('keeps generated visualizations inert until a complete native answer has a completed Pi run', async () => {
  const source = '```pi-visualize\n<section data-pi-visualize="1" data-kit-version="1" data-title="排队演示" data-description="调参观察变化"><script>window.bad=true</script></section>\n```'
  const wrapper = mount(TranscriptEntry, { props: { entry: {
    id: 'a1', kind: 'message', role: 'assistant', text: source, ts: 1,
    streaming: true, answerComplete: false, runStatus: 'completed',
  } as any } })
  expect(wrapper.text()).toContain('作品生成中')
  expect(wrapper.find('iframe').exists()).toBe(false)
  await wrapper.setProps({ entry: { ...wrapper.props('entry'), streaming: false, answerComplete: true, runStatus: 'stopped' } as any })
  expect(wrapper.text()).toContain('未自动运行')
  expect(wrapper.find('iframe').exists()).toBe(false)
  await wrapper.setProps({ entry: { ...wrapper.props('entry'), answerComplete: false } as any })
  expect(wrapper.text()).toContain('未自动运行')
  await wrapper.setProps({ entry: { ...wrapper.props('entry'), role: 'user' } as any })
  expect(wrapper.find('.pi-visualize').exists()).toBe(false)
  expect(wrapper.find('iframe').exists()).toBe(false)
  wrapper.unmount()
})

it.each(['completed', 'unknown'])('refuses to run when the required sandbox response policy is missing (%s)', async (runStatus) => {
  const { vi } = await import('vitest')
  const { flushPromises } = await import('@vue/test-utils')
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 Chrome/154.0.0.0')
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, headers: new Headers() })
  vi.stubGlobal('fetch', fetchMock)
  try {
    const wrapper = mount(TranscriptEntry, { props: { entry: {
      id: 'a1', kind: 'message', role: 'assistant', ts: 1, streaming: false,
      answerComplete: true, runStatus,
      text: '```pi-visualize\n<section data-pi-visualize="1" data-kit-version="1" data-title="排队演示" data-description="调参观察变化"></section>\n```',
    } as any } })
    await flushPromises()
    if (runStatus === 'unknown') {
      expect(fetchMock).not.toHaveBeenCalled()
      await wrapper.get('button').trigger('click')
      await flushPromises()
    }
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('部署尚未启用作品网络隔离')
    expect(wrapper.find('iframe').exists()).toBe(false)
    wrapper.unmount()
  } finally {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  }
})

it('preserves a single frame while expanding and ignores messages from other frames', async () => {
  const { vi } = await import('vitest')
  const { flushPromises } = await import('@vue/test-utils')
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 Chrome/154.0.0.0')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ 'Connection-Allowlist': '()' }) }))
  try {
    const wrapper = mount(TranscriptEntry, { props: { conversationId: 'conv-one', entry: {
      id: 'a1', kind: 'message', role: 'assistant', ts: 1, streaming: false,
      answerComplete: true, runStatus: 'completed', platformMessageId: 'platform-a1',
      text: '```pi-visualize\n<section data-pi-visualize="1" data-kit-version="1" data-title="排队演示" data-description="调参观察变化"></section>\n```',
    } as any } })
    await flushPromises()
    const frame = wrapper.find('iframe').element as HTMLIFrameElement
    const contentIdentity = wrapper.find('.pi-visualize').attributes('data-content-id')
    expect(contentIdentity).toMatch(/^conv-one:platform-a1:0:[a-f0-9]+$/)
    window.dispatchEvent(new MessageEvent('message', { source: window, data: { type: 'pi-visualize:error', id: 'fake', message: 'forged' } }))
    await wrapper.get('button[aria-expanded]').trigger('click')
    expect(wrapper.get('button[aria-expanded]').text()).toBe('收起')
    expect(wrapper.find('iframe').element).toBe(frame)
    expect(frame.getAttribute('sandbox')).toBe('allow-scripts')
    await wrapper.get('button[aria-expanded]').trigger('click')
    expect(wrapper.find('iframe').element).toBe(frame)
    await wrapper.get('.pi-visualize-actions button:last-child').trigger('click')
    expect(wrapper.find('iframe').exists()).toBe(false)
    wrapper.unmount()
  } finally { vi.restoreAllMocks(); vi.unstubAllGlobals() }
})

it('opens a valid unconfirmed native artwork only after an explicit click, without changing its run status', async () => {
  const { vi } = await import('vitest')
  const { flushPromises } = await import('@vue/test-utils')
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 Chrome/154.0.0.0')
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ 'Connection-Allowlist': '()' }) })
  vi.stubGlobal('fetch', fetchMock)
  try {
    const entry = { id: 'history-a', kind: 'message', role: 'assistant', ts: 1, streaming: false,
      answerComplete: true, runStatus: 'unknown',
      text: '```pi-visualize\n<section data-pi-visualize="1" data-kit-version="1" data-title="已保存作品" data-description="可本地操作"></section>\n```',
    } as any
    const wrapper = mount(TranscriptEntry, { props: { entry } })
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.find('iframe').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('iframe').exists()).toBe(true)
    expect(entry.runStatus).toBe('unknown')
    expect(wrapper.text()).toContain('运行状态未确认')
    for (const runStatus of ['failed', 'stopped', 'budget_exhausted']) {
      await wrapper.setProps({ entry: { ...entry, runStatus } })
      expect(wrapper.find('iframe').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('查看作品')
    }
    wrapper.unmount()
  } finally { vi.restoreAllMocks(); vi.unstubAllGlobals() }
})
