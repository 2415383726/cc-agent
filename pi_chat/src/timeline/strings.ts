/**
 * 时间线中文文案。字符串逐字取自上游 ui-chat/src/client/locale.ts 的 zh 字典
 * （MIT），并引用 packages/client/locale zh.ts 的 copy/copied；
 * 已复制反馈文案按票据措辞。终态徽标复用 projection/labels.ts 的 statusText。
 */
export const STRINGS = {
  copy: '复制',
  copied: '已复制',
  /** locale.ts: message.think */
  think: '思考',
  /** locale.ts: message.turnProcess.took（后接时长片段） */
  turnProcessTook: '已完成，用时 ',
  /** locale.ts: message.stopped */
  stopped: '已停止',
  /** locale.ts: chat.deepDiving / chat.deepDivingFor */
  deepDiving: '深度求索中',
  deepDivingFor: '深度求索中，用时 {duration} ···',
  /** locale.ts: duration.*Unit */
  hourUnit: '小时',
  minuteUnit: '分',
  secondUnit: '秒',
  /** locale.ts: clock.md / clock.ymd（message-chrome 的时钟模板） */
  clockMd: '{m}月{d}日',
  clockYmd: '{y}年{m}月{d}日',
  codeCopy: '复制代码',
} as const
