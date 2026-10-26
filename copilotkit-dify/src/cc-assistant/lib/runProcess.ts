import type { Message, ToolCall } from '@ag-ui/core'
import type { InterruptQuestion } from './question'

export type RunProcessDisplayMode = 'expanded' | 'collapsed'

export interface RunProcessDisplayConfig {
  autoCollapseCompletedRuns: boolean
  defaultProcessExpandedWhileRunning: boolean
  durationMsByGroupId: Record<string, number>
}

export interface RunProcessInterruptState {
  result?: InterruptQuestion | null
  resolve?: (payload: unknown) => void
}

export interface RunProcessGroup {
  id: string
  userMessages: Message[]
  processMessages: Message[]
  toolResultMessages: Message[]
  finalAssistantMessages: Message[]
  summary: string
  isRunning: boolean
  isComplete: boolean
  processDisplay: RunProcessDisplayMode
  defaultExpanded: boolean
  hasActiveInterrupt: boolean
}

export const defaultRunProcessDisplayConfig: RunProcessDisplayConfig = {
  autoCollapseCompletedRuns: true,
  defaultProcessExpandedWhileRunning: true,
  durationMsByGroupId: {},
}

interface WorkingGroup {
  id: string
  userMessages: Message[]
  runMessages: Message[]
  toolResultMessages: Message[]
  hasActiveInterrupt?: boolean
}

export function buildRunProcessGroups(
  messages: Message[] = [],
  isRunning = false,
  interruptState: RunProcessInterruptState | null = null,
  config: Partial<RunProcessDisplayConfig> = {},
): RunProcessGroup[] {
  const displayConfig = {
    ...defaultRunProcessDisplayConfig,
    ...config,
  }
  const groups: WorkingGroup[] = []
  let current: WorkingGroup | null = null

  const ensureGroup = () => {
    if (!current) {
      current = createWorkingGroup(`run:${groups.length + 1}`)
      groups.push(current)
    }
    return current
  }

  for (const message of messages || []) {
    const role = messageRole(message)
    if (role === 'user') {
      current = createWorkingGroup(`run:${message.id || groups.length + 1}`)
      current.userMessages.push(message)
      groups.push(current)
      continue
    }

    const group = ensureGroup()
    if (role === 'tool') {
      group.toolResultMessages.push(message)
    } else {
      group.runMessages.push(message)
    }
  }

  if (interruptState?.result) {
    const group = groups[groups.length - 1] || ensureGroup()
    group.hasActiveInterrupt = true
  }

  return groups.map((group, index) => finalizeGroup(group, index, groups.length, isRunning, displayConfig))
}

function createWorkingGroup(id: string): WorkingGroup {
  return {
    id,
    userMessages: [],
    runMessages: [],
    toolResultMessages: [],
  }
}

function finalizeGroup(
  group: WorkingGroup,
  index: number,
  groupCount: number,
  isRunning: boolean,
  config: RunProcessDisplayConfig,
): RunProcessGroup {
  const isLatest = index === groupCount - 1
  const groupRunning = Boolean(isRunning && isLatest)
  const hasActiveInterrupt = Boolean(group.hasActiveInterrupt)
  const finalAnswerIndex = findLastFinalAssistantIndex(group.runMessages)
  const finalAssistantMessages = finalAnswerIndex >= 0 ? [group.runMessages[finalAnswerIndex]] : []
  const processMessages = finalAnswerIndex >= 0
    ? group.runMessages.filter((_, messageIndex) => messageIndex !== finalAnswerIndex)
    : group.runMessages.slice()
  const isComplete = finalAssistantMessages.length > 0 && !hasActiveInterrupt
  const processDisplay: RunProcessDisplayMode = isComplete && config.autoCollapseCompletedRuns
    ? 'collapsed'
    : 'expanded'
  const defaultExpanded = processDisplay === 'expanded'
    ? Boolean(hasActiveInterrupt || config.defaultProcessExpandedWhileRunning || processMessages.length > 0)
    : false

  return {
    id: group.id,
    userMessages: group.userMessages,
    processMessages,
    toolResultMessages: group.toolResultMessages,
    finalAssistantMessages,
    summary: processSummary(
      processMessages,
      group.toolResultMessages,
      hasActiveInterrupt,
      isComplete,
      config.durationMsByGroupId[group.id] || 0,
    ),
    isRunning: groupRunning,
    isComplete,
    processDisplay,
    defaultExpanded,
    hasActiveInterrupt,
  }
}

function findLastFinalAssistantIndex(messages: Message[]) {
  let lastProcessBoundary = -1
  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index]
    const role = messageRole(message)
    if (role === 'reasoning' || role === 'activity' || assistantToolCalls(message).length > 0) {
      lastProcessBoundary = index
    }
  }

  for (let index = messages.length - 1; index > lastProcessBoundary; index -= 1) {
    const message = messages[index]
    if (
      messageRole(message) === 'assistant'
      && assistantToolCalls(message).length === 0
      && assistantHasFinalContent(message)
    ) return index
  }
  return -1
}

