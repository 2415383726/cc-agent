/**
 * 问卷草稿状态机（pure TS，框架无关）。
 *
 * 平移自 DeepSeek Harness ui-user-questions（MIT）：
 * - `QuestionDraftAnswer` / `QuestionDraftProgress`：draft-store.ts 的持久形状
 *   （本应用没有 Session store 基础设施，持久层换成组件内 state；形状逐字保留）。
 * - `parseRecommendedLabel` / 推荐预选：QuestionComposer.tsx 的同名纯函数逐字平移。
 * - `isQuestionDraftProgress`：QuestionComposer.tsx 的持久进度校验逐字平移。
 *
 * 有意偏离（本仓库 wire 契约）：上游草稿 selection 存 option **label**（答案
 * 协议 `selected: labels[]`）；pi_dify 的 answers 契约是 option **id**（labels
 * 仅作服务端回退别名）。因此本模块的 `selected` 存 option id，`recommendedOptions`
 * 返回推荐项的 id。状态机形状与判定逻辑未改。
 */

/** One in-progress answer, including an explicit skip.（draft-store.ts 逐字） */
export interface QuestionDraftAnswer {
  /** Offered options currently selected.（本应用存 option id） */
  selected: string[]
  /** Human-authored alternative or additional answer. */
  custom: string
  /** Whether the user explicitly skipped this question. */
  skipped: boolean
}

/** Navigation and answer drafts for one pending request.（draft-store.ts 逐字） */
export interface QuestionDraftProgress {
  /** Current question index. */
  index: number
  /** One draft per question, in request order. */
  drafts: QuestionDraftAnswer[]
}

/** 选项/问题输入形状：projection/transcript.ts 的 Question 的最小切片。 */
export interface DraftQuestion {
  id: string
  type: 'single' | 'multi' | 'text'
  options?: { id: string; label: string; description?: string }[]
  required?: boolean
  min_selections?: number
  max_selections?: number
}

/**
 * Split the conventional recommendation suffix without changing the answer value.
 *（QuestionComposer.tsx parseRecommendedLabel 逐字）
 */
export function parseRecommendedLabel(label: string): { label: string; recommended: boolean } {
  const suffix = /\s*(?:\((?:recommended|推荐)\)|（(?:recommended|推荐)）)\s*$/i
  return suffix.test(label)
    ? { label: label.replace(suffix, ''), recommended: true }
    : { label, recommended: false }
}

/**
 * Implicit draft selection the user still submits: every marked choice of a
 * multi-select question, or a marked first choice of a single-select question.
 *（QuestionComposer.tsx recommendedOptions 平移；返回 option id 而非 label。）
 */
export function recommendedOptions(question: DraftQuestion): string[] {
  const options = question.options ?? []
  const candidates = question.type === 'multi' ? options : options.slice(0, 1)
  return candidates
    .filter((option) => parseRecommendedLabel(option.label).recommended)
    .map((option) => option.id)
}

/** Accept persisted progress only when it still describes this question batch.（逐字） */
export function isQuestionDraftProgress(value: unknown, questionCount: number): value is QuestionDraftProgress {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const progress = value as Record<string, unknown>
  if (typeof progress.index !== 'number' || !Number.isInteger(progress.index)
    || progress.index < 0 || progress.index >= questionCount
    || !Array.isArray(progress.drafts) || progress.drafts.length !== questionCount) return false
  return progress.drafts.every((item: unknown) => {
    if (typeof item !== 'object' || item === null || Array.isArray(item)) return false
    const draft = item as Record<string, unknown>
    return Array.isArray(draft.selected) && draft.selected.every((label: unknown) => typeof label === 'string')
      && typeof draft.custom === 'string' && typeof draft.skipped === 'boolean'
  })
}

/** A live card seeds its drafts with the asker's recommendations.（QuestionComposer initialDrafts 活卡半区） */
export function emptyDrafts(questions: readonly DraftQuestion[]): QuestionDraftAnswer[] {
  return questions.map((item) => ({
    selected: recommendedOptions(item),
    custom: '',
    skipped: false,
  }))
}

