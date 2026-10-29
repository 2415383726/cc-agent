import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AskUserForm from '../src/components/AskUserForm.vue'
import ApprovalCard from '../src/components/ApprovalCard.vue'
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
    await wrapper.findAll('button').find((button) => button.text().includes('Submit answers'))!.trigger('click')
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
    await wrapper.findAll('button').find((button) => button.text().includes('Submit answers'))!.trigger('click')
    const emitted = wrapper.emitted('submit')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({ color: 'blue', tags: ['a', 'b'], notes: 'note text' })
  })

  it('disables submission while submitting', () => {
    const wrapper = mount(AskUserForm, {
      props: { questionnaire, status: 'waiting', submitting: true },
    })
    const submit = wrapper.findAll('button').find((button) => button.text().includes('Submitting'))!
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
    await wrapper.findAll('button').find((button) => button.text().includes('Approve'))!.trigger('click')
    expect(wrapper.emitted('decide')?.[0]).toEqual(['approve', 'session'])
    expect(wrapper.text()).toContain('not a questionnaire answer')
  })

  it('shows rejection as a resolved non-executed state', () => {
    const wrapper = mount(ApprovalCard, {
      props: { entry: { ...entry, status: 'rejected' } },
    })
    expect(wrapper.text()).toContain('was not executed')
  })
})
