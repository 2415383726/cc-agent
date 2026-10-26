---
name: answers-ui
description: Choose and produce CC Agent AG-UI business interfaces for structured final answers and user-input interruptions. Use when business information is clearer as cc-record, cc-table, cc-compare, or cc-timeline, or when missing information, choices, approvals, or several related values must be collected through UserPrompt options or fields before continuing.
---

# Answers UI

Choose between plain Markdown, a structured final-answer surface, and an interactive `UserPrompt`. Use UI only when it makes the business task easier to understand or complete.

## Decision workflow

1. Determine whether the next response is an answer or a blocking question.
2. For an answer, use Markdown by default. Use one structured surface only when the data has the matching business shape.
3. For a blocking question, call `UserPrompt`. Do not print a mock form or encode it in a fenced block.
4. Preserve known facts and defaults. Never ask for information already present in the conversation or available through a suitable tool.
5. Keep the interface focused. Do not generate UI merely for decoration.

| Need | Use |
|---|---|
| Conclusion, summary, recommendation, instructions, or short list | Markdown |
| One business object with grouped attributes | `cc-record` |
| Homogeneous rows sharing columns | `cc-table` |
| 2–4 subjects aligned by common criteria | `cc-compare` |
| Real events where chronology matters | `cc-timeline` |
| One simple choice or short answer required before continuing | `UserPrompt.options` / custom input |
| Several related typed values required together | `UserPrompt.fields` |

## Final-answer surfaces

For every surface:

- Set `version` to `1`.
- Use concise business-facing `meta.title`; add `description` or `status` only when useful.
- Use stable, unique IDs within the surface.
- Emit strict JSON with no unknown fields.
- Allow only strings, finite numbers, booleans, or string arrays as values. Do not emit `null`, objects, or nested arrays.
- Keep dates explicit and unambiguous. Preserve protocol order; do not expect the frontend to infer or reorder dates.
- Do not emit HTML, JavaScript, URLs, host functions, API calls, renderer styles, colors, or layout dimensions.
- Never wrap these protocols in the removed `cc-ui` envelope.
- Place explanatory Markdown before or after the fenced block when it adds meaning.

### Record

Use `cc-record` for one person, organization, policy, case, order, project, or other business object. Group related fields into sections.

```ts
type RecordSpec = {
  version: 1
  meta: { title: string; description?: string; status?: string }
  sections: Array<{
    title?: string
    fields: Array<{
      label: string
      value: string | number | boolean | string[]
      format?: "text" | "number" | "date" | "datetime" | "status" | "tags"
    }>
  }>
  actions?: Action[]
}
```

```cc-record
{
  "version": 1,
  "meta": { "title": "项目 A", "status": "进行中" },
  "sections": [
    {
      "title": "基本信息",
      "fields": [
        { "label": "负责人", "value": "张明" },
        { "label": "预算（万元）", "value": 360, "format": "number" },
        { "label": "计划完成日期", "value": "2026-09-30", "format": "date" }
      ]
    }
  ]
}
```

### Table

Use `cc-table` for a homogeneous collection. Every row must have a stable `id`; every column key must map to the same key in `rows[].values`.

```ts
type TableSpec = {
  version: 1
  meta: { title: string; description?: string; status?: string }
  columns: Array<{
    key: string
    label: string
    format?: "text" | "number" | "date" | "datetime" | "status" | "tags"
    align?: "start" | "center" | "end"
    sortable?: boolean
  }>
  rows: Array<{
    id: string
    values: Record<string, string | number | boolean | string[]>
  }>
  emptyText?: string
  actions?: Action[]
}
```

Keep row order meaningful. Mark `sortable` only for columns users are likely to inspect in different orders. Do not add pagination or model-generated links.

### Compare

Use `cc-compare` for 2–4 subjects evaluated against the same criteria. Key every criterion value by subject ID. Highlight only a factually outstanding subject for that criterion; do not force one overall winner.

```ts
type CompareSpec = {
  version: 1
  meta: { title: string; description?: string; status?: string }
  subjects: Array<{ id: string; label: string; description?: string }>
  criteria: Array<{
    id: string
    label: string
    values: Record<string, string | number | boolean | string[]>
    highlight?: string
    note?: string
  }>
  actions?: Action[]
}
```

### Timeline

Use `cc-timeline` for employment history, approvals, case handling, policy evolution, project milestones, or other real chronological events. Emit items in the exact display order. Do not use it for plans, instructions, or agent execution steps.

```ts
type TimelineSpec = {
  version: 1
  meta: { title: string; description?: string; status?: string }
  items: Array<{
    id: string
    time: string
    title: string
    description?: string
    status?: string
  }>
  actions?: Action[]
}
```

### Context actions

Add actions only when a follow-up is meaningful in the context of the result.

```ts
type Action = {
  id: string
  label: string
  prompt: string
  variant?: "primary" | "secondary"
}
```

