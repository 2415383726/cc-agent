---
name: answers-charts
description: Create clear analytical charts from supplied structured data using the cc-chart v1 protocol. Use for trends, category comparisons, rankings, part-to-whole composition, correlations, or multidimensional profiles that benefit from bar, line, pie, scatter, or radar visualization.
---

# Answers Charts

Turn supplied data into a concise analytical chart that the CC Agent frontend can render consistently.

## Workflow

1. Confirm that a chart improves the answer. Use prose or a table when data is sparse, mostly textual, or exact lookup matters more than visual pattern.
2. Preserve the user's data. Never invent observations, categories, units, totals, targets, or time periods.
3. Choose one chart type:
   - Use `line` for ordered trends, especially time series.
   - Use `bar` for category comparison; use `orientation: "horizontal"` for rankings or long labels.
   - Use `pie` only for a meaningful part-to-whole breakdown with 2–12 non-negative slices.
   - Use `scatter` for the relationship between two numeric measures.
   - Use `radar` for 3–10 comparable dimensions across no more than four entities.
4. Aggregate and sort before charting. Keep bar/line data at 100 rows or fewer, scatter data at 500 points or fewer, and series counts within the protocol limits.
5. Write an insight-led `meta.title`, a short factual `meta.description`, and a `meta.footer` when units, source, scope, or sample-data status need disclosure.
6. Compose valid cc-chart JSON. Check field mappings against the schema and examples below before outputting.
7. Output a fenced `cc-chart` JSON block. Do not output ECharts options, Recharts props, JavaScript functions, colors, layout pixels, or renderer-specific styling.

## Output rules

- Set `version` to `1`.
- Use only fields defined by the protocol; unknown fields make the chart invalid.
- Keep every row value a string or finite number.
- Map every referenced key to a field present in every data row.
- Put numeric formatting on the relevant series, or at the top level for pie values.
- Use `valueFormat: "percent"` for values already expressed as percentage points, such as `35` meaning `35%`.
- Do not wrap `cc-chart` in `cc-ui`, `charts_widget_v2`, HTML, or another component envelope.
- Explanatory prose may appear before or after the block, but the fenced body must contain JSON only.

## Envelope

Output exactly this fenced language identifier:

````text
```cc-chart
{ "version": 1, "chartType": "bar", "meta": { "title": "..." }, "data": [] }
```
````

The frontend owns colors, axes, tooltip, legend, spacing, responsiveness, accessibility, and exports.

## Schema

```ts
type ValueFormat = "compact" | "integer" | "raw" | "percent"

type SeriesSpec = {
  dataKey: string
  label?: string
  axisLabel?: string
  valueFormat?: ValueFormat
  valuePrefix?: string
  valueSuffix?: string
  decimals?: number // integer from 0 through 6
}

type ChartSpec = {
  version: 1
  chartType: "bar" | "line" | "pie" | "scatter" | "radar"
  meta: { title: string; description?: string; footer?: string }
  data: Array<Record<string, string | number>>
  xKey?: string
  xAxisLabel?: string
  series?: SeriesSpec[]
  orientation?: "vertical" | "horizontal"
  labelKey?: string
  nameKey?: string
  valueKey?: string
  valueFormat?: ValueFormat
  valuePrefix?: string
  valueSuffix?: string
  decimals?: number
  maxKey?: string
}
```

### Field reference

| Field | Required for | Type | Notes |
|---|---|---|---|
| `version` | all | `1` | Must be exactly `1`. |
| `chartType` | all | enum | `bar`, `line`, `pie`, `scatter`, `radar`. |
| `meta.title` | all | string | Insight-led title. |
| `meta.description` | all | string | Short factual context. |
| `meta.footer` | no | string | Units, source, scope, or sample-data note. |
| `data` | all | array | `Array<Record<string, string \| number>>` |
| `xKey` | bar, line, scatter | string | Column mapped to x-axis. |
| `xAxisLabel` | no | string | X-axis label text. |
| `series` | bar, line, scatter, radar | array | 1–6 for bar/line, 1–4 for scatter/radar. |
| `orientation` | no | `"vertical"` \| `"horizontal"` | Bar only; default vertical. |
| `labelKey` | no | string | Column for point labels (scatter). |
| `nameKey` | pie, radar | string | Column for slice or dimension names. |
| `valueKey` | pie | string | Column for slice values. |
| `maxKey` | no | string | Column for radar domain maxima. |
| `valueFormat` | no | `"compact"` \| `"integer"` \| `"raw"` \| `"percent"` | Top-level or per-series. |
| `valuePrefix` | no | string | e.g. `"¥"`, `"$"`. |
| `valueSuffix` | no | string | e.g. `" 万"`, `"%"`. |
| `decimals` | no | number | Integer 0–6. |
| `series[].dataKey` | — | string | Column mapped to this series. |
| `series[].label` | — | string | Legend or axis label. |
| `series[].axisLabel` | — | string | Axis label override. |
| `series[].valueFormat` | — | string | Per-series format override. |
| `series[].valuePrefix` | — | string | Per-series prefix. |
| `series[].valueSuffix` | — | string | Per-series suffix. |
| `series[].decimals` | — | number | Per-series decimal override. |

