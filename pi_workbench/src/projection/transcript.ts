import { DisplayEvent, normalizeAnswer, sameAnswer, terminalStatus } from '../contract/display'

export interface FileRef {
  id?: string
  name?: string
  mime_type?: string
  mimeType?: string
  size?: number
  type?: string
  url?: string
}

export interface QuestionOption {
  id: string
  label: string
  description?: string
}

export interface Question {
  id: string
  question: string
  header?: string
  type: 'single' | 'multi' | 'text'
  options: QuestionOption[]
  required?: boolean
  min_selections?: number
  max_selections?: number
  placeholder?: string
  max_length?: number
}

export interface Questionnaire {
  id: string
  title?: string
  description?: string
  questions: Question[]
  pending_id?: string
  created_at?: number
  expires_at?: number | null
}

export interface Artifact {
  id: string
  name: string
  mime_type?: string
  kind?: string
  size?: number
  url?: string
  source?: string
}

export type ToolStatus =
  | 'running'
  | 'ok'
  | 'error'
  | 'unknown'
  | 'not_executed'
  | 'awaiting_user'
  | 'awaiting_approval'
  | 'stopped'

export interface BaseEntry {
  id: string
  kind: string
  ts: number
}

export interface MessageEntry extends BaseEntry {
  kind: 'message'
  role: 'user' | 'assistant'
  text: string
  streaming: boolean
  files?: FileRef[]
  optimistic?: boolean
  platformConfirmed?: boolean
  runId?: string
  platformMessageId?: string
  answerComplete?: boolean
  runStatus?: string
}

export interface ReasoningEntry extends BaseEntry {
  kind: 'reasoning'
  text: string
  streaming: boolean
}

export interface ToolEntry extends BaseEntry {
  kind: 'tool'
  callId: string
  name: string
  args: unknown
  updates: string[]
  status: ToolStatus
  result: string
  artifacts: Artifact[]
  isError: boolean
  executionOutcome: string
  durationMs?: number
  businessRef?: string
}

export interface SkillEntry extends BaseEntry {
  kind: 'skill'
  skill: string
  action: 'activate' | 'read'
  source?: string
  activatedBy?: string
  path?: string
  offset?: number
  totalChars?: number
  nextOffset?: number | null
}

export interface CompactionEntry extends BaseEntry {
  kind: 'compaction'
  phase: 'start' | 'end'
  tokensBefore?: number
  summaryChars?: number
  reason?: string
}

export interface QuestionEntry extends BaseEntry {
  kind: 'question'
  pendingId: string
  questionnaire: Questionnaire
  status: 'waiting' | 'answered' | 'cancelled'
  answers?: Record<string, string | string[]>
  submitting?: boolean
  error?: string
}

export interface ApprovalEntry extends BaseEntry {
  kind: 'approval'
  pendingId: string
  toolCallId: string
  tool: string
  arguments: unknown
  source?: string
  status: 'waiting' | 'approved' | 'rejected' | 'cancelled'
  scope?: string
  submitting?: boolean
  error?: string
}

export interface TerminalInfo {
  status: string
  answer: string
  error: { code?: string; stage?: string; message?: string } | null
  stats?: Record<string, unknown>
  stateRef?: Record<string, unknown> | null
  pending?: unknown
}

export interface TerminalEntry extends BaseEntry {
  kind: 'terminal'
  terminal: TerminalInfo
}

export interface NoteEntry extends BaseEntry {
  kind: 'note'
  text: string
  tone?: 'info' | 'warning' | 'error'
}

export type WorkbenchEntry =
  | MessageEntry
  | ReasoningEntry
  | ToolEntry
  | SkillEntry
  | CompactionEntry
  | QuestionEntry
  | ApprovalEntry
  | TerminalEntry
  | NoteEntry

export interface TranscriptView {
  entries: WorkbenchEntry[]
  outputs: FileRef[]
  terminal: TerminalInfo | null
  running: boolean
  platformAnswer: string
  warnings: string[]
  ignored: number
  seen: Set<string>
  activeRunId: string
  runTerminals: Record<string, TerminalInfo>
  activeAssistantId: string
  activeReasoningId: string
  optimisticUserId: string
}

