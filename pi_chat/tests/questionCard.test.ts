import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import QuestionCard from '../src/cards/QuestionCard.vue'
import { parseRecommendedLabel } from '../src/cards/questionDraft'
import type { QuestionEntry, Questionnaire } from '../src/projection/transcript'

const BASE_TS = new Date('2026-11-07T10:00:00').getTime()

/* 问卷夹具平移自 pi_workbench tests/components.test.ts 的 AskUserForm 半区
   （single/multi/text 三型 + 必填 + min/max），id 契约与 pi_dify 一致。 */
const QUESTIONNAIRE: Questionnaire = {
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
      min_selections: 1,
      max_selections: 2,
      options: [
        { id: 'a', label: 'A' },
        { id: 'b', label: 'B' },
      ],
    },
    { id: 'notes', question: 'Notes', type: 'text', required: false },
  ],
}

function questionEntry(partial: Partial<QuestionEntry> = {}): QuestionEntry {
  return {
    id: 'question_q1',
    kind: 'question',
    pendingId: 'q1',
    questionnaire: QUESTIONNAIRE,
    status: 'waiting',
    ts: BASE_TS,
    ...partial,
  } as QuestionEntry
}

function primaryButton(wrapper: ReturnType<typeof mount>) {
  return wrapper
    .findAll('button')
    .find((button) => button.text() === '下一题' || button.text() === '提交')!
}

/* 组件 seam（spec 测试决策 3）：@vue/test-utils + happy-dom 挂载，只断言外显行为。
   用例平移自 pi_workbench components.test.ts 问卷半区（必填校验、三型提交、
   提交中禁用、历史作答回显），并按 Harness QuestionComposer 交互补齐
   分页/跳过/min-max/倒计时用例。 */

describe('questionDraft 推荐徽章解析（pure TS 平移）', () => {
  it('解析（推荐）/（recommended）后缀并剥掉后缀文本', () => {
    expect(parseRecommendedLabel('订单 A（推荐）')).toEqual({ label: '订单 A', recommended: true })
    expect(parseRecommendedLabel('Plan B (Recommended)')).toEqual({ label: 'Plan B', recommended: true })
    expect(parseRecommendedLabel('普通选项')).toEqual({ label: '普通选项', recommended: false })
  })
})

