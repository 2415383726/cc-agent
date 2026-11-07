/**
 * 问卷卡中文文案。字符串逐字取自上游 ui-user-questions/src/client/locales.ts
 * 的 zh 字典（MIT）；`submit`/`submitting` 取自 packages/client/locale zh 字典
 * （QuestionComposer 引用的共享键）。上游 `plan.*`（计划评审呈现）属票据 06
 * 语义，此处不引入；`error.resubmit`/`wait.continued` 属上游 waterfall 续聊
 * 通道文案，本应用通道是 controller，没有对应状态，一并裁剪。
 */
export const QUESTION_STRINGS = {
  errorIncomplete: '请先完成这道问题。',
  errorUnanswered: '请选择一个选项或填写自定义答案。',
  errorUnavailable: '当前无法提交，请稍候再试。',
  waitTakeTime: '慢慢回答',
  waitCountdown: '{seconds} 秒后继续工作',
  waitPaused: '已暂停 · 剩余 {seconds} 秒',
  waitHeld: '会一直等你回答',
  reviewSkipped: '这道问题当时被跳过。',
  navPrev: '上一题',
  navNext: '下一题',
  navMinimize: '收起问题卡片',
  navMaximize: '展开问题卡片',
  navCancel: '放弃整组问题',
  textExpand: '展开',
  textCollapse: '收起',
  optionRecommended: '推荐',
  customPlaceholder: '输入你的答案',
  actionSkip: '跳过',
  actionNext: '下一题',
  submit: '提交',
  submitting: '正在提交…',
  /** 本应用扩展（上游无 min/max 约束；文案对齐 pi_dify 服务端校验语义）。 */
  errorMinSelections: '至少选择 {min} 项。',
  errorMaxSelections: '最多选择 {max} 项。',
} as const

export function questionString(key: keyof typeof QUESTION_STRINGS, vars?: Record<string, string | number>): string {
  let text: string = QUESTION_STRINGS[key]
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value))
    }
  }
  return text
}