const INTERNAL_TOOL_NAMES = new Set(['ask_user', 'activate_skill', 'read_skill_resource'])

export function newView(): TranscriptView {
  return {
    entries: [],
    outputs: [],
    terminal: null,
    running: false,
    platformAnswer: '',
    warnings: [],
    ignored: 0,
    seen: new Set(),
    activeRunId: '',
    runTerminals: {},
    activeAssistantId: '',
    activeReasoningId: '',
    optimisticUserId: '',
  }
}

export function resetView(view: TranscriptView): void {
  const fresh = newView()
  Object.assign(view, fresh)
}

export function addOptimisticUser(view: TranscriptView, text: string, files: FileRef[] = []): string {
  const id = `optimistic_user_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  view.entries.push({
    id,
    kind: 'message',
    role: 'user',
    text,
    streaming: false,
    files,
    optimistic: true,
    ts: Date.now(),
  })
  view.optimisticUserId = id
  return id
}

export function applyEvent(view: TranscriptView, event: DisplayEvent): void {
  const key = `${event.run_id}:${event.seq}`
  if (view.seen.has(key)) return
  view.seen.add(key)
  view.activeRunId = event.run_id
  view.running = true
  switch (event.type) {
    case 'run.start':
      view.terminal = null
      view.running = true
      return
    case 'message.user': {
      const text = String(event.text || '')
      const last = view.entries[view.entries.length - 1]
      if (
        last &&
        last.kind === 'message' &&
        last.role === 'user' &&
        last.optimistic &&
        sameAnswer(last.text, text)
      ) {
        last.id = String(event.message_id || last.id)
        last.text = text
        last.optimistic = false
        if (Array.isArray(event.files)) last.files = event.files as FileRef[]
        view.optimisticUserId = ''
        return
      }
      view.entries.push({
        id: String(event.message_id || `user_${event.run_id}_${event.seq}`),
        kind: 'message',
        role: 'user',
        text,
        streaming: false,
        files: Array.isArray(event.files) ? (event.files as FileRef[]) : undefined,
        ts: event.ts,
      })
      return
    }
    case 'message.start': {
      const id = String(event.message_id || `assistant_${event.run_id}_${event.seq}`)
      view.activeAssistantId = id
      if (!view.entries.some((entry) => entry.kind === 'message' && entry.id === id)) {
        view.entries.push({
          id,
          kind: 'message',
          role: 'assistant',
          runId: event.run_id,
          text: '',
          streaming: true,
          ts: event.ts,
        })
      }
      return
    }
    case 'message.delta': {
      const entry = findMessage(view, String(event.message_id || view.activeAssistantId), 'assistant')
      if (!entry) return
      entry.text += String(event.delta || '')
      entry.streaming = true
      return
    }
    case 'message.end': {
      const entry = findMessage(view, String(event.message_id || view.activeAssistantId), 'assistant')
      if (!entry) return
      const text = String(event.text || entry.text || '')
      if (text) entry.text = text
      entry.streaming = false
      return
    }
    case 'reasoning.delta': {
      const id = String(event.reasoning_id || `reasoning_${event.run_id}`)
      view.activeReasoningId = id
      let entry = view.entries.find(
        (candidate): candidate is ReasoningEntry => candidate.kind === 'reasoning' && candidate.id === id,
      )
      if (!entry) {
        entry = { id, kind: 'reasoning', text: '', streaming: true, ts: event.ts }
        view.entries.push(entry)
      }
      entry.text += String(event.delta || '')
      entry.streaming = true
      return
    }
    case 'reasoning.end': {
      const id = String(event.reasoning_id || view.activeReasoningId)
      const entry = view.entries.find(
        (candidate): candidate is ReasoningEntry => candidate.kind === 'reasoning' && candidate.id === id,
      )
      if (entry) entry.streaming = false
      return
    }
    case 'tool.start': {
      const name = String(event.name || 'tool')
      if (INTERNAL_TOOL_NAMES.has(name)) return
      const callId = String(event.tool_call_id || '')
      let entry = findTool(view, callId)
      if (!entry) {
        entry = {
          id: `tool_${callId || event.seq}`,
          kind: 'tool',
          callId,
          name,
          args: event.arguments ?? {},
          updates: [],
          status: 'running',
          result: '',
          artifacts: [],
          isError: false,
          executionOutcome: '',
          ts: event.ts,
        }
        view.entries.push(entry)
      } else {
        entry.status = 'running'
        entry.args = event.arguments ?? entry.args
      }
      return
    }
    case 'tool.update': {
      const entry = findTool(view, String(event.tool_call_id || ''))
      if (!entry) return
      const text = String(event.text || '')
      if (text && !entry.updates.includes(text)) entry.updates.push(text)
      return
    }
    case 'tool.end': {
      const callId = String(event.tool_call_id || '')
      const name = String(event.name || 'tool')
      if (INTERNAL_TOOL_NAMES.has(name)) return
      let entry = findTool(view, callId)
      if (!entry) {
        entry = {
          id: `tool_${callId || event.seq}`,
          kind: 'tool',
          callId,
          name,
          args: event.arguments ?? {},
          updates: [],
          status: 'ok',
          result: '',
          artifacts: [],
          isError: false,
          executionOutcome: '',
          ts: event.ts,
        }
        view.entries.push(entry)
      }
      entry.status = toolStatus(String(event.status || 'ok'))
      entry.result = String(event.result || '')
      entry.artifacts = Array.isArray(event.artifacts) ? (event.artifacts as Artifact[]) : []
      entry.isError = Boolean(event.is_error)
      entry.executionOutcome = String(event.execution_outcome || '')
      entry.durationMs = typeof event.duration_ms === 'number' ? event.duration_ms : undefined
      entry.businessRef = event.business_ref ? String(event.business_ref) : undefined
      return
    }
    case 'skill.activate': {
      const callId = String(event.tool_call_id || '')
      if (callId && view.entries.some((item) => item.kind === 'skill' && item.id === `skill_${callId}`)) return
      view.entries.push({
        id: callId ? `skill_${callId}` : `skill_${event.run_id}_${event.seq}`,
        kind: 'skill',
        skill: String(event.skill || 'skill'),
        action: 'activate',
        source: event.source ? String(event.source) : undefined,
        activatedBy: event.activated_by ? String(event.activated_by) : undefined,
        ts: event.ts,
      })
      return
    }
    case 'skill.read': {
      view.entries.push({
        id: `skill_read_${event.tool_call_id || event.run_id}_${event.seq}`,
        kind: 'skill',
        skill: String(event.skill || 'skill'),
        action: 'read',
        path: event.path ? String(event.path) : undefined,
        offset: typeof event.offset === 'number' ? event.offset : undefined,
        totalChars: typeof event.total_chars === 'number' ? event.total_chars : undefined,
        nextOffset:
          typeof event.next_offset === 'number' || event.next_offset === null
            ? (event.next_offset as number | null)
            : undefined,
        ts: event.ts,
      })
      return
    }
    case 'skill.rejected':
      view.entries.push({
        id: `note_${event.run_id}_${event.seq}`,
        kind: 'note',
        text: `Skill ${String(event.skill || '')} is not available: ${String(event.reason || '')}`,
        tone: 'warning',
        ts: event.ts,
      })
      return
    case 'compaction.start': {
      view.entries.push({
        id: `compaction_${event.run_id}_${event.seq}`,
        kind: 'compaction',
        phase: 'start',
        tokensBefore: typeof event.tokens_before === 'number' ? event.tokens_before : undefined,
        reason: event.reason ? String(event.reason) : undefined,
        ts: event.ts,
      })
      return
    }
    case 'compaction.end': {
      const start = [...view.entries]
        .reverse()
        .find((entry): entry is CompactionEntry => entry.kind === 'compaction' && entry.phase === 'start')
      if (start) {
        start.phase = 'end'
        start.tokensBefore =
          typeof event.tokens_before === 'number' ? event.tokens_before : start.tokensBefore
        start.summaryChars =
          typeof event.summary_chars === 'number' ? event.summary_chars : undefined
      } else {
        view.entries.push({
          id: `compaction_end_${event.run_id}_${event.seq}`,
          kind: 'compaction',
          phase: 'end',
          tokensBefore: typeof event.tokens_before === 'number' ? event.tokens_before : undefined,
          summaryChars: typeof event.summary_chars === 'number' ? event.summary_chars : undefined,
          ts: event.ts,
        })
      }
      return
    }
    case 'question.asked': {
      const questionnaire = event.questionnaire as Questionnaire | undefined
      if (!questionnaire?.questions) return
      const pendingId = String(questionnaire.pending_id || questionnaire.id)
      const existing = view.entries.find(
        (entry): entry is QuestionEntry => entry.kind === 'question' && entry.pendingId === pendingId,
      )
      if (existing) {
        existing.questionnaire = questionnaire
        existing.submitting = false
        return
      }
      view.entries.push({
        id: `question_${pendingId}`,
        kind: 'question',
        pendingId,
        questionnaire,
        status: 'waiting',
        ts: event.ts,
      })
      return
    }
    case 'question.answered': {
      const pendingId = String(event.pending_id || '')
      const entry = view.entries.find(
        (candidate): candidate is QuestionEntry =>
          candidate.kind === 'question' && candidate.pendingId === pendingId,
      )
      if (!entry) return
      entry.status = 'answered'
      entry.answers = (event.answers as Record<string, string | string[]>) || {}
      entry.submitting = false
      return
    }
    case 'question.cancelled': {
      const pendingId = String(event.pending_id || '')
      const entry = view.entries.find(
        (candidate): candidate is QuestionEntry =>
          candidate.kind === 'question' && candidate.pendingId === pendingId,
      )
      if (entry) {
        entry.status = 'cancelled'
        entry.submitting = false
      }
      return
    }
    case 'approval.requested': {
      const approval = (event.approval || {}) as Record<string, unknown>
      const pendingId = String(approval.pending_id || '')
      if (!pendingId) return
      const existing = view.entries.find(
        (entry): entry is ApprovalEntry => entry.kind === 'approval' && entry.pendingId === pendingId,
      )
      if (existing) {
        existing.submitting = false
        return
      }
      view.entries.push({
        id: `approval_${pendingId}`,
        kind: 'approval',
        pendingId,
        toolCallId: String(approval.tool_call_id || ''),
        tool: String(approval.tool || 'tool'),
        arguments: approval.arguments ?? {},
        source: approval.source ? String(approval.source) : undefined,
        status: 'waiting',
        ts: event.ts,
      })
      return
    }
    case 'approval.resolved': {
      const callId = String(event.tool_call_id || '')
      const decision = String(event.decision || '')
      const entry = view.entries.find(
        (candidate): candidate is ApprovalEntry =>
          candidate.kind === 'approval' &&
          (candidate.toolCallId === callId || candidate.pendingId === String(event.pending_id || '')),
      )
      if (entry) {
        entry.status = decision === 'approved' ? 'approved' : decision === 'rejected' ? 'rejected' : 'cancelled'
        entry.scope = event.scope ? String(event.scope) : undefined
        entry.submitting = false
      }
      return
    }
    case 'run.state':
    case 'run.done': {
      const terminal: TerminalInfo = {
        status: terminalStatus(event.status),
        answer: String(event.answer || ''),
        error: (event.error as TerminalInfo['error']) || null,
        stats: (event.stats as Record<string, unknown>) || {},
        stateRef: (event.state_ref as Record<string, unknown>) || null,
        pending: event.pending,
      }
      view.terminal = terminal
      view.runTerminals[event.run_id] = terminal
      for (const entry of view.entries) {
        if (entry.kind === 'message' && entry.runId === event.run_id) entry.runStatus = terminal.status
      }
      view.running = false
      if (terminal.answer) mergeTerminalAnswer(view, terminal.answer, event.run_id)
      if (terminal.status !== 'awaiting_user' && terminal.status !== 'awaiting_approval') {
        const terminalId = `terminal_${event.run_id}`
        const existing = view.entries.find(
          (entry): entry is TerminalEntry => entry.kind === 'terminal' && entry.id === terminalId,
        )
        if (existing) {
          existing.terminal = terminal
        } else {
          view.entries.push({
            id: terminalId,
            kind: 'terminal',
            terminal,
            ts: event.ts,
          })
        }
      }
      return
    }
    case 'agent_failed': {
      const terminal: TerminalInfo = {
        status: 'failed',
        answer: String(event.message || 'The Pi agent run failed.'),
        error: {
          code: String(event.code || 'agent_failed'),
          stage: String(event.stage || 'runtime'),
          message: String(event.message || 'The Pi agent run failed.'),
        },
      }
      view.terminal = terminal
      view.runTerminals[event.run_id] = terminal
      for (const entry of view.entries) {
        if (entry.kind === 'message' && entry.runId === event.run_id) entry.runStatus = 'failed'
      }
      view.running = false
      view.entries.push({
        id: `terminal_${event.run_id}_failed`,
        kind: 'terminal',
        terminal,
        ts: event.ts,
      })
      return
    }
    case 'activity': {
      const activity = String(event.activity || '')
      if (activity === 'skills.discovered') return
      if (activity === 'abort') {
        view.entries.push({
          id: `note_abort_${event.run_id}_${event.seq}`,
          kind: 'note',
          text: 'Run aborted by the client.',
          tone: 'warning',
          ts: event.ts,
        })
        return
      }
      if (event.text) {
        view.entries.push({
          id: `note_${event.run_id}_${event.seq}`,
          kind: 'note',
          text: String(event.text),
          ts: event.ts,
        })
      }
      return
    }
    default:
      view.ignored += 1
  }
}

export interface AnswerBinding {
  runId?: string
  platformMessageId?: string
  ts?: number
}

/** Merge the complete native answer only into the final assistant message of its run. */
export function mergeFinalAnswer(view: TranscriptView, text: string, binding: AnswerBinding = {}): void {
  const answer = String(text || '')
  if (!normalizeAnswer(answer)) return
  view.platformAnswer = answer
  const runId = binding.runId || view.activeRunId || `platform:${binding.platformMessageId || 'answer'}`
  const assistant = [...view.entries].reverse().find(
    (entry): entry is MessageEntry => entry.kind === 'message' && entry.role === 'assistant' &&
      (entry.runId === runId || (!entry.runId && !binding.runId)),
  )
  const fields = {
    text: answer,
    streaming: false,
    platformConfirmed: true,
    answerComplete: true,
    platformMessageId: binding.platformMessageId,
    runId,
    runStatus: view.runTerminals[runId]?.status,
  }
  if (assistant) Object.assign(assistant, fields)
  else view.entries.push({
    id: `platform_answer_${binding.platformMessageId || runId}`,
    kind: 'message', role: 'assistant', ts: binding.ts || Date.now(), ...fields,
  })
}

function mergeTerminalAnswer(view: TranscriptView, answer: string, runId: string): void {
  const assistant = [...view.entries].reverse().find(
    (entry): entry is MessageEntry => entry.kind === 'message' && entry.role === 'assistant' && entry.runId === runId,
  )
  if (!assistant) view.entries.push({
    id: `terminal_answer_${runId}`, kind: 'message', role: 'assistant',
    text: answer, streaming: false, ts: Date.now(), runId,
    runStatus: view.runTerminals[runId]?.status,
  })
}

function findMessage(
  view: TranscriptView,
  id: string,
  role: 'user' | 'assistant',
): MessageEntry | undefined {
  const entry = view.entries.find(
    (candidate): candidate is MessageEntry =>
      candidate.kind === 'message' && candidate.id === id && candidate.role === role,
  )
  if (entry) return entry
  return [...view.entries]
    .reverse()
    .find(
      (candidate): candidate is MessageEntry =>
        candidate.kind === 'message' && candidate.role === role && candidate.streaming,
    )
}

function findTool(view: TranscriptView, callId: string): ToolEntry | undefined {
  return view.entries.find(
    (entry): entry is ToolEntry => entry.kind === 'tool' && entry.callId === callId,
  )
}

function toolStatus(value: string): ToolStatus {
  if (value === 'ok' || value === 'completed') return 'ok'
  if (value === 'running') return 'running'
  if (value === 'error' || value === 'failed') return 'error'
  if (value === 'unknown') return 'unknown'
  if (value === 'not_executed') return 'not_executed'
  if (value === 'awaiting_user') return 'awaiting_user'
  if (value === 'awaiting_approval') return 'awaiting_approval'
  if (value === 'stopped') return 'stopped'
  return 'ok'
}
