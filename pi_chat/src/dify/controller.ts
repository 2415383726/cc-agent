import { DisplayEvent, findPiEvent, normalizeAnswer } from '../contract/display'
import { eventsFromHistory, HistoryRecord } from '../projection/history'
import { eventsFromSavedState } from '../projection/savedState'
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
  deleteConversation as deleteConversationRequest,
  listConversations,
  listMessages,
  readAgentState,
  renameConversation as renameConversationRequest,
  stopChat,
  streamChat,
  uploadFile,
} from './transport'

/**
 * Framework-agnostic pure TS: no Vue reactivity imports. The binding seam is
 * the consumer shell (pi_chat src/App.vue), which wraps an instance in
 * reactive() and reads view/ui as plain data.
 */
export interface UiState {
  running: boolean
  stopping: boolean
  stopRequested: boolean
  connected: boolean
  error: string
  conversationId: string
  conversations: DifyConversation[]
  /** 会话列表加载失败信息；侧栏用它的存在切换到「加载失败重试」态。 */
  conversationsError: string
  /** 重命名/删除等列表操作的兜底提示（失败原因），成功时为空。 */
  actionNote: string
  loadingHistory: boolean
  hasMore: boolean
  firstId: string
  stoppedNote: string
  /** 已有回合在跑、但当前视图不在其中的会话；侧栏据此显示进行中。 */
  runningIds: string[]
}

