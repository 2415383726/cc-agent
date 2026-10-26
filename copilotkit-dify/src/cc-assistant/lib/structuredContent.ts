import { z } from 'zod'
import { normalizeChartSpec, type ChartSpec } from './chartSpec'

const metaSchema = z.object({
  title: z.string().trim().min(1),
  description: z.string().trim().min(1).optional(),
  status: z.string().trim().min(1).optional(),
}).strict()

const actionSchema = z.object({
  id: z.string().trim().min(1),
  label: z.string().trim().min(1),
  prompt: z.string().trim().min(1),
  variant: z.enum(['primary', 'secondary']).optional(),
}).strict()

const scalarSchema = z.union([
  z.string(),
  z.number().finite(),
  z.boolean(),
  z.array(z.string()),
])

const fieldSchema = z.object({
  label: z.string().trim().min(1),
  value: scalarSchema,
  format: z.enum(['text', 'number', 'date', 'datetime', 'status', 'tags']).optional(),
}).strict()

export const recordSpecSchema = z.object({
  version: z.literal(1),
  meta: metaSchema,
  sections: z.array(z.object({
    title: z.string().trim().min(1).optional(),
    fields: z.array(fieldSchema).min(1),
  }).strict()).min(1),
  actions: z.array(actionSchema).optional(),
}).strict()

export const tableSpecSchema = z.object({
  version: z.literal(1),
  meta: metaSchema,
  columns: z.array(z.object({
    key: z.string().trim().min(1),
    label: z.string().trim().min(1),
    format: z.enum(['text', 'number', 'date', 'datetime', 'status', 'tags']).optional(),
    align: z.enum(['start', 'center', 'end']).optional(),
    sortable: z.boolean().optional(),
  }).strict()).min(1),
  rows: z.array(z.object({
    id: z.string().trim().min(1),
    values: z.record(scalarSchema),
  }).strict()),
  emptyText: z.string().trim().min(1).optional(),
  actions: z.array(actionSchema).optional(),
}).strict()

export const compareSpecSchema = z.object({
  version: z.literal(1),
  meta: metaSchema,
  subjects: z.array(z.object({
    id: z.string().trim().min(1),
    label: z.string().trim().min(1),
    description: z.string().trim().min(1).optional(),
  }).strict()).min(2).max(4),
  criteria: z.array(z.object({
    id: z.string().trim().min(1),
    label: z.string().trim().min(1),
    values: z.record(scalarSchema),
    highlight: z.string().trim().min(1).optional(),
    note: z.string().trim().min(1).optional(),
  }).strict()).min(1),
  actions: z.array(actionSchema).optional(),
}).strict()

export const timelineSpecSchema = z.object({
  version: z.literal(1),
  meta: metaSchema,
  items: z.array(z.object({
    id: z.string().trim().min(1),
    time: z.string().trim().min(1),
    title: z.string().trim().min(1),
    description: z.string().trim().min(1).optional(),
    status: z.string().trim().min(1).optional(),
  }).strict()).min(1),
  actions: z.array(actionSchema).optional(),
}).strict()

export type UiMeta = z.infer<typeof metaSchema>
export type UiAction = z.infer<typeof actionSchema>
export type UiScalar = z.infer<typeof scalarSchema>
export type RecordSpec = z.infer<typeof recordSpecSchema>
export type TableSpec = z.infer<typeof tableSpecSchema>
export type CompareSpec = z.infer<typeof compareSpecSchema>
export type TimelineSpec = z.infer<typeof timelineSpecSchema>
export type BusinessSurfaceType = 'record' | 'table' | 'compare' | 'timeline'

export type StructuredContentPart =
  | { type: 'markdown'; content: string }
  | { type: 'record'; spec: RecordSpec }
  | { type: 'table'; spec: TableSpec }
  | { type: 'compare'; spec: CompareSpec }
  | { type: 'timeline'; spec: TimelineSpec }
  | { type: 'chart'; spec: ChartSpec }
  | { type: 'chart-pending' }
  | { type: 'surface-pending'; surface: BusinessSurfaceType }
  | { type: 'mermaid'; code: string }

const protocolSchemas = {
  'cc-record': recordSpecSchema,
  'cc-table': tableSpecSchema,
  'cc-compare': compareSpecSchema,
  'cc-timeline': timelineSpecSchema,
} as const

const protocolTypes = {
  'cc-record': 'record',
  'cc-table': 'table',
  'cc-compare': 'compare',
  'cc-timeline': 'timeline',
} as const

