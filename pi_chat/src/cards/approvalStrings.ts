/**
 * 审批卡中文文案。基调逐字沿用旧 pi_workbench ApprovalCard.vue 的语义基线
 * （「这是工具授权，不是问卷作答」、授权范围两值、拒绝后的非执行态回显）；
 * 阻断提示行与提交中文案为本票据新增（票据 06 DoD：阻断优先、提交中禁用）。
 * 上游 ui-user-questions locales.ts 的 `plan.*` 是计划评审语义（同意执行/
 * 要求修改），与工具授权不是同一待交互类型，不引入。
 */
export const APPROVAL_STRINGS = {
  eyebrow: '工具授权审批',
  blocked: '运行已被阻断：等待你对此工具调用的授权决定。',
  title: '需要审批：{tool}',
  authorization: '这是工具授权，不是问卷作答。该操作尚未执行。',
  argsLabel: '操作参数',
  sourceLabel: '来源',
  callLabel: '调用',
  scopeLabel: '授权范围',
  scopeOnce: '仅本次操作',
  scopeSession: '本会话内该工具',
  scopeHint: '批准后会重新检查当前工具、策略和预算。会话授权不会绕过服务端权限。',
  approve: '批准',
  reject: '拒绝',
  submitting: '正在提交…',
  echoApproved: '操作已批准（{scope}），结果显示在对话中。',
  echoScopeOnce: '仅本次',
  echoScopeSession: '本会话范围',
  echoRejected: '操作已被拒绝，未执行。',
  echoCancelled: '审批已取消，操作未执行。',
} as const

export function approvalString(key: keyof typeof APPROVAL_STRINGS, vars?: Record<string, string | number>): string {
  let text: string = APPROVAL_STRINGS[key]
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value))
    }
  }
  return text
}