interface RunState {
  ticket: number
  conversationId: string
  detached: boolean
  abort: AbortController
  taskId: string
  /** 平台侧累积的正文，按回合隔离（切走的回合不能污染当前视图）。 */
  platformText: string
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
  /** 重命名会话；成功 true 并即时更新列表，失败 false 且 actionNote 有兜底提示。 */
  renameConversation(id: string, name: string): Promise<boolean>
  /** 删除会话；删除当前会话回到新会话态并丢弃陈旧流结果。 */
  deleteConversation(id: string): Promise<boolean>
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
    conversationsError: '',
    actionNote: '',
    loadingHistory: false,
    hasMore: false,
    firstId: '',
    stoppedNote: '',
    runningIds: [],
  }
  config: WorkbenchConfig

  private _ticket = 0
  private _abort: AbortController | null = null
  private _taskId = ''
  private _records: HistoryRecord[] = []
  private _warnedVersion = false
  /**
   * 在跑的回合只记录成一笔账：切走视图时把它标成 detached 而不 abort，
   * 让流一直读到服务端终态 —— 这正是侧栏「进行中」的判断依据（没有终态 = 仍在跑）。
   */
  private _run: RunState | null = null
  /** 离开某会话时的视图快照：切回来先还原，避免「一切会话内容就没了」。 */
  private _views = new Map<string, TranscriptView>()

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
      // 上传失败与列表操作同路：写 actionNote 兜底提示（侧栏可见），不污染错误横幅。
      this.ui.actionNote = `附件上传失败：${safeError(error)}`
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
      this.ui.conversationsError = ''
      this.ui.connected = true
    } catch (error) {
      this.ui.conversationsError = safeError(error)
    }
  }

  async renameConversation(id: string, name: string): Promise<boolean> {
    const nextName = String(name || '').trim()
    if (!id || !nextName) return false
    this.ui.actionNote = ''
    try {
      const updated = await renameConversationRequest(this.config, id, nextName)
      const existing = this.ui.conversations.find((item) => item.id === id)
      if (existing) {
        existing.name = updated.name || nextName
        if (updated.updatedAt) existing.updatedAt = updated.updatedAt
      } else {
        this.ui.conversations.unshift({
          id,
          name: updated.name || nextName,
          updatedAt: updated.updatedAt || Date.now(),
        })
      }
      await this.refreshConversations()
      return true
    } catch (error) {
      this.ui.actionNote = `重命名失败：${safeError(error)}`
      return false
    }
  }

  async deleteConversation(id: string): Promise<boolean> {
    if (!id) return false
    this.ui.actionNote = ''
    try {
      await deleteConversationRequest(this.config, id)
      // 删除在跑的会话：这是唯一会主动中止流的场景，避免把结果写给已删除的会话。
      if (this._run?.conversationId === id) {
        this._abort?.abort()
        this._run = null
        this._setRunning(id, false)
      }
      this.ui.conversations = this.ui.conversations.filter((item) => item.id !== id)
      if (this.ui.conversationId === id) this.newConversation()
      await this.refreshConversations()
      return true
    } catch (error) {
      this.ui.actionNote = `删除失败：${safeError(error)}`
      return false
    }
  }

  async loadConversation(id: string): Promise<void> {
    this._snapshotView()
    // 回到仍在跑的会话：还原离开时的内容，并把流接回这个视图（不重拉历史，
    // 服务端此刻还没有这一轮的最终回答）。
    const active = this._run && this._run.conversationId === id ? this._run : null
    if (active) {
      this.ui.conversationId = id
      this.ui.error = ''
      this.ui.stopping = false
      this.ui.stoppedNote = ''
      this.ui.loadingHistory = false
      this._restoreView(id)
      active.detached = false
      this._ticket = active.ticket
      this._abort = active.abort
      this._taskId = active.taskId
      this.ui.running = true
      return
    }
    const epoch = ++this._ticket
    // 切会话不 abort 在跑的回合：摘掉视图绑定即可，终态到达时再回填历史。
    this._detachRun()
    this._abort = null
    this.ui.running = false
    this.ui.stopping = false
    this.ui.error = ''
    this.ui.conversationId = id
    this._records = []
    resetView(this.view)
    this._restoreView(id)
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
      this._views.delete(id)
      await this._restoreSavedState(epoch, id)
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
      await this._restoreSavedState(epoch, this.ui.conversationId)
    } catch (error) {
      if (epoch === this._ticket) this.ui.error = safeError(error)
    } finally {
      if (epoch === this._ticket) this.ui.loadingHistory = false
    }
  }

  newConversation(): void {
    this._snapshotView()
    this._ticket += 1
    // 上一轮仍在跑时只摘视图：继续读流到终态，侧栏保留该会话的进行中标记。
    this._detachRun()
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
    this.ui.actionNote = ''
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
    if (!events.some((event) => !event.run_id.startsWith('history:')) && this._records.length) {
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

  private async _restoreSavedState(ticket: number, conversationId: string): Promise<void> {
    try {
      const value = await readAgentState(this.config, conversationId)
      if (!value || ticket !== this._ticket) return
      const events = await eventsFromSavedState(value, conversationId)
      if (ticket !== this._ticket) return
      for (const event of events) applyEvent(this.view, event)
    } catch {
      if (ticket === this._ticket) this.view.warnings.push('无法读取当前 Pi 状态；未自动重发请求，请稍后刷新。')
    }
  }

  private async _interaction(payload: Record<string, unknown>): Promise<void> {
    const inputs = { ...this.config.inputs, interaction: JSON.stringify(payload) }
    await this._stream('提交交互', inputs, [])
  }

  /**
   * 断流未确认终态的合成（S2 收敛：try 尾「流先于终态结束」与 catch/stop 的
   * 「停止未确认」共用同一私有 helper）——诚实终态 status=unknown + 警示备注，
   * 绝不自动重发。
   */
  private _synthesizeUnconfirmed(stopped: boolean): void {
    this.view.terminal = {
      status: 'unknown',
      answer: stopped ? '已请求停止，但服务器没有确认终态。' : '',
      error: {
        code: stopped ? 'stopped_unconfirmed' : 'unknown',
        stage: 'transport',
        message: stopped
          ? '已请求停止，但没有收到可信的服务端终态。'
          : '流在可信终态之前结束。',
      },
    }
    this.view.entries.push({
      id: `${stopped ? 'stop' : 'unconfirmed'}_${Date.now()}`,
      kind: 'note',
      text: stopped
        ? '已请求停止；结果未确认，未重新发送请求。'
        : '流在可信终态到达前结束，未重新发送请求。',
      tone: 'warning',
      ts: Date.now(),
    })
  }

  private async _stream(
    query: string,
    inputs: Record<string, unknown>,
    files: FileRef[],
  ): Promise<void> {
    if (this.ui.running) return
    this.view.terminal = null
    this.view.platformAnswer = ''
    this.view.running = true
    this._ticket += 1
    const ticket = this._ticket
    const abort = new AbortController()
    const run: RunState = {
      ticket,
      conversationId: this.ui.conversationId,
      detached: false,
      abort,
      taskId: '',
      platformText: '',
    }
    this._run = run
    this.ui.running = true
    this.ui.stopping = false
    this.ui.stopRequested = false
    this.ui.error = ''
    this.ui.stoppedNote = ''
    this._taskId = ''
    this._abort = abort
    try {
      const stream = await streamChat({
        ...this.config,
        inputs,
        conversationId: this.ui.conversationId,
        query,
        files: files as UploadedFile[],
        signal: this._abort.signal,
      })
      // 视图切换只让 ticket 失配（detached），流本身读到底：终态是唯一的「跑完」证据。
      for await (const payload of stream.events) {
        this._handleDifyEvent(payload, run)
      }
      if (this._attached(run)) {
        if (!this.view.terminal) this._synthesizeUnconfirmed(this.ui.stopRequested)
      }
    } catch (error) {
      if (this._attached(run)) {
        if (this.ui.stopRequested) {
          if (!this.view.terminal) this._synthesizeUnconfirmed(true)
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
      }
    } finally {
      const attached = this._attached(run)
      this._finishRun(run, attached)
      if (attached) {
        this.ui.running = false
        this.ui.stopping = false
        this._abort = null
      }
    }
  }

  /** 该回合的视图是否仍由当前会话承载（切走即 detached，只保留运行中账目）。 */
  private _attached(run: RunState): boolean {
    return !run.detached && run.ticket === this._ticket
  }

  private _finishRun(run: RunState, attached: boolean): void {
    this._setRunning(run.conversationId, false)
    if (this._run?.conversationId === run.conversationId) this._run = null
    // 回合结束，缓存快照以服务端历史为准（下次进入会重新拉取）。
    if (run.conversationId) this._views.delete(run.conversationId)
    // 切走期间跑完的回合：回到该会话时补拉服务端历史（含最终回答）。
    if (!attached && this.ui.conversationId && this.ui.conversationId === run.conversationId) {
      void this.loadConversation(run.conversationId)
    }
  }

  private _setRunning(conversationId: string, running: boolean): void {
    if (!conversationId) return
    const index = this.ui.runningIds.indexOf(conversationId)
    if (running && index < 0) this.ui.runningIds.push(conversationId)
    if (!running && index >= 0) this.ui.runningIds.splice(index, 1)
  }

  /** 视图切走：保留流与运行中账目，只把后续事件从视图上摘掉。 */
  private _detachRun(): void {
    if (this._run) this._run.detached = true
  }

  /** 记住当前会话已渲染的内容（切回来先还原，等服务端历史到达再覆盖）。 */
  private _snapshotView(): void {
    const id = this.ui.conversationId
    if (!id) return
    this._views.set(id, cloneView(this.view))
  }

  private _restoreView(id: string): void {
    const cached = this._views.get(id)
    if (!cached) return
    const copy = cloneView(cached)
    Object.assign(this.view, copy)
  }

  private _handleDifyEvent(
    payload: Record<string, any>,
    run: RunState,
  ): void {
    const eventName = String(payload?.event || '')
    const attached = this._attached(run)
    if (payload?.task_id) {
      this._taskId = String(payload.task_id)
      run.taskId = this._taskId
    }
    if (payload?.conversation_id) {
      const incoming = String(payload.conversation_id)
      // 运行中账目按服务端会话 id 记，即便视图已切走也要登记（侧栏据此显示进行中）。
      if (!run.conversationId) run.conversationId = incoming
      this._setRunning(run.conversationId, true)
      if (attached) {
        this.ui.conversationId = incoming
        if (!this.ui.conversations.some((item) => item.id === incoming)) {
          this.ui.conversations.push({
            id: incoming,
            name: '当前会话',
            updatedAt: Date.now(),
          })
        }
      }
    }
    if (!attached) {
      // 切走的回合继续写进该会话的缓存视图：切回来时内容是完整的。
      if (!run.conversationId) return
      const live = this.view
      this.view = this._viewFor(run.conversationId)
      try {
        this._applyEvent(payload, eventName, run, true)
      } finally {
        this.view = live
      }
      return
    }
    this._applyEvent(payload, eventName, run, false)
  }

  private _applyEvent(
    payload: Record<string, any>,
    eventName: string,
    run: RunState,
    detached: boolean,
  ): void {
    if (eventName === 'error') {
      const message = safeText(payload?.message || 'Dify 流返回了错误。')
      if (!detached) this.ui.error = message
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
      if (answer) run.platformText += answer
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
      if (!detached && this.view.terminal && !isWaiting(this.view.terminal.status)) {
        this.ui.running = false
      }
    }
    if (eventName === 'message_end') {
      const finalText = normalizeAnswer(run.platformText || String(payload?.answer || ''))
      if (finalText) mergeFinalAnswer(this.view, finalText)
    }
  }

  /** 切走期间的缓存视图（按会话）；首次访问时从空视图开始。 */
  private _viewFor(conversationId: string): TranscriptView {
    let cached = this._views.get(conversationId)
    if (!cached) {
      cached = newView()
      this._views.set(conversationId, cached)
    }
    return cached
  }
}

function isWaiting(status: string): boolean {
  return status === 'awaiting_user' || status === 'awaiting_approval'
}

/** 视图快照的深拷贝：entries/outputs/terminal 是纯数据，seen 是 Set。 */
function cloneView(view: TranscriptView): TranscriptView {
  const copy: TranscriptView = {
    entries: JSON.parse(JSON.stringify(view.entries ?? [])),
    outputs: JSON.parse(JSON.stringify(view.outputs ?? [])),
    terminal: view.terminal ? JSON.parse(JSON.stringify(view.terminal)) : null,
    running: view.running,
    platformAnswer: view.platformAnswer,
    warnings: [...(view.warnings ?? [])],
    ignored: view.ignored,
    seen: new Set(view.seen ?? []),
    activeAssistantId: view.activeAssistantId,
    activeReasoningId: view.activeReasoningId,
    optimisticUserId: view.optimisticUserId,
  }
  return copy
}

function safeError(error: unknown): string {
  if (error instanceof Error) return error.message.slice(0, 500)
  return String(error || '未知错误').slice(0, 500)
}

function safeText(value: unknown): string {
  return String(value || '').slice(0, 1000)
}

export type { DisplayEvent }