const STRUCTURED_BLOCK_RE = /```[ \t]*(cc-record|cc-table|cc-compare|cc-timeline|cc-chart|mermaid)[ \t]*\r?\n([\s\S]*?)\r?\n?```/ig
const PENDING_STRUCTURED_BLOCK_RE = /```[ \t]*(cc-record|cc-table|cc-compare|cc-timeline|cc-chart)[ \t]*\r?\n([\s\S]*)$/i
const CHART_SPEC_CACHE_LIMIT = 100
const BUSINESS_SPEC_CACHE_LIMIT = 200
const chartSpecCache = new Map<string, ChartSpec>()
const businessPartCache = new Map<string, StructuredContentPart>()
const pendingSurfaceParts: Record<BusinessSurfaceType, StructuredContentPart> = {
  record: { type: 'surface-pending', surface: 'record' },
  table: { type: 'surface-pending', surface: 'table' },
  compare: { type: 'surface-pending', surface: 'compare' },
  timeline: { type: 'surface-pending', surface: 'timeline' },
}

export function parseStructuredContentParts(content: unknown): StructuredContentPart[] {
  if (typeof content !== 'string') return []

  const parts: StructuredContentPart[] = []
  let consumedUntil = 0
  let sawFence = false
  const regex = new RegExp(STRUCTURED_BLOCK_RE)
  let match: RegExpExecArray | null

  while ((match = regex.exec(content)) !== null) {
    sawFence = true
    pushMarkdown(parts, content.slice(consumedUntil, match.index))
    const parsed = parseBlock(match[1].toLowerCase(), match[2].trim())
    if (parsed) parts.push(parsed)
    else pushMarkdown(parts, match[0])
    consumedUntil = match.index + match[0].length
  }

  const trailing = content.slice(consumedUntil)
  const pendingMatch = PENDING_STRUCTURED_BLOCK_RE.exec(trailing)
  if (pendingMatch && !/^```/m.test(pendingMatch[2])) {
    pushMarkdown(parts, trailing.slice(0, pendingMatch.index))
    const language = pendingMatch[1].toLowerCase()
    if (language === 'cc-chart') {
      const spec = normalizeChartBlock(pendingMatch[2].trim())
      parts.push(spec ? { type: 'chart', spec } : { type: 'chart-pending' })
    } else {
      const surface = protocolTypes[language as keyof typeof protocolTypes]
      if (surface) parts.push(pendingSurfaceParts[surface])
    }
    return parts
  }

  if (!parts.some(part => part.type !== 'markdown')) {
    return sawFence ? parts : []
  }

  pushMarkdown(parts, trailing)
  return parts
}

function parseBlock(language: string, body: string): StructuredContentPart | null {
  if (language === 'cc-chart') {
    const spec = normalizeChartBlock(body)
    return spec ? { type: 'chart', spec } : null
  }
  if (language === 'mermaid') return body ? { type: 'mermaid', code: body } : null

  const schema = protocolSchemas[language as keyof typeof protocolSchemas]
  const type = protocolTypes[language as keyof typeof protocolTypes]
  if (!schema || !type) return null
  const cacheKey = `${language}\n${body}`
  const cached = businessPartCache.get(cacheKey)
  if (cached) return cached
  const raw = parseJson(body)
  const result = schema.safeParse(raw)
  if (!result.success) return null
  const part = { type, spec: result.data } as StructuredContentPart
  if (businessPartCache.size >= BUSINESS_SPEC_CACHE_LIMIT) {
    const oldestKey = businessPartCache.keys().next().value
    if (oldestKey !== undefined) businessPartCache.delete(oldestKey)
  }
  businessPartCache.set(cacheKey, part)
  return part
}

function normalizeChartBlock(body: string): ChartSpec | null {
  const cached = chartSpecCache.get(body)
  if (cached) return cached
  const spec = normalizeChartSpec(body)
  if (!spec) return null
  if (chartSpecCache.size >= CHART_SPEC_CACHE_LIMIT) {
    const oldestKey = chartSpecCache.keys().next().value
    if (oldestKey !== undefined) chartSpecCache.delete(oldestKey)
  }
  chartSpecCache.set(body, spec)
  return spec
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch (_) {
    return null
  }
}

function pushMarkdown(parts: StructuredContentPart[], content: string) {
  const trimmed = content.trim()
  if (trimmed) parts.push({ type: 'markdown', content: trimmed })
}

export function displayValue(value: UiScalar | undefined): string {
  if (Array.isArray(value)) return value.join('、')
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value ?? '').trim()
}
