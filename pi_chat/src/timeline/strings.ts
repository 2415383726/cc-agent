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

/*
 * 工具/技能时间线文案（票据 04）。逐字取自上游 locale zh 字典：
 * - ui-conversation/src/client/locales.ts：tool.title.*、row.input/output/running/failed/stopped
 * - ui-chat/src/client/locale.ts：message.stepProcess.*（分组头标题）、message.compaction.*
 * - ui-skill/src/client/locales.ts：skill row.title/instructions
 */
export const TOOL_STRINGS = {
  /** ui-conversation locales.ts: tool.title.* */
  titleSearch: '搜索',
  titleRead: '读取',
  titleBash: '运行命令',
  titleWrite: '写入',
  titleEdit: '编辑',
  titleCode: '代码',
  titleGeneric: '工具调用',
  /** ui-conversation locales.ts: row.input / row.output */
  input: '输入',
  output: '输出',
  /** ui-conversation locales.ts: row.running / row.failed / row.stopped（无障碍隐藏态文案） */
  rowRunning: '运行中',
  rowFailed: '失败',
  rowStopped: '已停止',
} as const

/** ui-chat locale.ts: message.stepProcess.done.*（闭合分组标题类别词）。 */
export const PROCESS_DONE: Record<string, string> = {
  read: '已读取文件',
  readImage: '已读取图片',
  write: '已写入文件',
  search: '已搜索代码',
  edit: '修改了文件',
  commands: '执行了命令',
  code: '运行了代码',
  webSearch: '已搜索网页',
  webFetch: '已访问网页',
  subagents: '已协调子智能体',
  plan: '更新了计划',
  questions: '向用户提出了问题',
  tools: '已调用工具',
  thinking: '已完成分析',
}

/** ui-chat locale.ts: message.stepProcess.*（进行中分组标题类别词）。 */
export const PROCESS_LIVE: Record<string, string> = {
  thinking: '正在分析请求',
  read: '正在读取文件',
  readImage: '正在读取图片',
  write: '正在写入文件',
  search: '正在搜索代码',
  edit: '正在编辑文件',
  commands: '正在运行命令',
  code: '正在运行代码',
  webSearch: '正在搜索网页',
  webFetch: '正在访问网页',
  subagents: '正在协调子智能体',
  plan: '正在更新计划',
  questions: '等待你的操作',
  tools: '正在调用工具',
}

/** ui-chat locale.ts: message.stepProcess.joinTwo/comma/sharedPrefix/more。 */
export const PROCESS_JOIN = {
  joinTwo: '{first}并{second}',
  comma: '，',
  sharedPrefix: '已',
  more: '{title}等',
} as const

/** ui-skill locales.ts: skill 命名空间（技能行）。 */
export const SKILL_STRINGS = {
  title: '加载技能',
  running: '正在加载 skill',
  instructions: '说明',
} as const

/** ui-chat locale.ts: message.compaction.*（压缩行）。 */
export const COMPACTION_STRINGS = {
  title: '上下文已压缩',
  running: '正在压缩…',
} as const
