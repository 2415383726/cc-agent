import { DisplayEvent, findPiEvent, normalizeAnswer } from '../contract/display'
import { eventsFromHistory, HistoryRecord } from '../projection/history'
import {
  ApprovalEntry,
  FileRef,
  QuestionEntry,
  TerminalInfo,
  TranscriptView,
  addOptimisticUser,
  applyEvent,
  mergeFinalAnswer,
  newView,
  resetView,
} from '../projection/transcript'
import { WorkbenchConfig } from './config'
import {
  DifyConversation,
  UploadedFile,
  listConversations,
  listMessages,
  stopChat,
  streamChat,
  uploadFile,
} from './transport'

export interface UiState {
  running: boolean
  stopping: boolean
  stopRequested: boolean
  connected: boolean
  error: string
  conversationId: string
  conversations: DifyConversation[]
  loadingHistory: boolean
  hasMore: boolean
  firstId: string
  stoppedNote: string
}

export interface WorkbenchController {
  view: TranscriptView
  ui: UiState
  send(text: string, files?: FileRef[]): Promise<void>
  stop(): Promise<void>
  upload(file: File): Promise<FileRef | null>
  submitAnswers(entry: QuestionEntry, answers: Record<string, string | string[]>): Promise<void>
  cancelQuestion(entry: QuestionEntry): Promise<void>
  submitApproval(entry: ApprovalEntry, decision: 'approve' | 'reject', scope: 'once' | 'session'): Promise<void>
  refreshConversations(): Promise<void>
  loadConversation(id: string): Promise<void>
  newConversation(): void
  updateConfig(config: WorkbenchConfig): void
}

export class DifyController implements WorkbenchController {
  view: TranscriptView = newView()
  ui: UiState = {
    running: false,
    stopping: false,
    stopRequested: false,
    connected: false,
    error: '',
    conversationId: '',
    conversations: [],
    loadingHistory: false,
    hasMore: false,
    firstId: '',
    stoppedNote: '',
  }
  config: WorkbenchConfig

  private _ticket = 0
  private _abort: AbortController | null = null
  private _taskId = ''
  private _platformText = ''
  private _records: HistoryRecord[] = []
  private _warnedVersion = false

  constructor(config: WorkbenchConfig) {
    this.config = { ...config }
  }

  updateConfig(config: WorkbenchConfig): void {
    this.config = { ...config }
    this.ui.connected = Boolean(config.apiKey && config.baseUrl)
  }

  async send(text: string, files: FileRef[] = []): Promise<void> {
    const query = String(text || '').trim()
    if (!query || this.ui.running || this.ui.stopping) return
    addOptimisticUser(this.view, query, files)
    await this._stream(query, this.config.inputs, files)
  }

  async upload(file: File): Promise<FileRef | null> {
    try {
      const uploaded = await uploadFile(this.config, file)
      return uploaded
    } catch (error) {
      this.ui.error = safeError(error)
      return null
    }
  }

  async stop(): Promise<void> {
    if (!this.ui.running && !this.ui.stopping) return
    this.ui.stopRequested = true
    this.ui.stopping = true
    try {
      if (this._taskId) await stopChat(this.config, this._taskId)
    } catch (error) {
      this.ui.error = safeError(error)
    }
    this._abort?.abort()
    this.ui.stoppedNote = '已请求停止；只有服务端终态才能确认最终结果。'
  }

  async submitAnswers(
    entry: QuestionEntry,
    answers: Record<string, string | string[]>,
  ): Promise<void> {
    if (!entry || entry.status !== 'waiting' || entry.submitting) return
    entry.submitting = true
    entry.error = ''
    try {
      await this._interaction({
        type: 'ask_user',
        pending_id: entry.pendingId,
        answers,
      })
    } catch (error) {
      entry.error = safeError(error)
    } finally {
      if (entry.status === 'waiting') {
        entry.submitting = false
        if (this.view.terminal?.error?.message) entry.error = this.view.terminal.error.message
      }
      this.ui.running = false
    }
  }

  async cancelQuestion(entry: QuestionEntry): Promise<void> {
    if (!entry || entry.status !== 'waiting' || entry.submitting) return
    entry.submitting = true
    entry.error = ''
    try {
      await this._interaction({ type: 'cancel', pending_id: entry.pendingId })
    } catch (error) {
      entry.error = safeError(error)
    } finally {
      if (entry.status === 'waiting') {
        entry.submitting = false
        if (this.view.terminal?.error?.message) entry.error = this.view.terminal.error.message
      }
      this.ui.running = false
    }
  }