- Write a self-contained prompt that remains understandable in history.
- Treat the click as the user's next message, not as a direct business operation.
- Do not use actions as navigation links or a generic button collection.
- Require the normal tool permission or approval flow for business writes.

## UserPrompt interrupts

Call the `UserPrompt` tool only when the answer must come from the user before safe progress is possible.

### Choose the interaction

- Use `options` for one concise decision. Set `multiSelect: true` only when several top-level options may be selected.
- Set `allowCustomInput: true` only when a valid answer may fall outside the supplied options or an explanation is useful.
- Use `fields` when 2–8 related values are needed together, when values require types or validation, or when a compact business form prevents repeated questioning.
- Split a longer form into multiple interruptions grouped by decision stage. Do not ask future-stage questions before earlier answers determine whether they are relevant.
- Prefer a reasonable stated assumption when the impact of being wrong is low.

### Field rules

- Give every field a unique, stable `name`, preferably `snake_case`.
- Use `group` for meaningful business sections, not decorative grouping.
- Use `width: "half"` only for naturally paired short fields; otherwise use `full`.
- Use `description` when the label alone does not explain scope, format, or consequence.
- Supply a known value as `defaultValue`; never fabricate a default merely to fill the form.
- Mark only truly necessary values as `required`.
- Use `radio` for 2–5 important choices whose descriptions should remain visible.
- Use `select` for compact single choice and `multiselect` for multiple choice.
- Use `date` for one day, `daterange` for a start/end period, and `datetime` only when time-of-day matters.
- Use `number` for quantities, amounts, rates, and ranges. Add `min`, `max`, `step`, `prefix`, or `suffix` only when they express real business constraints or units.
- Use `textarea` for explanations; use `maxLength` when the business rule has a real limit.
- Use `checkbox` for an explicit boolean acknowledgement, not for several independent choices.
- Do not encode URLs, API operations, callbacks, HTML, or styling in fields or options.

Supported field types are `text`, `textarea`, `select`, `multiselect`, `radio`, `date`, `daterange`, `datetime`, `number`, `email`, `tel`, and `checkbox`.

```ts
type UserPromptField = {
  name: string
  label: string
  type: "text" | "textarea" | "select" | "multiselect" | "radio" |
        "date" | "daterange" | "datetime" | "number" | "email" |
        "tel" | "checkbox"
  required?: boolean
  description?: string
  placeholder?: string
  defaultValue?: string | number | boolean | string[]
  options?: Array<string | {
    label: string
    value?: string
    description?: string
    disabled?: boolean
  }>
  group?: string
  width?: "full" | "half"
  min?: number
  max?: number
  step?: number
  maxLength?: number
  prefix?: string
  suffix?: string
}
```

Example tool arguments for collecting a compact request form:

```json
{
  "question": "请补充本次预算调整信息",
  "purpose": "clarification",
  "allowCustomInput": false,
  "fields": [
    {
      "name": "amount",
      "label": "调整金额",
      "type": "number",
      "required": true,
      "group": "调整内容",
      "width": "half",
      "min": 0,
      "step": 1000,
      "suffix": "元"
    },
    {
      "name": "effective_period",
      "label": "生效期间",
      "type": "daterange",
      "required": true,
      "group": "调整内容",
      "width": "half"
    },
    {
      "name": "reason_type",
      "label": "调整原因",
      "type": "radio",
      "required": true,
      "group": "说明",
      "options": [
        { "label": "业务增长", "value": "growth", "description": "现有预算无法覆盖已确认的新增业务" },
        { "label": "成本变化", "value": "cost_change", "description": "采购价格或实施成本发生变化" }
      ]
    },
    {
      "name": "reason_detail",
      "label": "补充说明",
      "type": "textarea",
      "group": "说明",
      "maxLength": 500
    }
  ]
}
```

The frontend resumes the agent with structured `values` and a readable `answer`. Use the returned values normally; do not ask the same fields again.

### Permission boundary

- Use `purpose: "clarification"` for missing facts or preferences.
- Use `purpose: "permission"` or `"approval"` only to request an explicit user decision.
- Treat the response as user intent, not as a way to bypass tool guards.
- Continue to use the normal tool permission or approval mechanism before any protected or business-writing operation.
- Never imply that submitting a form has already changed business data.

## Invalid patterns

Do not:

- Emit removed `cc-ui` kinds such as `summary`, `form`, `table`, `steps`, or `actions`.
- Put forms, permission controls, or approval buttons in final-answer fences.
- Use `cc-table` to imitate a record or a 2–4 subject comparison.
- Duplicate the same dataset as both `cc-chart` and `cc-table` unless exact lookup is also necessary.
- Ask for data available in context or retrievable with an appropriate tool.
- Combine unrelated questions into one large form.
- Present inferred or fabricated data as supplied business facts.
