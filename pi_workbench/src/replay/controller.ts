import { DisplayEvent, SCHEMA } from '../contract/display'
import type { WorkbenchConfig } from '../dify/config'
import type { UiState, WorkbenchController } from '../dify/controller'
import {
  ApprovalEntry,
  FileRef,
  QuestionEntry,
  Questionnaire,
  TranscriptView,
  addOptimisticUser,
  applyEvent,
  newView,
  resetView,
} from '../projection/transcript'
import { REPLAY_SCENARIOS, ReplayScenario, scenarioById } from './scenarios'

export class ReplayController implements WorkbenchController {
  view: TranscriptView = newView()
  ui: UiState = {
    running: false,
    stopping: false,
    stopRequested: false,
    connected: true,
    error: '',
    conversationId: 'replay',
    conversations: [{ id: 'replay', name: 'Replay scenario', updatedAt: 0 }],
    loadingHistory: false,
    hasMore: false,
    firstId: '',
    stoppedNote: '',
  }
  scenarios: ReplayScenario[] = REPLAY_SCENARIOS
  current: ReplayScenario | null = null
  private _seq = 100
  private _conversation: Questionnaire | null = null

  loadScenario(id: string): void {
    const scenario = scenarioById(id)
    if (!scenario) return
    resetView(this.view)
    this.current = scenario
    this._seq = 100
    this._conversation = null
    for (const event of scenario.events) {
      applyEvent(this.view, event)
      const questionnaire = event.questionnaire as Questionnaire | undefined
      if (questionnaire) this._conversation = questionnaire
    }
    this.ui.running = false
    this.ui.error = ''
  }

  async send(text: string, files: FileRef[] = []): Promise<void> {
    const query = String(text || '').trim()
    if (!query) return
    addOptimisticUser(this.view, query, files)
    this._append('note', { text: 'Replay mode: no Dify request or model call was made.', tone: 'info' })
    this._terminal('completed', 'Replay mode does not call a model. Choose a scenario to replay process events.')
  }

  async stop(): Promise<void> {
    this._append('activity', { activity: 'abort' })
    this._terminal('stopped', 'Replay mode stopped locally.')
  }

  async upload(file: File): Promise<FileRef | null> {
    return {
      id: `replay-file-${file.name}`,
      name: file.name,
      mimeType: file.type,
      size: file.size,
      type: file.type.startsWith('image/') ? 'image' : 'document',
    }
  }

  async submitAnswers(
    entry: QuestionEntry,
    answers: Record<string, string | string[]>,
  ): Promise<void> {
    if (!entry || entry.status !== 'waiting') return
    this._append('question.answered', {
      pending_id: entry.pendingId,
      answers,
    })
    this._append('message.user', {
      message_id: `replay-answer-${this._seq}`,
      text: formatAnswers(entry.questionnaire, answers),
    })
    this._append('message.start', { message_id: `replay-answer-assistant-${this._seq}` })
    this._append('message.end', {
      message_id: `replay-answer-assistant-${this._seq}`,
      text: 'Thanks — the questionnaire was submitted. This is a replay result; a real run resumes through Dify.',
      stop_reason: 'stop',
      has_tool_calls: false,
    })
    this._terminal('completed', 'Questionnaire answered in replay mode.')
  }

  async cancelQuestion(entry: QuestionEntry): Promise<void> {
    this._append('question.cancelled', { pending_id: entry.pendingId })
    this._terminal('cancelled', 'The questionnaire was cancelled in replay mode.')
  }

  async submitApproval(
    entry: ApprovalEntry,
    decision: 'approve' | 'reject',
    scope: 'once' | 'session',
  ): Promise<void> {
    if (!entry || entry.status !== 'waiting') return
    this._append('approval.resolved', {
      pending_id: entry.pendingId,
      tool_call_id: entry.toolCallId,
      decision: decision === 'approve' ? 'approved' : 'rejected',
      scope,
    })
    this._append('tool.end', {
      tool_call_id: entry.toolCallId,
      name: entry.tool,
      status: decision === 'approve' ? 'unknown' : 'not_executed',
      result:
        decision === 'approve'
          ? 'The replayed remote write returned no confirmation; the business outcome is unknown. Verify it before retrying.'
          : 'Rejected; the operation was not executed.',
      execution_outcome: decision === 'approve' ? 'unknown' : 'not_executed',
      business_ref: decision === 'approve' ? `${entry.tool}:${entry.toolCallId}` : undefined,
    })
    this._append('message.end', {
      message_id: `replay-approval-assistant-${this._seq}`,
      text:
        decision === 'approve'
          ? 'The approval was applied in replay mode. A real remote result would be delivered by the next Dify turn; verify unknown write outcomes.'
          : 'The operation was rejected and no change was made.',
      stop_reason: 'stop',
      has_tool_calls: false,
    })
    this._terminal('completed', 'Approval decision replayed.')
  }

  async refreshConversations(): Promise<void> {
    /* replay has one fixed conversation */
  }

  async loadConversation(id: string): Promise<void> {
    resetView(this.view)
    this.ui.conversationId = id || 'replay'
  }

  newConversation(): void {
    resetView(this.view)
    this.ui.conversationId = 'replay'
  }

  updateConfig(_config: WorkbenchConfig): void {
    /* replay does not use a Dify connection */
  }

  private _append(type: string, fields: Record<string, unknown>): void {
    const event = {
      schema: SCHEMA,
      schema_version: 1,
      type,
      run_id: 'run_replay_append',
      seq: this._seq++,
      ts: Date.now(),
      ...fields,
    } as DisplayEvent
    applyEvent(this.view, event)
  }

  private _terminal(status: string, answer: string): void {
    this._append('run.state', {
      status,
      answer,
      stats: { model_requests: 0, tool_calls: 0 },
    })
    this._append('run.done', { status, answer })
  }
}

function formatAnswers(questionnaire: Questionnaire, answers: Record<string, string | string[]>): string {
  const lines = ['Answers to the questionnaire:']
  for (const question of questionnaire.questions || []) {
    const value = answers[question.id]
    if (value == null) continue
    if (Array.isArray(value)) {
      const labels = new Map((question.options || []).map((option) => [option.id, option.label]))
      lines.push(`- ${question.question}: ${value.map((item) => labels.get(item) || item).join(', ')}`)
    } else if (question.type === 'text') {
      lines.push(`- ${question.question}: ${value}`)
    } else {
      const options = new Map((question.options || []).map((option) => [option.id, option.label]))
      lines.push(`- ${question.question}: ${options.get(value) || value}`)
    }
  }
  return lines.join('\n')
}