  async submitApproval(
    entry: ApprovalEntry,
    decision: 'approve' | 'reject',
    scope: 'once' | 'session',
  ): Promise<void> {
    if (!entry || entry.status !== 'waiting' || entry.submitting) return
    entry.submitting = true
    entry.error = ''
    try {
      await this._interaction({
        type: 'approval',
        pending_id: entry.pendingId,
        decision,
        scope,
      })
    } catch (error) {
      entry.error = safeError(error)
    } finally {
      if (entry.status === 'waiting') {
        entry.submitting = false
        if (this.view.terminal?.error?.message) entry.error = this.view.terminal.error.message
      }
      this.ui.running = false
    }
  }

  async refreshConversations(): Promise<void> {
    try {
      this.ui.conversations = await listConversations(this.config)
      this.ui.connected = true
    } catch (error) {
      this.ui.error = safeError(error)
    }
  }

  async loadConversation(id: string): Promise<void> {
    const epoch = ++this._ticket
    this._abort?.abort()
    this._abort = null
    this.ui.running = false
    this.ui.stopping = false
    this.ui.error = ''
    this.ui.conversationId = id
    this._records = []
    resetView(this.view)
    this.ui.firstId = ''
    this.ui.hasMore = false
    if (!id) return
    this.ui.loadingHistory = true
    try {
      const page = await listMessages(this.config, id, { limit: 20 })
      if (epoch !== this._ticket) return
      this._records = page.records
      this.ui.firstId = page.firstId
      this.ui.hasMore = page.hasMore
      this._applyHistory()
    } catch (error) {
      if (epoch !== this._ticket) return
      this.ui.error = safeError(error)
    } finally {
      if (epoch === this._ticket) this.ui.loadingHistory = false
    }
  }

  async loadMore(): Promise<void> {
    if (this.ui.loadingHistory || !this.ui.hasMore || !this.ui.conversationId) return
    const epoch = this._ticket
    this.ui.loadingHistory = true
    try {
      const page = await listMessages(this.config, this.ui.conversationId, {
        limit: 20,
        firstId: this.ui.firstId,
      })
      if (epoch !== this._ticket) return
      const seen = new Set(this._records.map((record) => record.id))
      const older = page.records.filter((record) => !seen.has(record.id))
      this._records = [...older, ...this._records]
      this.ui.firstId = page.firstId || this.ui.firstId
      this.ui.hasMore = page.hasMore
      this._applyHistory()
    } catch (error) {
      if (epoch === this._ticket) this.ui.error = safeError(error)
    } finally {
      if (epoch === this._ticket) this.ui.loadingHistory = false
    }
  }

  newConversation(): void {
    this._ticket += 1
    this._abort?.abort()
    this._abort = null
    this._records = []
    this._taskId = ''
    resetView(this.view)
    this.ui.running = false
    this.ui.stopping = false
    this.ui.error = ''
    this.ui.conversationId = ''
    this.ui.firstId = ''
    this.ui.hasMore = false
    this.ui.stoppedNote = ''
  }

  private _applyHistory(): void {
    const { events } = eventsFromHistory(this._records)
    resetView(this.view)
    for (const event of events) applyEvent(this.view, event)
    for (const record of this._records) {
      const files = Array.isArray((record as any).message_files) ? (record as any).message_files : []
      for (const file of files) {
        const url = String((file as any)?.url || '')
        if (url && !this.view.outputs.some((item) => item.url === url)) {
          this.view.outputs.push({
            id: String((file as any)?.id || url),
            name: String((file as any)?.filename || (file as any)?.name || 'output file'),
            mimeType: String((file as any)?.mime_type || (file as any)?.mimeType || ''),
            url,
          })
        }
      }
    }
    const last = this._records[this._records.length - 1]
    if (last?.answer) mergeFinalAnswer(this.view, String(last.answer))
    if (!events.length && this._records.length) {
      this.view.warnings.push('该会话历史中没有保存 Pi 过程事件。')
    }
    if (!this.view.terminal && this._records.length) {
      this.view.terminal = {
        status: 'unknown',
        answer: '',
        error: {
          code: 'unknown',
          stage: 'history',
          message: '最近一轮没有保存可信的终态。',
        },
      }
    }
  }

  private async _interaction(payload: Record<string, unknown>): Promise<void> {
    const inputs = { ...this.config.inputs, interaction: JSON.stringify(payload) }
    await this._stream('提交交互', inputs, [])
  }

