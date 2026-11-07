/**
 * 工具行纯函数模型。平移上游 ui-tool tool/models/tool-call-model.ts（MIT）
 * 的子集：variant 分类表、摘要派生（deriveSummary/pickString/firstLine）、
 * 参数展开体格式化（formatToolBody）。上游以流式 PartialArguments 读取
 * 「仅已确定的参数片段」；本契约的 DisplayEvent 在 tool.start 携带完整
 * arguments 对象，故以该对象为输入、语义不变（非对象/缺失时回退原样文本）。
 * 偏离：文件路径链接（filePath/fileTargets/openFile）、inspect、patch 解析、
 * recorded-path 元数据不在本契约事件面内，全部省略——summary 恒为纯文本。
 */
import type { ToolEntry } from '../projection/transcript'
import type { ToolStatus } from '../projection/transcript'
import { TOOL_STRINGS } from './strings'

/** 工具行变体（上游 ToolRowVariant）。 */
export type ToolRowVariant = 'search' | 'read' | 'bash' | 'write' | 'edit' | 'code' | 'others'

/** 行生命周期状态（上游 ToolRowState；preparing 不在本契约事件面内）。 */
export type ToolRowState = 'running' | 'ok' | 'error' | 'stopped'

/** 上游 TOOL_VARIANTS：已知工具名 → 变体，未知落 others。 */
const TOOL_VARIANTS: Record<string, ToolRowVariant> = {
  bash: 'bash',
  pwsh: 'bash',
  read: 'read',
  read_image: 'read',
  web_fetch: 'read',
  web_search: 'search',
  grep: 'search',
  glob: 'search',
  write: 'write',
  edit: 'edit',
  apply_patch: 'edit',
  run_code: 'code',
}

/** 变体 → zh 标题（ui-conversation locales.ts tool.title.*）。 */
const VARIANT_TITLES: Record<ToolRowVariant, string> = {
  search: TOOL_STRINGS.titleSearch,
  read: TOOL_STRINGS.titleRead,
  bash: TOOL_STRINGS.titleBash,
  write: TOOL_STRINGS.titleWrite,
  edit: TOOL_STRINGS.titleEdit,
  code: TOOL_STRINGS.titleCode,
  others: TOOL_STRINGS.titleGeneric,
}

/** 上游 SUMMARY_KEYS：每个变体的摘要参数键优先级。 */
const SUMMARY_KEYS: Record<ToolRowVariant, readonly string[]> = {
  bash: ['description', 'command'],
  read: ['path', 'file_path', 'url'],
  search: ['query', 'pattern', 'url'],
  write: ['path', 'file_path'],
  edit: ['path', 'file_path'],
  code: ['description'],
  others: [],
}

/** 按上游 classifyTool：查表命中否则 others。 */
export function classifyTool(toolName: string): ToolRowVariant {
  return TOOL_VARIANTS[toolName] ?? 'others'
}

/** zh 变体标题；通用工具 titled 工具调用。 */
export function toolTitle(toolName: string): string {
  return VARIANT_TITLES[classifyTool(toolName)]
}

function firstLine(text: string): string {
  const newline = text.indexOf('\n')
  return newline === -1 ? text : text.slice(0, newline)
}

function pickString(args: Record<string, unknown>, keys: readonly string[]): string | undefined {
  for (const key of keys) {
    const value = args[key]
    if (typeof value === 'string' && value !== '') return value
  }
  return undefined
}

/**
 * 上游 deriveSummary 的对象输入版：变体摘要键优先，否则首个非空字符串值，
 * 再否则（无可用参数）空串。通用工具的摘要由调用方前置工具名拼接。
 */
function deriveSummary(variant: ToolRowVariant, args: Record<string, unknown>): string {
  if (variant === 'search' && Array.isArray(args.queries)) {
    const queries = args.queries.filter((query): query is string => typeof query === 'string' && query !== '')
    if (queries.length > 0) return queries.map(firstLine).join(', ')
  }
  const picked = pickString(args, SUMMARY_KEYS[variant])
  if (picked !== undefined) return firstLine(picked)
  for (const value of Object.values(args)) {
    if (typeof value === 'string' && value !== '') return firstLine(value)
  }
  return ''
}

/**
 * 折叠行摘要（上游 toolRowModel 的 summary 组装）：
 * 通用变体摘要 = `工具名 · 参数摘要`，已知变体只保留参数摘要；
 * 无可用参数时（如尚未流出的片段）回落为纯工具名。
 */
export function toolSummary(entry: ToolEntry): string {
  const variant = classifyTool(entry.name)
  const args = entry.args
  const base =
    args !== null && typeof args === 'object' && !Array.isArray(args)
      ? deriveSummary(variant, args as Record<string, unknown>)
      : args === undefined || args === null ? '' : firstLine(String(args))
  const generic = variant === 'others'
  return [generic ? entry.name : '', base].filter(Boolean).join(' · ') || entry.name
}

/**
 * 展开时格式化参数体（上游 formatToolBody）：对象 → 两空格缩进 JSON；
 * 非对象原样文本；缺失 → null（无输入区）。PartialArguments 语义保持：
 * 参数视图里只有已确定的片段参与格式化。
 */
export function formatToolBody(variant: ToolRowVariant, args: unknown): string | null {
  if (args === undefined || args === null || args === '') return null
  if (typeof args === 'object') {
    // code 变体的展开体是程序本身（上游：剥掉 args JSON 信封取 code 字段）。
    if (variant === 'code') {
      const code = (args as Record<string, unknown>).code
      if (typeof code === 'string' && code !== '') return code
    }
    return JSON.stringify(args, null, 2)
  }
  return String(args)
}

/**
 * 投影 ToolStatus → 行状态（上游 state 推导的契约版）：
 * 运行族（running/awaiting_user/awaiting_approval）→ running；
 * stopped/not_executed/unknown → stopped（上游无 unknown 态，按中断警示处理，
 * 徽标文案仍区分「结果未知/未执行」）。
 */
export function toolRowState(status: ToolStatus): ToolRowState {
  if (status === 'ok' || status === 'completed') return 'ok'
  if (status === 'running' || status === 'awaiting_user' || status === 'awaiting_approval') return 'running'
  if (status === 'error' || status === 'failed') return 'error'
  return 'stopped'
}
