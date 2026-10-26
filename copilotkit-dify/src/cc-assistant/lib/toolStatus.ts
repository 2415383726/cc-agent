export type ToolDisplayState = 'pending' | 'executing' | 'complete' | 'waiting_permission'

export function toolDisplayState(status: string, result?: string): ToolDisplayState {
  if (isPermissionWaitingResult(result)) return 'waiting_permission'
  if (status === 'executing') return 'executing'
  if (status === 'complete') return 'complete'
  return 'pending'
}

export function toolDisplayLabel(status: string, result?: string, labels: Partial<Record<ToolDisplayState, string>> = {}) {
  const state = toolDisplayState(status, result)
  const defaults: Record<ToolDisplayState, string> = {
    pending: '准备中',
    executing: '执行中',
    complete: '已完成',
    waiting_permission: '等待授权',
  }
  return labels[state] || defaults[state]
}

function isPermissionWaitingResult(result?: string) {
  const text = String(result || '').toLowerCase()
  return (
    text.includes('requires user permission') ||
    text.includes('requires your permission') ||
    text.includes('permission_required')
  )
}
