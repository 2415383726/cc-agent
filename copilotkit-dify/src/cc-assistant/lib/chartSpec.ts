import { z } from 'zod'

export const CHART_TYPES = ['bar', 'line', 'pie', 'scatter', 'radar'] as const
export const VALUE_FORMATS = ['compact', 'integer', 'raw', 'percent'] as const

export type ChartType = typeof CHART_TYPES[number]
export type ValueFormat = typeof VALUE_FORMATS[number]

export interface ChartMeta {
  title: string
  description?: string
  footer?: string
}

export interface ChartSeriesSpec {
  dataKey: string
  label?: string
  axisLabel?: string
  valueFormat?: ValueFormat
  valuePrefix?: string
  valueSuffix?: string
  decimals?: number
}

export interface ChartSpec {
  version: 1
  chartType: ChartType
  meta: ChartMeta
  data: Array<Record<string, string | number>>
  xKey?: string
  xAxisLabel?: string
  series?: ChartSeriesSpec[]
  orientation?: 'vertical' | 'horizontal'
  labelKey?: string
  nameKey?: string
  valueKey?: string
  valueFormat?: ValueFormat
  valuePrefix?: string
  valueSuffix?: string
  decimals?: number
  maxKey?: string
}

const nonEmptyString = z.string().trim().min(1)
const finiteNumber = z.number().finite()
const dataRowSchema = z.record(z.union([z.string(), finiteNumber]))
const valueFormatSchema = z.enum(VALUE_FORMATS)

const metaSchema = z.object({
  title: nonEmptyString.max(120),
  description: z.string().trim().max(320).optional(),
  footer: z.string().trim().max(200).optional(),
}).strict()

const seriesSchema = z.object({
  dataKey: nonEmptyString,
  label: z.string().trim().max(80).optional(),
  axisLabel: z.string().trim().max(80).optional(),
  valueFormat: valueFormatSchema.optional(),
  valuePrefix: z.string().max(24).optional(),
  valueSuffix: z.string().max(24).optional(),
  decimals: z.number().int().min(0).max(6).optional(),
}).strict()

const commonShape = { version: z.literal(1), meta: metaSchema }

const cartesianSchema = z.object({
  ...commonShape,
  chartType: z.enum(['bar', 'line']),
  xKey: nonEmptyString,
  xAxisLabel: z.string().trim().max(80).optional(),
  series: z.array(seriesSchema).min(1).max(6),
  orientation: z.enum(['vertical', 'horizontal']).optional(),
  data: z.array(dataRowSchema).min(1).max(100),
}).strict()

const scatterSchema = z.object({
  ...commonShape,
  chartType: z.literal('scatter'),
  xKey: nonEmptyString,
  xAxisLabel: z.string().trim().max(80).optional(),
  labelKey: z.string().trim().min(1).optional(),
  series: z.array(seriesSchema).min(1).max(4),
  data: z.array(dataRowSchema).min(1).max(500),
}).strict()

const pieSchema = z.object({
  ...commonShape,
  chartType: z.literal('pie'),
  nameKey: nonEmptyString,
  valueKey: nonEmptyString,
  valueFormat: valueFormatSchema.optional(),
  valuePrefix: z.string().max(24).optional(),
  valueSuffix: z.string().max(24).optional(),
  decimals: z.number().int().min(0).max(6).optional(),
  data: z.array(dataRowSchema).min(2).max(12),
}).strict()

const radarSchema = z.object({
  ...commonShape,
  chartType: z.literal('radar'),
  nameKey: nonEmptyString,
  maxKey: z.string().trim().min(1).optional(),
  series: z.array(seriesSchema).min(1).max(4),
  data: z.array(dataRowSchema).min(3).max(10),
}).strict()

const chartSpecSchema = z.discriminatedUnion('chartType', [cartesianSchema, scatterSchema, pieSchema, radarSchema])

export function normalizeChartSpec(value: unknown): ChartSpec | null {
  const raw = typeof value === 'string' ? parseJson(value) : value
  const parsed = chartSpecSchema.safeParse(raw)
  if (!parsed.success) return null
  const spec = parsed.data as ChartSpec
  return validateDataMappings(spec) ? spec : null
}

function validateDataMappings(spec: ChartSpec): boolean {
  if (spec.chartType === 'pie') {
    return spec.data.every((row) => typeof row[spec.nameKey!] === 'string' && isFiniteNumber(row[spec.valueKey!]) && Number(row[spec.valueKey!]) >= 0)
  }
  if (spec.chartType === 'radar') {
    return spec.data.every((row) => typeof row[spec.nameKey!] === 'string' && spec.series!.every((item) => isFiniteNumber(row[item.dataKey])) && (!spec.maxKey || (isFiniteNumber(row[spec.maxKey]) && Number(row[spec.maxKey]) > 0)))
  }
  if (spec.chartType === 'scatter') {
    return spec.data.every((row) => isFiniteNumber(row[spec.xKey!]) && spec.series!.every((item) => isFiniteNumber(row[item.dataKey])) && (!spec.labelKey || typeof row[spec.labelKey] === 'string'))
  }
  return spec.data.every((row) => (typeof row[spec.xKey!] === 'string' || isFiniteNumber(row[spec.xKey!])) && spec.series!.every((item) => isFiniteNumber(row[item.dataKey])))
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch (_) {
    return null
  }
}