  private async _stream(
    query: string,
    inputs: Record<string, unknown>,
    files: FileRef[],
  ): Promise<void> {
    if (this.ui.running) return
    this._ticket += 1
    const ticket = this._ticket
    this.ui.running = true
    this.ui.stopping = false
    this.ui.stopRequested = false
    this.ui.error = ''
    this.ui.stoppedNote = ''
    this._taskId = ''
    this._platformText = ''
    this._abort = new AbortController()
    try {
      const stream = await streamChat({
        ...this.config,
        inputs,
        conversationId: this.ui.conversationId,
        query,
        files: files as UploadedFile[],
        signal: this._abort.signal,
      })
      for await (const payload of stream.events) {
        if (ticket !== this._ticket) return
        this._handleDifyEvent(payload)
      }
      if (ticket !== this._ticket) return
      if (!this.view.terminal) {
        const stopped = this.ui.stopRequested
        this.view.terminal = {
          status: 'unknown',
          answer: stopped
            ? '已请求停止，但服务器没有确认终态。'
            : '',
          error: {
            code: stopped ? 'stopped_unconfirmed' : 'unknown',
            stage: 'transport',
            message: stopped
              ? '已请求停止，但没有收到可信的服务端终态。'
              : '流在可信终态之前结束。',
          },
        }
        this.view.entries.push({
          id: `unconfirmed_${Date.now()}`,
          kind: 'note',
          text: stopped
            ? '已请求停止；结果未确认，未重新发送请求。'
            : '流在可信终态到达前结束，未重新发送请求。',
          tone: 'warning',
          ts: Date.now(),
        })
      }
      this.ui.running = false
    } catch (error) {
      if (ticket !== this._ticket) return
      if (this.ui.stopRequested) {
        if (!this.view.terminal) {
          this.view.terminal = {
            status: 'unknown',
            answer: '已请求停止，但服务器没有确认终态。',
            error: {
              code: 'stopped_unconfirmed',
              stage: 'transport',
              message: '已请求停止，但没有收到可信的服务端终态。',
            },
          }
          this.view.entries.push({
            id: `stop_${Date.now()}`,
            kind: 'note',
            text: '已请求停止；结果未确认，未重新发送请求。',
            tone: 'warning',
            ts: Date.now(),
          })
        }
      } else {
        this.ui.error = safeError(error)
        if (!this.view.terminal) {
          this.view.terminal = {
            status: 'failed',
            answer: 'Dify 请求失败，未收到可信终态。',
            error: { code: 'transport_failed', stage: 'transport', message: safeError(error) },
          }
        }
      }
      this.ui.running = false
    } finally {
      if (ticket === this._ticket) {
        this.ui.running = false
        this.ui.stopping = false
        this._abort = null
      }
    }
  }

  private _handleDifyEvent(payload: Record<string, any>): void {
    const eventName = String(payload?.event || '')
    if (payload?.task_id) this._taskId = String(payload.task_id)
    if (payload?.conversation_id) {
      this.ui.conversationId = String(payload.conversation_id)
      if (!this.ui.conversations.some((item) => item.id === this.ui.conversationId)) {
        this.ui.conversations.push({
          id: this.ui.conversationId,
          name: '当前会话',
          updatedAt: Date.now(),
        })
      }
    }
    if (eventName === 'error') {
      const message = safeText(payload?.message || 'Dify 流返回了错误。')
      this.ui.error = message
      if (!this.view.terminal) {
        this.view.terminal = {
          status: 'failed',
          answer: message,
          error: { code: 'stream_error', stage: 'transport', message },
        }
      }
      return
    }
    if (eventName === 'message' || eventName === 'agent_message') {
      const answer = String(payload?.answer || '')
      if (answer) this._platformText += answer
    }
    if (eventName === 'message_file') {
      const url = String(payload?.url || '')
      if (url && !this.view.outputs.some((item) => item.url === url)) {
        this.view.outputs.push({
          id: String(payload?.id || url),
          name: String(payload?.filename || payload?.name || 'output file'),
          mimeType: String(payload?.type || ''),
          type: String(payload?.type || ''),
          url,
        })
      }
    }
    const found = findPiEvent(payload)
    if (found?.problem === 'unsupported-version' && !this._warnedVersion) {
      this._warnedVersion = true
      this.view.warnings.push('工作台忽略了不受支持的显示契约版本事件。')
    }
    if (found?.event) {
      applyEvent(this.view, found.event)
      if (this.view.terminal && !isWaiting(this.view.terminal.status)) {
        this.ui.running = false
      }
    }
    if (eventName === 'message_end') {
      const finalText = normalizeAnswer(this._platformText || String(payload?.answer || ''))
      if (finalText) mergeFinalAnswer(this.view, finalText)
    }
  }
}

function isWaiting(status: string): boolean {
  return status === 'awaiting_user' || status === 'awaiting_approval'
}

function safeError(error: unknown): string {
  if (error instanceof Error) return error.message.slice(0, 500)
  return String(error || '未知错误').slice(0, 500)
}

function safeText(value: unknown): string {
  return String(value || '').slice(0, 1000)
}

export type { DisplayEvent }