describe('QuestionCard 必填校验', () => {
  it('未答必填时主按钮禁用；跳过必填后提交被阻止并跳回该题提示', async () => {
    const wrapper = mount(QuestionCard, { props: { entry: questionEntry() } })
    // 第 1 题（必填单选）未作答：主按钮（下一题）禁用，问题级拦截。
    expect(primaryButton(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('1 / 3')

    // 逐题跳过；末题跳过即触发整组提交：必填缺失阻止提交并跳回第 1 题提示。
    await wrapper.findAll('button').find((button) => button.text() === '跳过')!.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '跳过')!.trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('3 / 3')
    await wrapper.findAll('button').find((button) => button.text() === '跳过')!.trigger('click')
    expect(wrapper.find('[data-testid="question-feedback"]').text()).toContain('请先完成这道问题')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('1 / 3')
    expect(wrapper.emitted('submit')).toBeFalsy()
  })
})

describe('QuestionCard 三型提交', () => {
  it('single 提交选项 id、multi 提交 id 数组、text 提交文本', async () => {
    const wrapper = mount(QuestionCard, { props: { entry: questionEntry() } })
    // single：点击第二个选项后自动翻到第 2 题。
    await wrapper.findAll('[role="radio"]')[1].trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('2 / 3')
    // multi：勾选两项。
    const checkboxes = wrapper.findAll('[role="checkbox"]')
    await checkboxes[0].trigger('click')
    await checkboxes[1].trigger('click')
    await primaryButton(wrapper).trigger('click') // 下一题 → 第 3 题
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('3 / 3')
    await wrapper.find('textarea').setValue('note text')
    await primaryButton(wrapper).trigger('click') // 提交
    const emitted = wrapper.emitted('submit')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({ color: 'blue', tags: ['a', 'b'], notes: 'note text' })
  })
})

describe('QuestionCard min/max 约束', () => {
  const constrained: Questionnaire = {
    ...QUESTIONNAIRE,
    questions: QUESTIONNAIRE.questions.map((question) =>
      question.id === 'tags' ? { ...question, min_selections: 2, max_selections: 2 } : question,
    ),
  }

  it('少选提示至少 N 项并阻止提交', async () => {
    const wrapper = mount(QuestionCard, {
      props: { entry: questionEntry({ questionnaire: constrained }) },
    })
    await wrapper.findAll('[role="radio"]')[0].trigger('click') // q1 → q2
    await wrapper.findAll('[role="checkbox"]')[0].trigger('click') // 只选 1 项（min 2）
    await primaryButton(wrapper).trigger('click') // q2 → q3
    await wrapper.findAll('button').find((button) => button.text() === '跳过')!.trigger('click') // q3 跳过触发提交
    expect(wrapper.find('[data-testid="question-feedback"]').text()).toContain('至少选择 2 项')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('2 / 3')
    expect(wrapper.emitted('submit')).toBeFalsy()
  })

  it('多选提示最多 N 项并阻止提交', async () => {
    const wider: Questionnaire = {
      ...constrained,
      questions: constrained.questions.map((question) =>
        question.id === 'tags'
          ? {
              ...question,
              max_selections: 2,
              options: [
                ...(question.options ?? []),
                { id: 'c', label: 'C' },
              ],
            }
          : question,
      ),
    }
    const wrapper = mount(QuestionCard, {
      props: { entry: questionEntry({ questionnaire: wider }) },
    })
    await wrapper.findAll('[role="radio"]')[0].trigger('click') // q1 → q2
    const checkboxes = wrapper.findAll('[role="checkbox"]')
    await checkboxes[0].trigger('click')
    await checkboxes[1].trigger('click')
    await checkboxes[2].trigger('click') // 选满 3 项（max 2）
    await primaryButton(wrapper).trigger('click') // q2 → q3
    await wrapper.findAll('button').find((button) => button.text() === '跳过')!.trigger('click') // q3 跳过触发提交
    expect(wrapper.find('[data-testid="question-feedback"]').text()).toContain('最多选择 2 项')
    expect(wrapper.emitted('submit')).toBeFalsy()
  })
})

describe('QuestionCard text 型 placeholder / max_length', () => {
  it('带出 question.placeholder 与 max_length，选项题内联自定义答案用上游占位文案', async () => {
    const wrapper = mount(QuestionCard, { props: { entry: questionEntry() } })
    expect(wrapper.find('textarea').attributes('placeholder')).toBe('输入你的答案')
    const withText: Questionnaire = {
      ...QUESTIONNAIRE,
      questions: QUESTIONNAIRE.questions.map((question) =>
        question.id === 'notes' ? { ...question, placeholder: '选填备注', max_length: 500 } : question,
      ),
    }
    const wrapper2 = mount(QuestionCard, {
      props: { entry: questionEntry({ questionnaire: withText }) },
    })
    await wrapper2.findAll('[role="radio"]')[0].trigger('click') // q1 → q2
    await wrapper2.findAll('[role="checkbox"]')[0].trigger('click') // q2 勾选
    await primaryButton(wrapper2).trigger('click') // 下一题 → q3（text 型）
    const textarea = wrapper2.find('textarea')
    expect(textarea.attributes('placeholder')).toBe('选填备注')
    expect(textarea.attributes('maxlength')).toBe('500')
  })
})

describe('QuestionCard 提交中禁用', () => {
  it('submitting 时选项/跳过/提交/翻页/关闭全部禁用，主按钮显示正在提交', () => {
    const wrapper = mount(QuestionCard, {
      props: { entry: questionEntry({ submitting: true }) },
    })
    // 长文案折叠钮是纯装饰（CSS 控制显隐），与上游一致不参与提交冻结。
    const actionable = wrapper
      .findAll('button')
      .filter((button) => !button.classes().some((cls) => cls.includes('copyToggle')))
    expect(actionable.length).toBeGreaterThan(0)
    expect(actionable.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.find('[data-testid="question-primary"]').text()).toBe('正在提交…')
  })
})

describe('QuestionCard 历史作答回显', () => {
  it('作答后渲染只读回显：选中态可见、无提交/跳过按钮、翻页可走记录', async () => {
    const wrapper = mount(QuestionCard, {
      props: {
        entry: questionEntry({
          status: 'answered',
          answers: { color: 'red', tags: ['a'], notes: 'done' },
        }),
      },
    })
    expect(wrapper.text()).toContain('已回答')
    expect(wrapper.text()).toContain('Red')
    // 只读：没有跳过/提交入口。
    expect(wrapper.findAll('button').some((button) => button.text() === '跳过')).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text() === '提交')).toBe(false)
    // 选中态回显：single 选中 Red，multi 勾选 A。
    expect(wrapper.findAll('[role="radio"]')[0].attributes('aria-checked')).toBe('true')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('1 / 3')
    // 翻页仍可走记录。
    await wrapper.find('[data-testid="question-next"]').trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('2 / 3')
    expect(wrapper.findAll('[role="checkbox"]')[0].attributes('aria-checked')).toBe('true')
    await wrapper.find('[data-testid="question-next"]').trigger('click')
    // text 型记录在只读文本域的值里回显。
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('done')
  })

  it('取消的问卷渲染只读取消态', () => {
    const wrapper = mount(QuestionCard, {
      props: { entry: questionEntry({ status: 'cancelled' }) },
    })
    expect(wrapper.text()).toContain('已取消')
    expect(wrapper.findAll('button').some((button) => button.text() === '跳过')).toBe(false)
  })
})

