import { AbstractAgent, type AgentSubscriber, type RunAgentInput, type RunAgentParameters, type RunAgentResult } from '@ag-ui/client'
import type { BaseEvent } from '@ag-ui/core'
import { Observable } from 'rxjs'
import { createDifyBlobAccumulator, isDifyBlobEvent } from './difyBlob'
import { extractAgUiEvent, normalizeDifyEvent } from './difyEventBridge'
import { MISSING_ANSWER_NOTICE, isLikelyWorkflowPlaceholder } from './difyHistoryMessages'
import { createDifyRunEmitter } from './difyRunAdapter'
import { listMessages, stopChat, streamChat, uploadFile as uploadDifyFile, type DifyUploadedFile } from './difyTransport'
import { copilotDifyDebug } from './debugLog'
import { buildInterruptResumePayload, type InterruptQuestion } from './question'

export interface DifyAgentConfig {
  baseUrl: string
  apiKey: string
  user: string
  stateId?: string
  token?: string
  inputs?: Record<string, unknown>
}

interface DifyAgentConfigRef {
  current: DifyAgentConfig
}

export interface DifyConversationChange {
  conversationId: string
  threadId: string
}

export interface DifyRunStatusChange extends DifyConversationChange {
  running: boolean
}

interface DifyAgentOptions {
  onConversationIdChange?: (change: DifyConversationChange) => void
  onRunStatusChange?: (change: DifyRunStatusChange) => void
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

function clonePlain<T>(value: T, fallback: T): T {
  const cloned = toPlain(value, new WeakSet<object>())
  return (cloned === undefined ? fallback : cloned) as T
}

function toPlain(value: any, seen: WeakSet<object>): any {
  if (value == null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value
  if (typeof value === 'bigint') return String(value)
  if (typeof value === 'function' || typeof value === 'symbol') return undefined
  if (Array.isArray(value)) return value.map((item) => toPlain(item, seen)).filter((item) => item !== undefined)
  if (typeof value !== 'object') return value
  if (seen.has(value)) return undefined
  seen.add(value)
  const output: Record<string, any> = {}
  for (const key of Object.keys(value)) {
    const child = toPlain(value[key], seen)
    if (child !== undefined) output[key] = child
  }
  seen.delete(value)
  return output
}

function sanitizeRunParameters(parameters?: RunAgentParameters): RunAgentParameters | undefined {
  if (!parameters) return parameters
  return {
    ...parameters,
    tools: clonePlain(parameters.tools || [], []),
    context: clonePlain(parameters.context || [], []),
    forwardedProps: clonePlain(parameters.forwardedProps || {}, {}),
  }
}

function latestUserMessage(messages: any[]) {
  return [...(messages || [])].reverse().find((message) => message?.role === 'user')
}

function normalizeLoadedHistoryMessages(messages: any[]) {
  return (messages || []).map((message) => {
    if (message?.role !== 'assistant' || typeof message.content !== 'string') return message
    if (!isLikelyWorkflowPlaceholder(message.content)) return message
    return {
      ...message,
      content: MISSING_ANSWER_NOTICE,
      metadata: {
        ...(message.metadata && typeof message.metadata === 'object' ? message.metadata : {}),
        originalPlaceholderContent: message.content,
      },
    }
  })
}

function textFromContent(content: any) {
  if (typeof content === 'string') return content.trim()
  if (!Array.isArray(content)) return String(content || '').trim()
  return content
    .filter((part) => part?.type === 'text')
    .map((part) => String(part?.text || ''))
    .join('\n')
    .trim()
}

function fileFromPart(part: any): DifyUploadedFile | null {
  const metadata = part?.metadata || {}
  const uploaded = metadata.difyUploadedFile || metadata.dify_uploaded_file || {}
  const id = String(
    uploaded.id ||
    uploaded.upload_file_id ||
    uploaded.uploadFileId ||
    metadata.upload_file_id ||
    metadata.uploadFileId ||
    metadata.difyUploadFileId ||
    '',
  )
  if (!id) return null
  const mimeType = String(uploaded.mimeType || uploaded.mime_type || metadata.mimeType || metadata.mime_type || part?.source?.mimeType || '')
  return {
    id,
    type: uploaded.type || part?.type ? String(uploaded.type || part?.type) : undefined,
    name: uploaded.name || metadata.filename ? String(uploaded.name || metadata.filename) : undefined,
    mimeType: mimeType || undefined,
    size: uploaded.size == null && metadata.size == null ? undefined : Number(uploaded.size ?? metadata.size),
  }
}

function lastUserMessageContent(messages: any[]) {
  return textFromContent(latestUserMessage(messages)?.content)
}

function lastUserMessageFiles(messages: any[]): DifyUploadedFile[] {
  const latestUser = latestUserMessage(messages)
  const files = latestUser?.files || latestUser?.attachments || []
  const directFiles = Array.isArray(files) ? files : []
  const contentFiles = Array.isArray(latestUser?.content)
    ? latestUser.content.map(fileFromPart).filter(Boolean)
    : []
  return [...directFiles, ...contentFiles]
    .map((file: any) => ({
      id: String(file?.id || file?.upload_file_id || file?.uploadFileId || ''),
      type: file?.type ? String(file.type) : undefined,
      name: file?.name ? String(file.name) : undefined,
      mimeType: file?.mimeType || file?.mime_type ? String(file.mimeType || file.mime_type) : undefined,
      size: file?.size == null ? undefined : Number(file.size),
    }))
    .filter((file: DifyUploadedFile) => file.id)
}

function resumePayload(parameters: RunAgentParameters | undefined) {
  return (parameters as any)?.forwardedProps?.command?.resume || null
}

function interruptEventPayload(parameters: RunAgentParameters | undefined) {
  return (parameters as any)?.forwardedProps?.command?.interruptEvent || null
}

function resumeAnswer(parameters: RunAgentParameters | undefined) {
  const resume = resumePayload(parameters)
  return typeof resume?.answer === 'string' ? resume.answer.trim() : ''
}

function interruptValueFromAgUiEvent(event: any) {
  if (event?.type !== 'RUN_FINISHED') return null
  const payload = event.result || {}
  const metadata = payload.executionMetadata || payload.execution_metadata || {}
  const outcome = event.outcome || null

  if (!(outcome?.type === 'interrupt' || metadata.finishReason === 'awaiting_user' || metadata.finish_reason === 'awaiting_user')) {
    return null
  }

  if (outcome?.interrupts?.[0]) {
    const intr = outcome.interrupts[0]
    return {
      id: intr.id || intr.toolCallId || '',
      question: intr.message || intr.reason || '',
      purpose: intr.metadata?.purpose || 'clarification',
      options: intr.metadata?.options || [],
      allowCustomInput: intr.metadata?.allowCustomInput ?? true,
      multiSelect: intr.metadata?.multiSelect ?? false,
      fields: intr.metadata?.fields || [],
    }
  }

  const question = metadata.question || {}
  return {
    id: question.id || question.toolCallId || question.tool_call_id || '',
    question: question.question || question.text || '',
    purpose: question.purpose || 'clarification',
    options: question.options || [],
    allowCustomInput: question.allowCustomInput ?? true,
    multiSelect: question.multiSelect ?? false,
    fields: question.fields || [],
  }
}

function conversationIdFromAgUiEvent(event: any) {
  if (event?.type !== 'RUN_FINISHED') return ''
  const result = event.result || {}
  const stateRef = result.state_ref || result.stateRef || {}
  return String(stateRef.conversation_id || stateRef.conversationId || '').trim()
}

function permissionResumePayloadFromText(question: InterruptQuestion | null, answer: string) {
  const text = String(answer || '').trim()
  if (!question || question.purpose !== 'permission' || !text) return null
  const selectedValue = matchingPermissionOptionValue(question, text) || permissionAliasValue(text)
  if (!selectedValue) return null
  return buildInterruptResumePayload(question, [selectedValue], '')
}

function matchingPermissionOptionValue(question: InterruptQuestion, answer: string) {
  const normalizedAnswer = normalizeChoice(answer)
  for (const option of question.options || []) {
    const candidates = [option.value, option.label, option.description]
    if (candidates.some((candidate) => candidate && normalizeChoice(candidate) === normalizedAnswer)) {
      return option.value || option.label
    }
  }
  return ''
}

function permissionAliasValue(answer: string) {
  const normalized = normalizeChoice(answer)
  const aliases: Record<string, string[]> = {
    allow_conversation: [
      'allow_conversation',
      'always_allow',
      'always allow',
      'allow always',
      'allow in conversation',
      'always allow in this conversation',
      '当前会话始终允许',
    ],
    allow_once: [
      'allow_once',
      'approve',
      'allow',
      'continue',
      'confirm',
      'yes',
      'y',
      'true',
      '允许一次',
      '继续执行',
      '允许',
    ],
    deny: ['deny', 'reject', 'cancel', 'stop', 'no', 'n', 'false', '拒绝', '取消', '停止'],
  }
  for (const [value, candidates] of Object.entries(aliases)) {
    if (candidates.some((candidate) => normalizeChoice(candidate) === normalized)) return value
  }
  return ''
}

function normalizeChoice(value: any) {
  return String(value || '').trim().toLowerCase()
}

let messageSeq = 0
function nextMessageId(prefix: string) {
  return `${prefix}_${++messageSeq}_${Math.random().toString(36).slice(2, 8)}`
}

function uploadedFilesActivity(files: DifyUploadedFile[]) {
  return {
    type: 'ACTIVITY_SNAPSHOT',
    messageId: nextMessageId('uploaded_files'),
    activityType: 'cc_agent.uploaded_files',
    content: {
      source: 'user_message',
      files,
    },
  } as BaseEvent
}

export class DifyAgUiAgent extends AbstractAgent {
  private configRef: DifyAgentConfigRef
  private options: DifyAgentOptions
  private conversationId = ''
  private currentTaskId = ''
  private abortController: AbortController | null = null
  private pendingInterrupt: InterruptQuestion | null = null

  constructor(config: DifyAgentConfig, agentId = 'default', configRef?: DifyAgentConfigRef, options: DifyAgentOptions = {}) {
    super({ agentId })
    this.configRef = configRef || {
      current: {
        ...config,
        inputs: { ...(config.inputs || {}) },
      },
    }
    this.options = options
  }

  private get config() {
    return this.configRef.current
  }

  updateConfig(next: Partial<DifyAgentConfig>) {
    this.configRef.current = {
      ...this.config,
      ...next,
      inputs: next.inputs === undefined ? { ...(this.config.inputs || {}) } : { ...(next.inputs || {}) },
    }
  }

  async uploadFile(file: File): Promise<DifyUploadedFile> {
    return uploadDifyFile({
      baseUrl: this.config.baseUrl,
      apiKey: this.config.apiKey,
      user: this.config.user,
      file,
    })
  }

  async loadHistory(conversationId: string) {
    const id = String(conversationId || '').trim()
    if (!id) return { loaded: false, messageCount: 0 }

    copilotDifyDebug('agent.history.load.start', {
      conversationId: id,
      currentConversationId: this.conversationId,
      currentMessages: this.messages.length,
    })
    const history = await listMessages({
      baseUrl: this.config.baseUrl,
      apiKey: this.config.apiKey,
      user: this.config.user,
      conversationId: id,
      limit: 20,
    })
    this.currentTaskId = ''
    this.pendingInterrupt = null
    const loadedMessages = normalizeLoadedHistoryMessages(deepClone(history.messages))
    this.setMessages(loadedMessages)
    this.setState({})
    this.setConversationId(id)
    copilotDifyDebug('agent.history.load.done', {
      conversationId: id,
      messageCount: history.messages.length,
      hasMore: history.hasMore,
      firstId: history.firstId,
      agentMessages: this.messages.length,
      sampleMessages: loadedMessages.slice(0, 4).map((message: any) => ({
        id: message?.id,
        role: message?.role,
        content: typeof message?.content === 'string' ? message.content.slice(0, 80) : message?.content,
      })),
    })
    return { loaded: true, messageCount: history.messages.length, hasMore: history.hasMore, firstId: history.firstId }
  }

  getConversationId() {
    return this.conversationId
  }

  private notifyConversationIdChange(conversationId: string) {
    this.options.onConversationIdChange?.({
      conversationId,
      threadId: this.threadId || 'default',
    })
  }

  private notifyRunStatusChange(running: boolean) {
    this.options.onRunStatusChange?.({
      conversationId: this.conversationId,
      threadId: this.threadId || 'default',
      running,
    })
  }

  setConversationId(conversationId: string) {
    const id = String(conversationId || '').trim()
    if (!id || id === this.conversationId) return
    this.conversationId = id
    this.notifyConversationIdChange(id)
  }

  clearConversation() {
    if (!this.conversationId && this.messages.length === 0) return
    this.conversationId = ''
    this.currentTaskId = ''
    this.pendingInterrupt = null
    this.setMessages([])
    this.setState({})
    this.notifyConversationIdChange('')
  }

  startNewConversation() {
    this.clearConversation()
  }

  async selectConversation(conversationId: string) {
    return this.loadHistory(conversationId)
  }

  override clone(): DifyAgUiAgent {
    const cloned = new DifyAgUiAgent(this.config, this.agentId || 'default', this.configRef, this.options)
    cloned.threadId = this.threadId
    cloned.messages = deepClone(this.messages)
    cloned.state = deepClone(this.state)
    cloned.isRunning = this.isRunning
    cloned.conversationId = this.conversationId
    cloned.currentTaskId = this.currentTaskId
    cloned.pendingInterrupt = deepClone(this.pendingInterrupt)
    return cloned
  }

  override run(input: RunAgentInput): Observable<BaseEvent> {
    return new Observable<BaseEvent>((observer) => {
      const ctx = this.buildRunContext(input)
      if (!ctx.query) {
        observer.complete()
        return
      }

      this.abortController = new AbortController()

      const run = async () => {
        try {
          const result = await streamChat({
            baseUrl: ctx.baseUrl,
            apiKey: this.config.apiKey,
            user: this.config.user,
            conversationId: this.conversationId || '',
            query: ctx.query,
            inputs: this.buildInputs(input, ctx.resumeResponse),
            files: ctx.files,
            signal: this.abortController!.signal,
          })
          if (ctx.resumeResponse || resumePayload(input as any)) {
            this.pendingInterrupt = null
          }

          const runId = input.runId || nextMessageId('run')
          const threadId = this.threadId || 'default'
          const emitter = createDifyRunEmitter(observer, { runId, threadId })
          let emittedRunStarted = false
          let emittedUploadedFiles = false
          let nativeAgUiSeen = false
          const blobAccumulator = createDifyBlobAccumulator()
          const emitUploadedFiles = () => {
            if (emittedUploadedFiles || ctx.files.length === 0) return
            observer.next(uploadedFilesActivity(ctx.files))
            emittedUploadedFiles = true
          }
          const ensureRunStarted = () => {
            if (emittedRunStarted) return
            emitter.emitRunStarted()
            emittedRunStarted = true
            emitUploadedFiles()
          }

          this.setConversationId(result.response.conversationId || this.conversationId)
          this.currentTaskId = result.response.taskId || this.currentTaskId

          for await (const rawEvent of result.events) {
            if (rawEvent?.task_id) this.currentTaskId = String(rawEvent.task_id)
            if (rawEvent?.conversation_id) this.setConversationId(String(rawEvent.conversation_id))

            const blobActivity = blobAccumulator.ingest(rawEvent)
            if (isDifyBlobEvent(rawEvent)) {
              if (blobActivity) {
                if (!emittedRunStarted) ensureRunStarted()
                observer.next({
                  type: 'ACTIVITY_SNAPSHOT',
                  messageId: blobActivity.messageId,
                  activityType: blobActivity.activityType,
                  content: blobActivity.content,
                } as BaseEvent)
              }
              continue
            }

            const aguiEvent = extractAgUiEvent(rawEvent)
            if (aguiEvent) {
              nativeAgUiSeen = true
              if (!emittedRunStarted && aguiEvent.type !== 'RUN_STARTED') ensureRunStarted()
              emittedRunStarted = emittedRunStarted || aguiEvent.type === 'RUN_STARTED'
              const stateRefConversationId = conversationIdFromAgUiEvent(aguiEvent)
              if (stateRefConversationId) this.setConversationId(stateRefConversationId)
              const interruptValue = interruptValueFromAgUiEvent(aguiEvent)
              if (interruptValue) {
                this.pendingInterrupt = interruptValue
                observer.next({
                  type: 'CUSTOM',
                  name: 'on_interrupt',
                  value: interruptValue,
                } as BaseEvent)
              } else if (aguiEvent.type === 'RUN_FINISHED' || aguiEvent.type === 'RUN_ERROR') {
                this.pendingInterrupt = null
              }
              observer.next(aguiEvent as BaseEvent)
              if (aguiEvent.type === 'RUN_STARTED') emitUploadedFiles()
              continue
            }

            if (nativeAgUiSeen && rawEvent?.event !== 'error') {
              continue
            }

            const normalizedEvents = normalizeDifyEvent(rawEvent)
            if (normalizedEvents.length === 0) continue

            ensureRunStarted()
            for (const normalized of normalizedEvents) {
              if (normalized.kind === 'error') {
                observer.error(new Error(String(normalized.message || 'Dify event error')))
                return
              }
              emitter.emitNormalized(normalized)
            }
          }

          emitter.closeOpenMessages()
          observer.complete()
        } catch (error: any) {
          if (error?.name === 'AbortError') {
            observer.complete()
          } else {
            observer.error(error)
          }
        } finally {
          this.currentTaskId = ''
          this.abortController = null
        }
      }

      run()
    })
  }

  override async runAgent(parameters?: RunAgentParameters, subscriber?: AgentSubscriber): Promise<RunAgentResult> {
    this.messages = clonePlain(this.messages, [])
    this.state = clonePlain(this.state, {})
    this.notifyRunStatusChange(true)
    try {
      return await super.runAgent(sanitizeRunParameters(parameters), subscriber)
    } finally {
      this.notifyRunStatusChange(false)
    }
  }

  override abortRun(): void {
    const taskId = this.currentTaskId
    this.currentTaskId = ''
    if (taskId && this.config.baseUrl && this.config.apiKey) {
      void stopChat({
        baseUrl: this.config.baseUrl,
        apiKey: this.config.apiKey,
        user: this.config.user,
        taskId,
      }).catch(() => undefined)
    }
    this.abortController?.abort()
  }

  override async connectAgent(
    _parameters: RunAgentParameters = {},
  ): Promise<RunAgentResult> {
    return { newMessages: [], result: undefined }
  }

  private buildRunContext(input: RunAgentInput) {
    const baseUrl = String(this.config.baseUrl || '').replace(/\/+$/, '')
    const messages = (input as any).messages || []
    const explicitResumeAnswer = resumeAnswer(input as any)
    const query = explicitResumeAnswer || lastUserMessageContent(messages)
    const resumeResponse = explicitResumeAnswer ? null : permissionResumePayloadFromText(this.pendingInterrupt, query)
    const isResume = Boolean(explicitResumeAnswer || resumeResponse)
    const files = isResume ? [] : lastUserMessageFiles(messages)
    return { baseUrl, query, files, resumeResponse }
  }

  private buildInputs(input: RunAgentInput, implicitResume: Record<string, unknown> | null = null) {
    const resume = resumePayload(input as any) || implicitResume
    const interruptEvent = interruptEventPayload(input as any) || (implicitResume ? this.pendingInterrupt : null)
    const inputs: Record<string, unknown> = {
      ...(this.config.inputs || {}),
    }

    if (this.config.token) inputs.token = this.config.token

    if (resume && typeof resume === 'object') {
      inputs.user_prompt_response = {
        ...(resume as Record<string, unknown>),
        promptId:
          (resume as any).promptId ||
          (interruptEvent && typeof interruptEvent === 'object' ? (interruptEvent as any).id : '') ||
          '',
      }
    }

    return inputs
  }
}
