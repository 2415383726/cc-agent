const STATUS: Record<string, string> = {
  idle: '空闲',
  running: '运行中',
  stopping: '停止中',
  completed: '已完成',
  awaiting_user: '等待回答',
  awaiting_approval: '等待审批',
  failed: '失败',
  stopped: '已停止',
  budget_exhausted: '预算耗尽',
  context_overflow: '上下文溢出',
  context_too_large: '上下文过大',
  state_save_failed: '状态保存失败',
  cancelled: '已取消',
  unknown: '未确认',
  waiting: '等待处理',
  answered: '已回答',
  approved: '已批准',
  rejected: '已拒绝',
  'awaiting user': '等待回答',
  'awaiting approval': '等待审批',
}

const ERRORS: Record<string, string> = {
  agent_failed: 'Agent 运行失败。',
  invalid_state: '保存的会话状态无效。',
  state_save_failed: '状态保存失败，上一轮状态已保留。',
  state_too_large: '状态过大，无法安全保存。',
  context_too_large: '固定提示内容超过模型上下文窗口。',
  context_overflow: '上下文超过模型窗口，恢复失败。',
  budget_exhausted: '本轮执行预算已耗尽。',
  pending_invalid: '答复与当前等待的交互不匹配。',
  pending_expired: '等待的交互已过期。',
  pending_consumed: '该交互已经答复过。',
  approval_rejected: '操作已被拒绝，未执行。',
  approval_unknown: '外部操作结果未知，请先核实。',
  tool_failed: '工具执行失败。',
  tool_unknown: '工具不可用。',
  provider_failed: '模型服务失败。',
  stream_failed: '流式响应失败。',
  stopped_unconfirmed: '已请求停止，但服务器未确认终态。',
  transport_failed: 'Dify 请求失败，未收到可信终态。',
  unknown: '没有可信的终态，结果未确认。',
}

export function statusText(status: string): string {
  return STATUS[status] || status
}

export function errorText(code: string | undefined, fallback: string): string {
  return (code && ERRORS[code]) || fallback
}

export function toolStatusText(status: string): string {
  const labels: Record<string, string> = {
    running: '运行中',
    ok: '已完成',
    completed: '已完成',
    error: '失败',
    failed: '失败',
    unknown: '结果未知',
    not_executed: '未执行',
    awaiting_user: '等待回答',
    awaiting_approval: '等待审批',
    stopped: '已停止',
  }
  return labels[status] || status
}