## Examples

### Bar

Use vertical bars for ordinary comparison and horizontal bars for rankings or long labels. Supply `xKey`, 1–6 series, and 1–100 rows.

```json
{
  "version": 1,
  "chartType": "bar",
  "meta": {
    "title": "企业版贡献最高，领先第二名 35%",
    "description": "2026 年第二季度各产品线确认收入，按收入从高到低排列。",
    "footer": "单位：万元｜示例数据"
  },
  "orientation": "horizontal",
  "xKey": "product",
  "series": [{ "dataKey": "revenue", "label": "收入", "valuePrefix": "¥", "valueSuffix": " 万" }],
  "data": [
    { "product": "企业版", "revenue": 648 },
    { "product": "专业版", "revenue": 480 },
    { "product": "团队版", "revenue": 356 }
  ]
}
```

### Line

Use for ordered trends. Supply `xKey`, 1–6 series, and 1–100 rows. Keep rows in display order.

```json
{
  "version": 1,
  "chartType": "line",
  "meta": {
    "title": "收入连续四个月高于目标",
    "description": "实际收入自 3 月超过目标后持续扩大领先幅度。",
    "footer": "单位：万元｜示例数据"
  },
  "xKey": "month",
  "xAxisLabel": "月份",
  "series": [
    { "dataKey": "actual", "label": "实际收入", "valuePrefix": "¥", "valueSuffix": " 万" },
    { "dataKey": "target", "label": "经营目标", "valuePrefix": "¥", "valueSuffix": " 万" }
  ],
  "data": [
    { "month": "1 月", "actual": 82, "target": 85 },
    { "month": "2 月", "actual": 91, "target": 92 },
    { "month": "3 月", "actual": 104, "target": 98 }
  ]
}
```

### Pie

Use only for part-to-whole composition. Supply `nameKey`, `valueKey`, and 2–12 non-negative rows. Put value formatting at the top level.

```json
{
  "version": 1,
  "chartType": "pie",
  "meta": {
    "title": "订阅业务贡献近七成收入",
    "description": "第二季度收入结构以企业订阅和团队订阅为主。",
    "footer": "总收入 ¥1,980 万｜示例数据"
  },
  "nameKey": "segment",
  "valueKey": "revenue",
  "valuePrefix": "¥",
  "valueSuffix": " 万",
  "data": [
    { "segment": "企业订阅", "revenue": 820 },
    { "segment": "团队订阅", "revenue": 540 },
    { "segment": "API 调用", "revenue": 300 }
  ]
}
```

### Scatter

Use for correlation between numeric measures. Supply numeric `xKey`, 1–4 numeric series, and up to 500 rows. Use `labelKey` for point names.

```json
{
  "version": 1,
  "chartType": "scatter",
  "meta": {
    "title": "广告投入与新增收入呈明显正相关",
    "description": "多数月份广告投入增加后，新增收入同步增长。",
    "footer": "每个点代表一个月份｜示例数据"
  },
  "xKey": "adSpend",
  "xAxisLabel": "广告投入",
  "labelKey": "month",
  "series": [{ "dataKey": "newRevenue", "label": "新增收入", "axisLabel": "新增收入", "valuePrefix": "¥", "valueSuffix": " 万" }],
  "data": [
    { "month": "1 月", "adSpend": 18, "newRevenue": 76 },
    { "month": "2 月", "adSpend": 22, "newRevenue": 88 },
    { "month": "3 月", "adSpend": 25, "newRevenue": 102 }
  ]
}
```

### Radar

Use for comparable multidimensional profiles. `nameKey` identifies each dimension. Each series `dataKey` identifies an entity. Supply 3–10 rows and 1–4 series. Use `maxKey` when domain maxima are known; otherwise the frontend derives readable maxima.

```json
{
  "version": 1,
  "chartType": "radar",
  "meta": {
    "title": "企业版在能力完整度与稳定性上领先",
    "description": "专业版在易用性方面接近企业版，但扩展能力差距明显。",
    "footer": "评分范围：0–100｜示例数据"
  },
  "nameKey": "metric",
  "maxKey": "max",
  "series": [
    { "dataKey": "enterprise", "label": "企业版" },
    { "dataKey": "professional", "label": "专业版" }
  ],
  "data": [
    { "metric": "能力完整度", "enterprise": 92, "professional": 78, "max": 100 },
    { "metric": "易用性", "enterprise": 82, "professional": 86, "max": 100 },
    { "metric": "稳定性", "enterprise": 95, "professional": 80, "max": 100 }
  ]
}
```

## Invalid patterns

Do not:

- Output `echarts`, Recharts, SVG, HTML, JavaScript callbacks, colors, or pixel dimensions.
- Add unknown fields such as `tooltip`, `grid`, `legend`, `style`, or `theme`.
- Mix strings into numeric series fields.
- Omit a mapped key from any row.
- Use pie for values that do not form a meaningful whole.
- Use radar for unrelated measures or measures with incompatible direction without explaining normalization.
- Claim a trend, ranking, or correlation not supported by the supplied values.