describe('QuestionCard 跳过保留其余草稿', () => {
  it('跳过只清空当前题草稿并翻页，其余题草稿保留', async () => {
    const wrapper = mount(QuestionCard, { props: { entry: questionEntry() } })
    await wrapper.findAll('[role="radio"]')[1].trigger('click') // q1 选 Blue → 翻到 q2
    await wrapper.findAll('[role="checkbox"]')[0].trigger('click') // q2 勾选 A
    await wrapper.findAll('button').find((button) => button.text() === '跳过')!.trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('3 / 3')
    // 回翻：q2 草稿被跳过清空，q1 的 Blue 保留。
    await wrapper.find('[data-testid="question-prev"]').trigger('click')
    expect(wrapper.findAll('[role="checkbox"]')[0].attributes('aria-checked')).toBe('false')
    await wrapper.find('[data-testid="question-prev"]').trigger('click')
    expect(wrapper.findAll('[role="radio"]')[1].attributes('aria-checked')).toBe('true')
  })
})

describe('QuestionCard 翻页器', () => {
  it('显示 1 / N 进度，首页 prev 禁用', () => {
    const wrapper = mount(QuestionCard, { props: { entry: questionEntry() } })
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('1 / 3')
    expect(wrapper.find('[data-testid="question-prev"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="question-next"]').attributes('disabled')).toBeUndefined()
  })
})

describe('QuestionCard 倒计时', () => {
  it('按 expires_at 呈现倒计时，开始编辑后停表并提示会一直等', async () => {
    const questionnaire: Questionnaire = {
      ...QUESTIONNAIRE,
      expires_at: Date.now() + 30_000,
    }
    const wrapper = mount(QuestionCard, {
      props: { entry: questionEntry({ questionnaire }) },
    })
    expect(wrapper.text()).toMatch(/秒后继续工作/)
    // 开始编辑（engage）后倒计时冻结：显示会一直等你回答。
    await wrapper.find('textarea').setValue('自定义回答')
    expect(wrapper.text()).toContain('会一直等你回答')
    expect(wrapper.text()).not.toMatch(/秒后继续工作/)
  })

  it('无 expires_at 时不渲染倒计时也不报错', () => {
    const wrapper = mount(QuestionCard, { props: { entry: questionEntry() } })
    expect(wrapper.text()).not.toMatch(/秒后继续工作/)
    expect(wrapper.find('[data-testid="question-feedback"]').text()).toBe('')
  })
})

describe('QuestionCard 推荐徽章', () => {
  it('解析（推荐）后缀渲染徽章，单选自动预选推荐项', async () => {
    const questionnaire: Questionnaire = {
      ...QUESTIONNAIRE,
      questions: QUESTIONNAIRE.questions.map((question) =>
        question.id === 'color'
          ? {
              ...question,
              options: [
                { id: 'red', label: 'Red（推荐）' },
                { id: 'blue', label: 'Blue' },
              ],
            }
          : question,
      ),
    }
    const wrapper = mount(QuestionCard, {
      props: { entry: questionEntry({ questionnaire }) },
    })
    expect(wrapper.text()).toContain('推荐')
    expect(wrapper.text()).not.toContain('Red（推荐）')
    expect(wrapper.findAll('[role="radio"]')[0].attributes('aria-checked')).toBe('true')
    // 换选另一项后照常翻页。
    await wrapper.findAll('[role="radio"]')[1].trigger('click')
    expect(wrapper.find('[data-testid="question-progress"]').text()).toBe('2 / 3')
  })
})

describe('QuestionCard 取消整组', () => {
  it('点击关闭按钮 emit cancel', async () => {
    const wrapper = mount(QuestionCard, { props: { entry: questionEntry() } })
    await wrapper.find('[data-testid="card-close"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })
})