function processSummary(
  processMessages: Message[],
  toolResultMessages: Message[],
  hasActiveInterrupt: boolean,
  isComplete: boolean,
  fallbackDurationMs = 0,
) {
  const parts: string[] = []
  const durationMs = processDurationMs(processMessages, toolResultMessages) || fallbackDurationMs
  const prefix = isComplete ? '已处理' : '处理中'
  parts.push(durationMs > 0 ? `${prefix} ${formatDuration(durationMs)}` : prefix)

  const toolCount = countToolCalls(processMessages)
  const generatedFiles = countGeneratedFiles(processMessages)
  const stepCount = countVisibleSteps(processMessages, hasActiveInterrupt)
  if (toolCount > 0) parts.push(`调用 ${toolCount} 个工具`)
  if (generatedFiles > 0) parts.push(`生成 ${generatedFiles} 个文件`)
  parts.push(`${stepCount} 步`)
  return parts.join(' · ')
}

function countToolCalls(messages: Message[]) {
  const ids = new Set<string>()
  for (const message of messages) {
    for (const toolCall of assistantToolCalls(message)) {
      ids.add(toolCall.id || `${toolCall.function?.name || 'tool'}:${ids.size}`)
    }
  }
  return ids.size
}

function countVisibleSteps(messages: Message[], hasActiveInterrupt: boolean) {
  let count = hasActiveInterrupt ? 1 : 0
  for (const message of messages) {
    const role = messageRole(message)
    if (role === 'assistant') {
      const toolCalls = assistantToolCalls(message)
      count += toolCalls.length
      if (assistantHasFinalContent(message)) count += 1
      continue
    }
    if (role === 'reasoning' || role === 'activity') count += 1
  }
  return count
}

function countGeneratedFiles(messages: Message[]) {
  return messages
    .filter((message) => messageRole(message) === 'activity')
    .reduce((count, message) => {
      const activityType = stringValue((message as any).activityType)
      if (
        activityType !== 'cc_agent.workspace' &&
        activityType !== 'cc_agent.skill_artifact' &&
        activityType !== 'cc_agent.uploaded_files'
      ) {
        return count
      }
      const files = filesFromContent(contentObject((message as any).content))
      return count + files.length
    }, 0)
}

function processDurationMs(processMessages: Message[], toolResultMessages: Message[]) {
  const values = [...processMessages, ...toolResultMessages]
    .map((message) => messageTime(message))
    .filter((value) => value > 0)
  if (values.length < 2) return 0
  return Math.max(0, Math.max(...values) - Math.min(...values))
}

function formatDuration(durationMs: number) {
  const seconds = Math.max(1, Math.round(durationMs / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`
}

function messageRole(message: Message) {
  return stringValue((message as any).role)
}

function textContent(message: Message) {
  return textFromValue((message as any).content)
}

function textFromValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value
      .map((part) => {
        if (part && typeof part === 'object' && (part as any).type === 'text') return stringValue((part as any).text)
        return ''
      })
      .filter(Boolean)
      .join('\n')
  }
  return safeHumanText(value)
}

function assistantToolCalls(message: Message): ToolCall[] {
  const toolCalls = (message as any).toolCalls || (message as any).tool_calls || []
  return Array.isArray(toolCalls) ? toolCalls : []
}

function assistantHasFinalContent(message: Message) {
  return textContent(message).trim().length > 0
}

function messageTime(message?: Message) {
  if (!message) return 0
  const source = message as any
  return timeValue(source.createdAt || source.created_at || source.timestamp || source.time || source.startedAt || source.started_at)
}

function contentObject(value: unknown): Record<string, any> {
  const parsed = parseMaybeJson(value)
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as Record<string, any>
  return { message: stringValue(parsed) }
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== 'string') return value
  const text = value.trim()
  if (!text) return ''
  if (!text.startsWith('{') && !text.startsWith('[')) return text
  try {
    return JSON.parse(text)
  } catch (_) {
    return text
  }
}

function safeHumanText(value: unknown, maxLength = 420): string {
  const text = typeof value === 'string' ? value : stringifySafe(value)
  return text.replace(/\s+/g, ' ').trim().slice(0, maxLength)
}

function stringifySafe(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch (_) {
    return String(value)
  }
}

function stringValue(value: unknown) {
  return value == null ? '' : String(value)
}

function filesFromContent(content: Record<string, any>) {
  const rawFiles = Array.isArray(content.files)
    ? content.files
    : Array.isArray(content.artifacts)
      ? content.artifacts
      : []
  return rawFiles
    .map((file: any, index: number) => stringValue(file?.name || file?.filename || file?.path || file?.workspace_path || `file-${index + 1}`))
    .filter(Boolean)
}

function timeValue(value: unknown) {
  if (!value) return 0
  if (value instanceof Date) return value.getTime()
  if (typeof value === 'number') return value
  const parsed = Date.parse(String(value))
  return Number.isFinite(parsed) ? parsed : 0
}
