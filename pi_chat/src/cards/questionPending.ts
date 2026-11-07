/**
 * 问卷卡倒计时/等待状态机（pure TS，框架无关）。
 *
 * 平移自 DeepSeek Harness ui-user-questions contract/slots.ts 的
 * `PendingQuestion`（MIT），按票据要求逐字保留其草稿/倒计时状态机，剥离
 * waterfall 传输面：本应用的提交通道是 Dify controller（新 Dify 轮次的
 * `inputs.interaction` JSON），不存在 Host waterfall / Remote rpc / composer
 * seat / sibling 注册表，因此以下成员没有对应物，已删除：
 * - `attachWaterfall` / `detachWaterfall` / `createWaterfallRequest`（waterfall 传输）
 * - `attachRpc` / `answer()`（rpc 通道；提交改由组件 emit 给 controller）
 * - `attachSeat` / `dismiss()` / `delegate()`（面板座位与转发）
 * - `state: open|continued`（上游投影行的续聊状态；本应用由 entry.status 驱动只读）
 *
 * 保留并逐字平移的核心：倒计时归属 carrier 而非组件（面板收起再展开、
 * 组件重挂载都不丢表），`takeTime`（慢慢回答）/`holdFocus`/`releaseFocus`
 * （聚焦暂停）/`engage`（首笔编辑永久停表）的等待语义，以及到点
 * `timeout()` 后关闭作答通道。上游 timeout 会以 ASK_TIMED_OUT 拒绝
 * waterfall；这里没有传输层，改为置 `timedOut` 并停表，作答入口随即关闭。
 */

/** Reactive card state read by every mounted presentation of one question.（逐字，裁剪通道字段） */
export interface QuestionCardSnapshot {
  /** User-visible foreground wait presentation. */
  readonly waitState: 'counting' | 'focused' | 'editing' | 'waiting'
  /**
   * Foreground countdown presentation, absent for a request that carried no
   * deadline. The card owns the ticking, so a hidden panel keeps counting and
   * still times out; `running` is false while a hold or an edit froze it.
   */
  readonly countdown: { readonly remainingMs: number; readonly running: boolean } | undefined
  /** Whether an answer may still be submitted through the controller channel. */
  readonly canSubmit: boolean
}

/** One answerable card carrier（PendingQuestion 的倒计时半区平移）. */
export class QuestionPending {
  readonly key: string
  #timedWait = false
  #timer: ReturnType<typeof setInterval> | undefined
  #deadline: number | undefined
  #remainingMs: number | undefined
  #focused = false
  #engaged = false
  #held = false
  #timedOut = false
  #disposed = false
  readonly #listeners = new Set<() => void>()
  #snapshot: QuestionCardSnapshot

  /**
   * @param key - render identity（本应用用 pendingId）。
   * @param deadline - 问卷 `expires_at`（epoch ms）；absent for a blocking request（无可倒计时不报错）。
   */
  constructor(key: string, deadline?: number) {
    this.key = key
    this.#timedWait = deadline !== undefined
    this.#deadline = deadline
    this.#snapshot = this.createSnapshot()
    this.#reschedule()
  }

  /** Subscribe to card state changes.（逐字） */
  readonly subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener)
    return () => {
      this.#listeners.delete(listener)
    }
  }

  /** Read the stable current card state.（逐字） */
  readonly snapshot = (): QuestionCardSnapshot => this.#snapshot

  private createSnapshot(): QuestionCardSnapshot {
    const waitState = this.#held
      ? 'waiting'
      : this.#engaged ? 'editing' : this.#focused ? 'focused' : 'counting'
    return {
      waitState,
      countdown: this.#timedWait
        ? {
          remainingMs: this.#deadline === undefined
            ? this.#remainingMs ?? 0
            : Math.max(0, this.#deadline - Date.now()),
          running: this.#deadline !== undefined,
        }
        : undefined,
      canSubmit: !this.#timedOut,
    }
  }

  private publish(): void {
    this.#snapshot = this.createSnapshot()
    this.#reschedule()
    for (const listener of this.#listeners) listener()
  }

  /**
   * Own the countdown here rather than in a mounted component: the panel can be
   * hidden and remounted while the request stands, and a timer that died with
   * the component would leave the tool call waiting past its deadline.（逐字）
   */
  #reschedule(): void {
    const wanted = this.#deadline !== undefined && !this.#timedOut && !this.#disposed
    if (wanted === (this.#timer !== undefined)) return
    if (!wanted) {
      clearInterval(this.#timer)
      this.#timer = undefined
      return
    }
    this.#timer = setInterval(() => {
      this.#tick()
    }, 1000)
  }

  #tick(): void {
    const deadline = this.#deadline
    if (deadline === undefined) return
    if (Date.now() >= deadline) {
      this.timeout()
      return
    }
    this.publish()
  }

  /** Stop this card's countdown indefinitely; the request then waits like a blocking question.（逐字） */
  takeTime(): void {
    if (this.#held) return
    this.#held = true
    this.#focused = false
    this.#remainingMs = undefined
    this.#deadline = undefined
    this.publish()
  }

  /**
   * Record focus even before an edit, freezing a pristine countdown.（逐字，去 waterfall 分支）
   * @param now - current epoch time.
   */
  holdFocus(now = Date.now()): void {
    if (this.#held || this.#engaged || this.#focused) return
    this.#remainingMs = this.#deadline === undefined ? undefined : Math.max(0, this.#deadline - now)
    this.#deadline = undefined
    this.#focused = true
    this.publish()
  }

  /** Resume a pristine countdown after the answer surface loses focus.（逐字） */
  releaseFocus(now = Date.now()): void {
    if (!this.#focused) return
    this.#focused = false
    this.#deadline = this.#timedWait && this.#remainingMs !== undefined ? now + this.#remainingMs : undefined
    this.#remainingMs = undefined
    this.publish()
  }

  /**
   * Keep the first edited draft answerable without a foreground deadline.（逐字）
   * @param now - current epoch time used to preserve the remaining duration.
   */
  engage(now = Date.now()): void {
    if (this.#held || this.#engaged) return
    if (this.#remainingMs === undefined && this.#deadline !== undefined) {
      this.#remainingMs = Math.max(0, this.#deadline - now)
    }
    this.#engaged = true
    this.#focused = false
    this.#deadline = undefined
    this.publish()
  }

  /**
   * Local countdown reached zero: close the answer channel and keep the card.
   *（上游以 ASK_TIMED_OUT 拒绝 waterfall；本应用仅关闭作答通道，提交与否
   * 最终仍由服务端 expires_at 校验裁决。）
   */
  timeout(): void {
    if (this.#held || this.#engaged || this.#focused) return
    this.#timedOut = true
    this.#timedWait = false
    this.#deadline = undefined
    this.publish()
  }

  /** Stop the interval and drop listeners; the carrier never outlives its card. */
  dispose(): void {
    this.#disposed = true
    if (this.#timer !== undefined) {
      clearInterval(this.#timer)
      this.#timer = undefined
    }
    this.#listeners.clear()
  }
}
