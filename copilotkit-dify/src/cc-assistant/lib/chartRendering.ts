import type { ChartSeriesSpec, ChartSpec, ValueFormat } from './chartSpec'

export const ANSWER_CHART_PALETTE = ['#4C91F7', '#5BC47A', '#F58A5A', '#F3CB59', '#A98AF3', '#55B8C8']

export interface ChartTheme {
  text: string
  muted: string
  grid: string
  surface: string
  palette: string[]
  reducedMotion?: boolean
}

export const DEFAULT_CHART_THEME: ChartTheme = {
  text: '#111827',
  muted: '#6B7280',
  grid: '#E5E7EB',
  surface: '#FFFFFF',
  palette: ANSWER_CHART_PALETTE,
}

type FormatSource = Pick<ChartSeriesSpec, 'valueFormat' | 'valuePrefix' | 'valueSuffix' | 'decimals'>

export function formatChartValue(value: unknown, source: FormatSource = {}): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return String(value ?? '')
  const format = source.valueFormat || 'raw'
  const decimals = source.decimals
  let body: string
  if (format === 'compact') {
    body = new Intl.NumberFormat('zh-CN', {
      notation: 'compact',
      maximumFractionDigits: decimals ?? 1,
    }).format(value)
  } else if (format === 'integer') {
    body = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value)
  } else {
    body = new Intl.NumberFormat('zh-CN', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals ?? 6,
    }).format(value)
  }
  if (format === 'percent' && !source.valueSuffix) body += '%'
  return `${source.valuePrefix || ''}${body}${source.valueSuffix || ''}`
}

export function buildChartOption(spec: ChartSpec, theme: ChartTheme = DEFAULT_CHART_THEME): Record<string, unknown> {
  const base = {
    animation: !theme.reducedMotion,
    animationDuration: theme.reducedMotion ? 0 : 320,
    animationDurationUpdate: theme.reducedMotion ? 0 : 180,
    animationEasing: 'cubicOut',
    color: theme.palette,
    aria: { enabled: true, decal: { show: false } },
    textStyle: { color: theme.text, fontFamily: 'PingFang SC, Microsoft YaHei, system-ui, sans-serif' },
  }
  if (spec.chartType === 'pie') return { ...base, ...buildPieOption(spec, theme) }
  if (spec.chartType === 'radar') return { ...base, ...buildRadarOption(spec, theme) }
  if (spec.chartType === 'scatter') return { ...base, ...buildScatterOption(spec, theme) }
  return { ...base, ...buildCartesianOption(spec, theme) }
}

function buildCartesianOption(spec: ChartSpec, theme: ChartTheme) {
  const horizontal = spec.chartType === 'bar' && spec.orientation === 'horizontal'
  const categories = spec.data.map((row) => row[spec.xKey!])
  const valueFormatter = spec.series![0] || {}
  const categoryAxis = {
    type: 'category',
    data: categories,
    name: spec.xAxisLabel || '',
    nameLocation: 'middle',
    nameGap: horizontal ? 70 : 34,
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: theme.muted, fontSize: 13, margin: 14, hideOverlap: true },
    splitLine: { show: false },
  }
  const valueAxis = {
    type: 'value',
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: theme.muted, fontSize: 13, formatter: (value: number) => formatChartValue(value, valueFormatter) },
    splitLine: { show: true, lineStyle: { color: theme.grid, type: 'dashed', width: 1 } },
  }
  const series = spec.series!.map((item, index) => ({
    name: item.label || item.dataKey,
    type: spec.chartType,
    data: spec.data.map((row) => row[item.dataKey]),
    ...(spec.chartType === 'bar' ? {
      barMaxWidth: horizontal ? 28 : 64,
      itemStyle: { color: theme.palette[index % theme.palette.length], borderRadius: horizontal ? [0, 7, 7, 0] : [7, 7, 0, 0], opacity: 0.72 },
      emphasis: { itemStyle: { opacity: 1 } },
    } : {
      smooth: false,
      showSymbol: false,
      symbolSize: 8,
      lineStyle: { width: 2.5 },
      emphasis: { focus: 'series', scale: true },
    }),
  }))
  return {
    grid: { top: 26, right: 24, bottom: horizontal ? 48 : 34, left: horizontal ? 96 : 28, containLabel: true },
    legend: spec.series!.length > 1 ? legend(theme) : undefined,
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.surface,
      borderColor: theme.grid,
      borderWidth: 1,
      padding: [12, 14],
      extraCssText: tooltipCss(),
      axisPointer: { type: spec.chartType === 'bar' ? 'shadow' : 'line', lineStyle: { color: theme.grid } },
      formatter: (params: any[]) => formatAxisTooltip(params, spec),
    },
    xAxis: horizontal ? valueAxis : categoryAxis,
    yAxis: horizontal ? categoryAxis : valueAxis,
    series,
  }
}

