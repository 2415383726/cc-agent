import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ApprovalCard from '../src/cards/ApprovalCard.vue'
import type { ApprovalEntry } from '../src/projection/transcript'

// 相对日期：跨天运行不改变「同日只显示时钟」的行为（BASE_TS 原为固定日期，会在日期翻转后失效）。
const BASE_TS = (() => {
  const today = new Date()
  today.setHours(10, 0, 0, 0)
  return today.getTime()
})()

/* 审批夹具沿用 pi_dify pending 交互契约（tool/arguments/source/scope_options），
   id 契约与 pi_dify pending 交互一致。 */
function approvalEntry(partial: Partial<ApprovalEntry> = {}): ApprovalEntry {
  return {
    id: 'approval_apv_replay_1',
    kind: 'approval',
    pendingId: 'apv_replay_1',
    toolCallId: 'call_delete',
    tool: 'delete_record',
    arguments: { record: 'stale-14' },
    source: 'mcp',
    scopeOptions: ['once', 'session'],
    status: 'waiting',
    ts: BASE_TS,
    ...partial,
  } as ApprovalEntry
}

/* 组件 seam（spec 测试决策 3）：@vue/test-utils + happy-dom 挂载，只断言外显
   行为（渲染文案 + emit 参数）。用例平移自 pi_workbench components.test.ts
   审批半区（授权语义、scope、拒绝非执行态），并按票据 06 方法节补齐
   阻断提示、提交中禁用、保存态恢复直接可操作。 */

