export type AssistantCatalogItemKind = 'command' | 'skill'

export interface AssistantCommand {
  kind: 'command'
  name: string
  label: string
  description: string
  message: string
}

export interface AssistantSkill {
  kind: 'skill'
  name: string
  label: string
  description: string
  category: string
  icon?: AssistantIconName
}

export interface SuggestedQuestion {
  title: string
  message: string
}

export interface AssistantCatalog {
  commands: AssistantCommand[]
  skills: AssistantSkill[]
  suggestedQuestions: SuggestedQuestion[]
}

export type AssistantSlashEntry = AssistantCommand | AssistantSkill
export const ASSISTANT_ICON_NAMES = [
  'file-text',
  'chart',
  'mail',
  'pen',
  'target',
  'feedback',
  'checklist',
  'skill',
] as const
export type AssistantIconName = typeof ASSISTANT_ICON_NAMES[number]

declare global {
  interface Window {
    CC_AGENT_HOME_CATALOG?: unknown
  }
}

export const defaultAssistantCatalog: AssistantCatalog = normalizeAssistantCatalog({
  skills: [
    {
      name: 'leadership-team-analysis',
      label: '班子分析',
      description: '围绕指定单位班子结构、履职表现和风险短板生成综合分析',
      category: '分析',
      icon: 'chart',
    },
    {
      name: 'personnel-comparison',
      label: '人员对比',
      description: '对多名人员的经历、能力、绩效和适配度进行横向对比',
      category: '对比',
      icon: 'checklist',
    },
    {
      name: 'role-fit-analysis',
      label: '人岗匹配',
      description: '根据岗位要求或人员画像，分析人找岗、岗找人的匹配建议',
      category: '研判',
      icon: 'target',
    },
    {
      name: 'policy-research',
      label: '政策研究',
      description: '围绕指定方向梳理政策依据、管理口径和研究要点',
      category: '研究',
      icon: 'file-text',
    },
    {
      name: 'advanced-talent-search',
      label: '高级检索',
      description: '把复杂筛选条件整理为人员检索、统计分析或数据查询思路',
      category: '检索',
      icon: 'target',
    },
    {
      name: 'text-proofreading',
      label: '文字校对',
      description: '检查错别字、表述不顺和格式问题，输出修改建议',
      category: '工具',
      icon: 'pen',
    },
  ],
  commands: [
    { name: 'help', label: '查看帮助', description: '列出当前可用命令和技能' },
    { name: 'status', label: '会话状态', description: '查看当前会话运行状态' },
    { name: 'context', label: '查看上下文', description: '检查当前会话上下文和 token 使用' },
    { name: 'compact', label: '压缩上下文', description: '强制压缩当前对话历史' },
    { name: 'reset', label: '重置上下文', description: '清空当前会话上下文' },
  ],
  suggestedQuestions: [
    '帮我分析这个单位班子的结构特点和风险短板',
    '帮我对比这几名人员的优势、短板和适配方向',
    '帮我根据岗位要求判断候选人的匹配度',
  ],
})

export function normalizeAssistantCatalog(input: unknown): AssistantCatalog {
  const raw = isRecord(input) ? input : {}
  return {
    commands: normalizeCommands(raw.commands),
    skills: normalizeSkills(raw.skills),
    suggestedQuestions: normalizeSuggestedQuestions(raw.suggestedQuestions),
  }
}

export function slashEntriesFromCatalog(catalog: AssistantCatalog): AssistantSlashEntry[] {
  return [
    ...(catalog.commands || []),
    ...(catalog.skills || []),
  ]
}

export function resolveAssistantCatalog(input: unknown): AssistantCatalog {
  return withFallback(input)
}

export async function loadAssistantCatalog(): Promise<AssistantCatalog> {
  if (typeof window !== 'undefined' && window.CC_AGENT_HOME_CATALOG) {
    return withFallback(window.CC_AGENT_HOME_CATALOG)
  }

  if (typeof fetch !== 'function') return defaultAssistantCatalog

  try {
    const response = await fetch('/cc-agent-home-catalog.json', { cache: 'no-store' })
    if (!response.ok) return defaultAssistantCatalog
    return withFallback(await response.json())
  } catch (_) {
    return defaultAssistantCatalog
  }
}

function withFallback(input: unknown) {
  const raw = isRecord(input) ? input : {}
  const normalized = normalizeAssistantCatalog(input)
  return {
    commands: normalized.commands.length ? normalized.commands : defaultAssistantCatalog.commands,
    skills: normalized.skills.length ? normalized.skills : defaultAssistantCatalog.skills,
    suggestedQuestions: Object.prototype.hasOwnProperty.call(raw, 'suggestedQuestions')
      ? normalized.suggestedQuestions
      : defaultAssistantCatalog.suggestedQuestions,
  }
}

function normalizeCommands(input: unknown): AssistantCommand[] {
  if (!Array.isArray(input)) return []
  return input.map((item) => {
    const raw = isRecord(item) ? item : {}
    const name = cleanName(raw.name)
    if (!name) return null
    const message = cleanString(raw.message) || `/${name}`
    return {
      kind: 'command' as const,
      name,
      label: cleanString(raw.label) || `/${name}`,
      description: cleanString(raw.description),
      message: message.startsWith('/') ? message : `/${message}`,
    }
  }).filter(Boolean) as AssistantCommand[]
}

function normalizeSkills(input: unknown): AssistantSkill[] {
  if (!Array.isArray(input)) return []
  return input.map((item) => {
    const raw = isRecord(item) ? item : {}
    const name = cleanName(raw.name)
    if (!name) return null
    return {
      kind: 'skill' as const,
      name,
      label: cleanString(raw.label) || name,
      description: cleanString(raw.description),
      category: cleanString(raw.category) || '技能',
      icon: cleanIcon(raw.icon),
    }
  }).filter(Boolean) as AssistantSkill[]
}

function normalizeSuggestedQuestions(input: unknown): SuggestedQuestion[] {
  if (!Array.isArray(input)) return []
  return input.map((item) => {
    if (typeof item === 'string') {
      const text = item.trim()
      return text ? { title: text, message: text } : null
    }
    const raw = isRecord(item) ? item : {}
    const message = cleanString(raw.message)
    if (!message) return null
    return {
      title: cleanString(raw.title) || message,
      message,
    }
  }).filter(Boolean) as SuggestedQuestion[]
}

function cleanName(value: unknown) {
  return cleanString(value).replace(/^\/+/, '').trim()
}

function cleanString(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function cleanIcon(value: unknown) {
  return normalizeAssistantIcon(cleanString(value).replace(/[^a-z0-9_-]/gi, '').toLowerCase())
}

export function normalizeAssistantIcon(value: unknown): AssistantIconName {
  const icon = cleanString(value).replace(/[^a-z0-9_-]/gi, '').toLowerCase()
  return ASSISTANT_ICON_NAMES.includes(icon as AssistantIconName) ? icon as AssistantIconName : 'skill'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