function buildScatterOption(spec: ChartSpec, theme: ChartTheme) {
  const series = spec.series!.map((item, index) => ({
    name: item.label || item.dataKey,
    type: 'scatter',
    symbolSize: 11,
    data: spec.data.map((row) => [row[spec.xKey!], row[item.dataKey], spec.labelKey ? row[spec.labelKey] : '']),
    itemStyle: { color: theme.palette[index % theme.palette.length], opacity: 0.9 },
    emphasis: { scale: 1.45, itemStyle: { opacity: 1 } },
  }))
  return {
    grid: { top: 24, right: 24, bottom: 38, left: 30, containLabel: true },
    legend: spec.series!.length > 1 ? legend(theme) : undefined,
    xAxis: valueAxis(theme, spec.xAxisLabel || ''),
    yAxis: { ...valueAxis(theme, spec.series![0]?.axisLabel || ''), axisLabel: { color: theme.muted, fontSize: 13, formatter: (value: number) => formatChartValue(value, spec.series![0]) } },
    tooltip: {
      trigger: 'item', backgroundColor: theme.surface, borderColor: theme.grid, borderWidth: 1,
      padding: [12, 14], extraCssText: tooltipCss(),
      formatter: (param: any) => formatScatterTooltip(param, spec),
    },
    series,
  }
}