describe('ApprovalCard 等待渲染', () => {
  it('工具名与格式化参数可见，scope 默认 once，阻断提示与授权语义可见', () => {
    const wrapper = mount(ApprovalCard, { props: { entry: approvalEntry() } })
    // 工具名可见（卡体标题 + 参数区上下文）。
    expect(wrapper.text()).toContain('delete_record')
    // 参数 JSON 格式化（与 timeline 展开体同一 2 空格缩进格式，字面量独立于实现）。
    expect(wrapper.find('[data-testid="approval-args"]').text()).toBe('{\n  "record": "stale-14"\n}')
    // scope 默认 once。
    expect(wrapper.find('[data-testid="approval-scope-once"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.find('[data-testid="approval-scope-session"]').attributes('aria-checked')).toBe('false')
    // 阻断优先：运行被阻断的提示行醒目可见。
    expect(wrapper.find('[data-testid="approval-blocked"]').text()).toContain('阻断')
    // 语义严格分离：这是工具授权，不是问卷作答（旧 ApprovalCard 文案基调）。
    expect(wrapper.text()).toContain('这是工具授权')
    expect(wrapper.text()).toContain('不是问卷作答')
    expect(wrapper.text()).toContain('尚未执行')
    // 等待状态徽标（header-extra）。
    expect(wrapper.find('[data-testid="approval-wait"]').text()).toBe('等待审批')
  })

  it('scope_options 只给 once 时只渲染一个选项且默认选中', () => {
    const wrapper = mount(ApprovalCard, {
      props: { entry: approvalEntry({ scopeOptions: ['once'] }) },
    })
    expect(wrapper.find('[data-testid="approval-scope-once"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="approval-scope-session"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="approval-scope-once"]').attributes('aria-checked')).toBe('true')
  })
})

describe('ApprovalCard 批准提交', () => {
  it('默认 scope=once，提交参数为 approve + once', async () => {
    const wrapper = mount(ApprovalCard, { props: { entry: approvalEntry() } })
    await wrapper.find('[data-testid="approval-approve"]').trigger('click')
    expect(wrapper.emitted('submit')).toEqual([['approve', 'once']])
  })

  it('scope 切换到 session 后随决定一并提交', async () => {
    const wrapper = mount(ApprovalCard, { props: { entry: approvalEntry() } })
    await wrapper.find('[data-testid="approval-scope-session"]').trigger('click')
    expect(wrapper.find('[data-testid="approval-scope-session"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.find('[data-testid="approval-scope-once"]').attributes('aria-checked')).toBe('false')
    await wrapper.find('[data-testid="approval-approve"]').trigger('click')
    expect(wrapper.emitted('submit')).toEqual([['approve', 'session']])
  })

  it('拒绝提交 reject + 当前 scope', async () => {
    const wrapper = mount(ApprovalCard, { props: { entry: approvalEntry() } })
    await wrapper.find('[data-testid="approval-scope-session"]').trigger('click')
    await wrapper.find('[data-testid="approval-reject"]').trigger('click')
    expect(wrapper.emitted('submit')).toEqual([['reject', 'session']])
  })
})

describe('ApprovalCard 决策后只读回显', () => {
  it('rejected 呈现「已拒绝且未执行」明确态：无批准/拒绝入口', () => {
    const wrapper = mount(ApprovalCard, {
      props: { entry: approvalEntry({ status: 'rejected', scope: 'once' }) },
    })
    // 卡片整体呈现「已拒绝」（头部状态徽标）且「未执行」（回显行，旧文案基调）。
    expect(wrapper.text()).toContain('已拒绝')
    expect(wrapper.find('[data-testid="approval-echo"]').text()).toContain('未执行')
    expect(wrapper.find('[data-testid="approval-approve"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="approval-reject"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="approval-scope"]').exists()).toBe(false)
  })

  it('approved 回显决定与 scope；cancelled 同样是非执行态', () => {
    const approved = mount(ApprovalCard, {
      props: { entry: approvalEntry({ status: 'approved', scope: 'session' }) },
    })
    expect(approved.find('[data-testid="approval-echo"]').text()).toContain('已批准')
    expect(approved.find('[data-testid="approval-echo"]').text()).toContain('本会话')
    expect(approved.find('[data-testid="approval-echo"]').text()).not.toContain('未执行')

    const cancelled = mount(ApprovalCard, {
      props: { entry: approvalEntry({ status: 'cancelled' }) },
    })
    expect(cancelled.find('[data-testid="approval-echo"]').text()).toContain('已取消')
    expect(cancelled.find('[data-testid="approval-echo"]').text()).toContain('未执行')
  })
})

describe('ApprovalCard 提交中禁用', () => {
  it('submitting 时批准/拒绝/scope 全部禁用，批准按钮显示提交中文案', () => {
    const wrapper = mount(ApprovalCard, {
      props: { entry: approvalEntry({ submitting: true }) },
    })
    expect(wrapper.find('[data-testid="approval-approve"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="approval-reject"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="approval-scope-once"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="approval-scope-session"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="approval-approve"]').text()).toContain('正在提交')
  })
})

describe('ApprovalCard 保存态恢复直接可操作', () => {
  it('恢复的 waiting 卡（scope_options 来自保存态）按钮可用，点批准即 emit', async () => {
    // 形状对齐 eventsFromSavedState 产出的 entry：scopeOptions 来自 pending.scope_options。
    const wrapper = mount(ApprovalCard, { props: { entry: approvalEntry() } })
    expect(wrapper.find('[data-testid="approval-approve"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="approval-reject"]').attributes('disabled')).toBeUndefined()
    await wrapper.find('[data-testid="approval-scope-session"]').trigger('click')
    await wrapper.find('[data-testid="approval-approve"]').trigger('click')
    expect(wrapper.emitted('submit')).toEqual([['approve', 'session']])
  })

  it('无 scopeOptions 的旧条目回退为 once/session 两项，默认 once', async () => {
    const wrapper = mount(ApprovalCard, {
      props: { entry: approvalEntry({ scopeOptions: undefined }) },
    })
    expect(wrapper.find('[data-testid="approval-scope-once"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="approval-scope-session"]').exists()).toBe(true)
    await wrapper.find('[data-testid="approval-approve"]').trigger('click')
    expect(wrapper.emitted('submit')).toEqual([['approve', 'once']])
  })
})