/**
 * Recorded answers echo the question ids rather than their order.
 *（QuestionComposer initialDrafts review 半区平移；pi_dify answers：
 * Record<questionId, optionId | optionId[] | text>。）
 */
export function draftsWithRecord(
  questions: readonly DraftQuestion[],
  answers: Record<string, string | string[]> | undefined,
): QuestionDraftAnswer[] {
  return questions.map((item) => {
    const value = answers?.[item.id]
    // 上游 review 记录区分 selected 与 custom 两个字段；我们的 wire 把
    // single 的 custom 折叠进同一个字符串值，这里按「不在选项 id 集合内」
    // 还原为 custom 文本，其余按选项 id 还原为选中态。
    const optionIds = new Set((item.options ?? []).map((option) => option.id))
    const custom =
      item.type === 'text'
        ? typeof value === 'string'
          ? value
          : ''
        : typeof value === 'string' && value !== '' && !optionIds.has(value)
          ? value
          : ''
    const selected =
      Array.isArray(value)
        ? [...value]
        : typeof value === 'string' && value !== '' && item.type !== 'text' && optionIds.has(value)
          ? [value]
          : []
    return {
      selected,
      custom,
      // A recorded answer with no selection and no custom text was skipped.
      skipped: value !== undefined && selected.length === 0 && custom === '',
    }
  })
}

/**（QuestionComposer.tsx answered/completed 平移） */
export function answered(item: QuestionDraftAnswer): boolean {
  return item.selected.length > 0 || item.custom.trim() !== ''
}

export function completed(item: QuestionDraftAnswer): boolean {
  return answered(item) || item.skipped
}

/** 提交校验结果：缺失/越界的题目下标与上游 feedback 文案键。 */
export type DraftRejection =
  | { ok: true }
  | { ok: false; index: number; reason: 'incomplete' | 'min' | 'max' }

/**
 * Submit-time validation, aligned with pi_dify validate_question_answer:
 * a required question must be answered (an explicit skip of a required
 * question is rejected server-side, so it is rejected here too), and a
 * multi-select answer must stay within [min_selections, max_selections].
 */
export function validateDrafts(
  questions: readonly DraftQuestion[],
  drafts: readonly QuestionDraftAnswer[],
): DraftRejection {
  for (let index = 0; index < questions.length; index += 1) {
    const question = questions[index]!
    const draft = drafts[index]!
    const required = question.required !== false
    if (!answered(draft)) {
      if (required) return { ok: false, index, reason: 'incomplete' }
      continue
    }
    if (question.type === 'multi') {
      const count = draft.selected.length
      const minimum = question.min_selections
      const maximum = question.max_selections
      if (minimum !== undefined && minimum !== null && count < minimum) {
        return { ok: false, index, reason: 'min' }
      }
      if (maximum !== undefined && maximum !== null && count > maximum) {
        return { ok: false, index, reason: 'max' }
      }
    }
  }
  return { ok: true }
}

/**
 * Wire mapping (pi_dify answers: option ids / ids array / text string).
 * 上游 QuestionAnswer 的 per-item 形状（selected + custom）在这里折叠成
 * pi_dify 的 Record<questionId, value>：
 * - skipped 或未作答 → 不写入（服务端对可选题按缺失处理）；
 * - single：custom 非空提交 custom（上游清空 selected 只发 custom），否则选项 id；
 * - multi：选项 id 数组（custom 文本在 pi_dify 契约中没有通道，不混入数组）；
 * - text：裁剪后的文本。
 */
export function answersOf(
  questions: readonly DraftQuestion[],
  drafts: readonly QuestionDraftAnswer[],
): Record<string, string | string[]> {
  const answers: Record<string, string | string[]> = {}
  for (let index = 0; index < questions.length; index += 1) {
    const question = questions[index]!
    const value = drafts[index]!
    const custom = value.custom.trim()
    if (question.type === 'text') {
      if (custom !== '') answers[question.id] = custom
      continue
    }
    if (custom !== '' && question.type !== 'multi') {
      answers[question.id] = custom
      continue
    }
    if (value.selected.length > 0) {
      answers[question.id] = question.type === 'multi' ? [...value.selected] : value.selected[0]!
    }
  }
  return answers
}