function buildPieOption(spec: ChartSpec, theme: ChartTheme) {
  const format = { valueFormat: spec.valueFormat, valuePrefix: spec.valuePrefix, valueSuffix: spec.valueSuffix, decimals: spec.decimals }
  return {
    legend: { ...legend(theme), bottom: 0 },
    tooltip: {
      trigger: 'item', backgroundColor: theme.surface, borderColor: theme.grid, borderWidth: 1,
      padding: [12, 14], extraCssText: tooltipCss(),
      formatter: (param: any) => `<strong>${escapeHtml(param.name)}</strong><br>${dot(param.color)}${escapeHtml(formatChartValue(param.value, format))} <span style="color:${theme.muted}">${escapeHtml(String(param.percent))}%</span>`,
    },
    series: [{
      name: spec.meta.title,
      type: 'pie',
      radius: ['48%', '70%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      label: { show: false },
      itemStyle: { borderColor: theme.surface, borderWidth: 3, borderRadius: 3 },
      emphasis: { scale: true, scaleSize: 5 },
      data: spec.data.map((row) => ({ name: row[spec.nameKey!], value: row[spec.valueKey!] })),
    }],
  }
}

function buildRadarOption(spec: ChartSpec, theme: ChartTheme) {
  const indicators = spec.data.map((row) => ({
    name: String(row[spec.nameKey!]),
    max: spec.maxKey ? Number(row[spec.maxKey]) : niceRadarMax(Math.max(...spec.series!.map((item) => Number(row[item.dataKey])))),
  }))
  return {
    legend: spec.series!.length > 1 ? { ...legend(theme), bottom: 0 } : undefined,
    tooltip: { trigger: 'item', backgroundColor: theme.surface, borderColor: theme.grid, borderWidth: 1, padding: [12, 14], extraCssText: tooltipCss() },
    radar: {
      center: ['50%', '48%'], radius: '66%', indicator: indicators,
      axisName: { color: theme.muted, fontSize: 13 },
      splitNumber: 4,
      axisLine: { lineStyle: { color: theme.grid } },
      splitLine: { lineStyle: { color: theme.grid } },
      splitArea: { areaStyle: { color: ['transparent', 'rgba(76,145,247,0.025)'] } },
    },
    series: [{
      type: 'radar', symbolSize: 5,
      data: spec.series!.map((item, index) => ({
        name: item.label || item.dataKey,
        value: spec.data.map((row) => row[item.dataKey]),
        lineStyle: { width: 2.2, color: theme.palette[index % theme.palette.length] },
        itemStyle: { color: theme.palette[index % theme.palette.length] },
        areaStyle: { color: theme.palette[index % theme.palette.length], opacity: 0.12 },
      })),
    }],
  }
}

function valueAxis(theme: ChartTheme, name: string) {
  return {
    type: 'value', name, nameLocation: 'middle', nameGap: 48,
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { color: theme.muted, fontSize: 13 },
    splitLine: { show: true, lineStyle: { color: theme.grid, type: 'dashed' } },
  }
}

function legend(theme: ChartTheme) {
  return { bottom: 0, left: 'center', icon: 'circle', itemWidth: 10, itemHeight: 10, itemGap: 28, textStyle: { color: theme.text, fontSize: 13 } }
}

function formatAxisTooltip(params: any[], spec: ChartSpec): string {
  const items = Array.isArray(params) ? params : [params]
  const title = escapeHtml(String(items[0]?.axisValueLabel ?? items[0]?.name ?? ''))
  const rows = items.map((param) => {
    const item = spec.series?.[param.seriesIndex] || spec.series?.find((series) => (series.label || series.dataKey) === param.seriesName) || {}
    const value = Array.isArray(param.value) ? param.value[1] : param.value
    return `${dot(param.color)}<span>${escapeHtml(String(param.seriesName || '数值'))}</span><strong style="margin-left:18px">${escapeHtml(formatChartValue(value, item))}</strong>`
  })
  return `<strong>${title}</strong><div style="display:grid;gap:6px;margin-top:8px">${rows.join('')}</div>`
}

function formatScatterTooltip(param: any, spec: ChartSpec): string {
  const item = spec.series?.[param.seriesIndex] || {}
  const values = Array.isArray(param.value) ? param.value : []
  const label = values[2] || item.label || item.dataKey || '数据点'
  return `<strong>${escapeHtml(String(label))}</strong><div style="display:grid;gap:6px;margin-top:8px"><span>${escapeHtml(spec.xAxisLabel || spec.xKey || 'X')}<strong style="margin-left:18px">${escapeHtml(String(values[0] ?? ''))}</strong></span><span>${dot(param.color)}${escapeHtml(item.label || item.dataKey || '数值')}<strong style="margin-left:18px">${escapeHtml(formatChartValue(values[1], item))}</strong></span></div>`
}

function dot(color: unknown): string {
  return `<span style="display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;background:${safeColor(color)}"></span>`
}

function safeColor(value: unknown): string {
  const color = String(value || '')
  return /^#[0-9a-f]{3,8}$/i.test(color) || /^rgba?\([\d\s,.%]+\)$/i.test(color) ? color : '#4C91F7'
}

function tooltipCss(): string {
  return 'border-radius:12px;box-shadow:0 10px 28px rgba(15,23,42,.14);font:13px/1.5 PingFang SC,Microsoft YaHei,system-ui,sans-serif;color:#111827'
}

function niceRadarMax(value: number): number {
  const padded = Math.max(1, value * 1.2)
  const magnitude = 10 ** Math.floor(Math.log10(padded))
  return Math.ceil(padded / magnitude) * magnitude
}

export function chartSpecToCsv(spec: ChartSpec): string {
  const keys = Array.from(new Set(spec.data.flatMap((row) => Object.keys(row))))
  const rows = [keys, ...spec.data.map((row) => keys.map((key) => row[key] ?? ''))]
  return `\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`
}

function csvCell(value: unknown): string {
  const text = String(value ?? '')
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function suggestedChartHeight(spec: ChartSpec): number {
  if (spec.chartType === 'bar' && spec.orientation === 'horizontal') return Math.max(320, spec.data.length * 54 + 80)
  if (spec.chartType === 'pie' || spec.chartType === 'radar') return 390
  return 360
}

export function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}