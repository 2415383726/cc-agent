---
name: visualize
description: Authoring contract for interactive HTML visualization cards. Load before the first `visualize` call; teaches the zero-network inline fragment rules, the card CSS vocabulary and the per-mode sizing.
user-invocable: true
---

# Visualize card authoring

Call `visualize` to show the user an interactive card inside the conversation
(a sandboxed iframe; it cannot reach the host page or any server). This skill
defines what a valid fragment looks like in this deployment.

## The one rule that shapes everything

**This deployment is intranet-only: the card has zero network access.** Every
style, script, font and image must be inline in the fragment. The tool rejects
fragments that reference `https://` (or protocol-relative `//`) resources, use
`url(https://…)`, or call `fetch`/`XMLHttpRequest`/`WebSocket`/
`EventSource`/`sendBeacon`. There is no Chart.js, no ECharts, no CDN — write
vanilla SVG, `<canvas>` 2D, or DOM/CSS. `data:` URIs and inline `<script>` /
`<style>` blocks are the only supported resource shapes.

## Lint codes

Rejections name a stable code — read it, fix that rule, call again:

| Code | Rule |
| --- | --- |
| `[VZ002]` | fragment over the size limit |
| `[VZ003]` | document-skeleton tag (`<!doctype>`/`<html>`/`<head>`/`<body>`) |
| `[VZ004]` | **string-escaped markup** — literal `\"` or `\n` where real quotes and line breaks belong. The most common failure: send the markup itself, never a JSON-escaped rendition of it |
| `[VZ005]` | external resource (`https://`, `//`, remote `@import`) |
| `[VZ007]` | network API (`fetch`/XHR/WebSocket/`EventSource`/`sendBeacon`) |
| `[VZ008]` | form submission (`<form action>`, `method="post"`, `formaction`) — a bare `<form>` used as layout is fine, but never rely on submission |
| `[VZ009]` | the fragment declares `color-scheme` — delete it; the card document already carries the host scheme |
| `[VZ010]` | `document.currentScript` — give the root a unique `id` and use `document.getElementById(...)` |

Warnings (the card still renders, fix if it matters): `[VZ106]` relative
resource URLs (cannot resolve in the sandbox — inline instead), `[VZ108]`
browser storage (`localStorage`/`sessionStorage`/`indexedDB`/
`document.cookie` **throw** inside the sandboxed card and stop your script —
keep state in the fragment's own variables), `[VZ101]` hard-coded colours
(ignores the host theme — use the tokens below; canvas code should resolve a
token through a probe element).

## Fragment contract

- One or more top-level elements (a wrapper `<div>` is fine). **Never** emit
  `<!doctype>`, `<html>`, `<head>`, `<body>` — the card supplies the document,
  stylesheet and theme; emitting a skeleton is a hard error.
- Keep the fragment self-contained and under the size limit the error message
  reports (~40k chars). Prefer one focused visualization per card; split a
  dashboard into several cards instead of one giant fragment.
- Scripts run once when the settled card loads. Use plain JavaScript; guard
  against double execution by rendering into your own wrapper element.

## Surfaces (`mode`)

- `inline` (default): fits the chat column, height capped at 800px (the card
  scrolls internally past the cap). Right choice for charts, single panels and
  simulators.
- `wide`: extends to the composer-card width for side-by-side compact panels;
  height capped at 1200px. Use sparingly — it overlays the page margins.

## Theme and CSS vocabulary

The frame injects theme tokens as CSS custom properties — always style against
them so the card matches the host palette:

| Token | Meaning |
| --- | --- |
| `var(--foreground)` / `var(--muted-foreground)` | primary / secondary ink |
| `var(--card)` / `var(--card-foreground)` / `var(--border)` | panel surface, ink, hairline |
| `var(--primary)` / `var(--primary-foreground)` | brand blue and its contrast ink |
| `var(--viz-series-1)` … `--viz-series-6` | categorical series colors (charts) |
| `var(--viz-grid)` / `var(--viz-axis)` / `var(--viz-context)` | chart furniture |
| `var(--radius)` / `var(--font-size-base)` / `var(--font-size-small)` | shape and type scale |
| `var(--font-sans)` / `var(--font-mono)` | font stacks |

Prebuilt classes you should reuse instead of reinventing: `.card` (surface
box), `.btn` / `.btn-primary` / `.btn-ghost` (buttons, with
`aria-pressed`/`aria-selected` pressed styling), `.viz-grid` (responsive tile
grid), `.viz-row` / `.viz-controls` (layout rows), `.viz-stat` +
`.viz-stat-value` (KPI tiles), `.viz-badge`, `.text-small`, `.form-label` /
`.form-control` / `.form-select` / `.form-check` (inputs), and plain `table`
styling (border-collapse rows with muted headers).

Do not declare your own `color-scheme` or redefine the tokens above; bridge
values arrive on `:root` from the host.

## Interaction patterns that work well

- A controls row (`.viz-controls`) of sliders/selects feeding a re-render
  function; recompute synchronously on `input` events.
- An SVG or `<canvas>` chart bound to state; rebuild paths/rects from data
  arrays instead of mutating strings.
- KPI tiles (`.viz-grid` of `.viz-stat`) above the chart for summary numbers.
- Buttons toggle state with `aria-pressed` so the pressed style applies for
  free.

## Anti-patterns (rejected or broken)

- Any `<script src>` / `<link href>` / `<img src="http…">` — hard error.
- Charting libraries — there is no network; hand-roll the 3–4 primitives you
  need (bars, lines, points, axes).
- `setInterval` polling or timers expecting later data — the card is static
  data + interaction only.
- Emitting a full HTML document — hard error (`[VZ003]`).
- A JSON-escaped fragment (literal `\"` / `\n` in place of real quotes and
  newlines) — hard error (`[VZ004]`).
- `localStorage`/`sessionStorage`/`indexedDB`/`document.cookie` — they throw
  inside the sandboxed card and stop your script (`[VZ108]`).
- Forms relying on submission — `<form>` posts are blocked by CSP; use button
  handlers (`[VZ008]`).

## After the call

The tool returns a one-line confirmation; the user sees the card immediately.
Do not paste the fragment back into your reply — describe what the card shows
in one or two sentences and let the card do the talking. If validation fails,
read the error: it names a stable code (`[VZ004]`, `[VZ005]`, …) plus the fix;
repair the fragment and call again. Cards are immutable once rendered —
re-call `visualize` with a corrected full fragment rather than trying to
patch.
