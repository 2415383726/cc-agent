# Pi visualization author contract — kit 1.0.0

Content protocol `1`, kit major `1`. This is the capability reference for ticket
03's built-in skill. It describes the implemented static workbench, not an
OpenAI/ZCode bridge. Runtime assets stay in the workbench; model-readable skill
resources may copy these instructions and the small examples, never vendor JS.

## Delivery and available resources

Return one closed `pi-visualize` Markdown fence containing one HTML root:

````text
```pi-visualize
<section data-pi-visualize="1" data-kit-version="1"
  data-title="A short title" data-description="A useful text alternative"
  data-libraries="d3 lucide">
  <!-- Artwork markup, optional small local styles and classic inline scripts. -->
</section>
```
````

The only library IDs are `d3` and `lucide`, case-sensitive. Space or comma
separation is accepted. Omit `data-libraries` for native HTML/CSS/JS/SVG/canvas.
The host injects styles, declared libraries and `PiViz` before author scripts,
then initializes tabs, tooltips and icons at DOMContentLoaded. Never add script
or stylesheet URLs, module imports, a document shell, a base or CSP element.
Unknown protocol/kit/library versions fail with readable text. Dependencies
are not inferred from JS names and do not fall back to a CDN.

| Capability | Actual version/global | Use |
| --- | --- | --- |
| Shared CSS and controls | kit 1.0.0 / `PiViz` | Always supplied |
| Native graphics | browser SVG/canvas | No library declaration |
| D3 | 7.9.0 / `d3` | Declare `d3`; selection, scales, axes, shapes, etc. |
| Lucide | 1.17.0 / `lucide` | Declare `lucide`; decorative icons initialized by host |

D3's networking functions do not gain network access. Data must be self-contained.
There is no Floating UI dependency, calendar, Tweak, map, dynamic package loader,
variant carousel, file API, persistence, follow-up, model or tool API.

Each author fragment is limited to 64 KiB UTF-8. Each answer permits two works,
128 KiB total; shared assets do not count. Titles permit 120 Unicode characters
and descriptions 500. Do not fill a budget unnecessarily. Invalid/over-limit
fragments are rejected whole. A partial streamed fence never runs.

## Shared styles

Use native labelled elements. Layout classes do not add semantics or business
logic. Slider/select/toggle/button state and graph changes belong to author JS.

| Class | Contract |
| --- | --- |
| `.viz-row` | Wrapping flex row, centred items and 12px gaps |
| `.viz-grid` | Responsive equal columns, minimum 220px or available width |
| `.viz-controls` | Wrapping form group; labelled fields flex from 170px |
| `.card` | Optional bordered surface; charts do not require a card |
| `.viz-stat` | Tabular numeric summary |
| `.btn`, `.btn-primary`, `.btn-ghost` | Button styles; native `disabled` supported |
| `.form-label` | Label text, normally `label[for]` or inside a wrapping label |
| `.form-control`, `.form-select`, `.form-range` | Native text/select/range controls |
| `.form-check`, `.form-switch` | Label wrapping a native checkbox; switch may use `role="switch"` |
| `.table`, `.table-responsive`, `.numeric` | Table styles, overflow wrapper and numeric cell alignment |
| `.viz-muted` / `.text-muted`, `.viz-small`, `.viz-error` | Secondary text, 12px text, error text |
| `.sr-only` / `.visually-hidden` | Visually hidden text that remains accessible |

Buttons, fields, switches, ranges and tabs have 44px minimum heights. Visible
focus, selection, caret and native accent colors use theme tokens. Give every
control a meaningful label, expose units and current values, and explain charts
in visible text as well as accessible names. Keep labels outside small scaled
SVG viewBoxes when they would become unreadable at 320px. Tables may scroll
within their labelled, keyboard-focusable wrapper.

## Themes, graphics and motion

The workbench's light/dark switch updates the existing frame. There is no frame
rebuild or parameter reset. CSS/SVG can use these public custom properties:

| Tokens | Meaning |
| --- | --- |
| `--viz-bg`, `--viz-text` | Background and foreground |
| `--viz-surface`, `--viz-raised` | Card/input-adjacent surface and tooltip/hover surface |
| `--viz-primary`, `--viz-on-primary` | Primary action background and its foreground |
| `--viz-muted`, `--viz-border`, `--viz-input` | Secondary text, visible control border and field background |
| `--viz-focus`, `--viz-danger` | Focus ring and errors |
| `--viz-series-1` … `--viz-series-6` | Six stable series identities with light/dark colors |
| `--viz-font`, `--viz-font-size`, `--viz-font-sm`, `--viz-font-lg` | System font stack, 14px body, 12px small, 18px heading |

Default six-series order is purple, blue, green, amber, pink, mauve. Do not rely
only on color to identify data. Use direct labels, legends, shape or line style.

`PiViz.version` is `"1.0.0"`. `PiViz.getTheme()` returns a frozen object:

```js
{
  mode: 'light' /* or 'dark' */,
  colors: {
    background, text, surface, raised, muted, border, primary, onPrimary,
    input, focus, danger, series1, series2, series3, series4, series5, series6
  }
}
```

Color values are resolved CSS colors usable directly by canvas. Initial colors
are installed before author scripts. When host colors change, the window emits
`piviz:themechange`; `event.detail` contains the current theme object. D3 colors
stored in attributes and canvas pixels should be redrawn:

```js
function draw() {
  const { colors } = PiViz.getTheme();
  const canvas = document.getElementById('diagram');
  const context = canvas.getContext('2d');
  context.fillStyle = colors.background;
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = colors.series1;
  context.fillRect(10, 10, 80, 20);
}
addEventListener('piviz:themechange', draw);
draw();
```

Use `PiViz.reducedMotion` to read the live boolean preference. CSS reduces CSS
animations/transitions; it cannot pause author JS timers. Start an animation
paused under reduced motion, offer play/pause/reset, and handle preference
changes with native `matchMedia('(prefers-reduced-motion: reduce)')`. Plain
parameter changes should update immediately without animation. Resize SVG and
canvas to available width; use devicePixelRatio when drawing sharp canvas text.

## Tabs

The host initializes this markup automatically. Each group needs a labelled
tablist, native buttons, local unique panel IDs, and `aria-controls`:

```html
<div data-viz-tabs>
  <div role="tablist" aria-label="Result views">
    <button role="tab" aria-controls="figure-panel" aria-selected="true">Figure</button>
    <button role="tab" aria-controls="data-panel">Data</button>
  </div>
  <section id="figure-panel" role="tabpanel">…</section>
  <section id="data-panel" role="tabpanel" hidden>…</section>
</div>
```

One enabled tab has `aria-selected=true` and tabindex 0. Click and arrow keys
activate it and reveal only its panel. Left/Right wrap; Home/End choose first/
last enabled tabs. A vertical tablist uses Up/Down. Disabled tabs are skipped.
Panels receive `aria-labelledby`; missing tab IDs are assigned locally. The
first enabled tab is selected unless an enabled tab is initially selected.
Invalid panel associations cause readable artwork failure.

## Tooltips and icons

Use a native focusable trigger with an accessible name. Tooltip content is only
supplementary; keep required formulas, labels and explanations in visible text.

```html
<button class="btn btn-ghost" type="button"
  data-viz-tooltip="Rates are per minute.">Rate details</button>
```

Focus/hover shows the tooltip, Escape/blur/scroll hides it, touch toggles it and
an outside touch dismisses it. Position is kept inside the viewport. Text is
limited to 500 characters, never HTML. `aria-describedby` preserves existing IDs
and adds the generated tooltip ID. Tooltips are not interactive popovers.

With `data-libraries="lucide"`, use an actual Lucide 1.17.0 kebab-case name:

```html
<button class="btn" type="button"><i data-lucide="play" aria-hidden="true"></i>Play</button>
```

The host supplies `lucide` and converts icons after content is ready. Icons are
decorative (`aria-hidden=true`, `focusable=false`); buttons still need text or an
accessible name. After inserting new icons, call `PiViz.initIcons(container)`.
For newly inserted tabs/tooltips/icons together, call `PiViz.init(container)`;
both methods scan descendants, default to `document`, and repeated initialization
does not duplicate the kit's tab/tooltip handlers. They do not wire business
actions. Native `lucide.createIcons()` is also the pinned library API.

## Complete examples and deployment

- [Native SVG + range](examples/visualize-native.html): small fragment, no libraries.
- [D3 + controls + tabs + tooltip + Lucide](examples/visualize-controls.html): small complete fragment for skill references.
- [Full queue fixture](fixtures/kit-visualize.html): native SVG, D3, canvas, all controls and 360 meaningful synthetic samples; available at `/?replay=visualize-kit`.

Example files are fragments: wrap their exact contents in a closed
`pi-visualize` fence when answering. They do not require local file creation by
the model. The host must remain a supported static deployment; see
[deployment policy](docs-visualize.md). The parent checks the exact shell HTTP
policy, fetches only fixed local assets using SHA-256 Fetch integrity plus byte
lengths, then inlines them into the isolated child before author scripts.
Missing/corrupted resources fail without a CDN retry. Even library network
helpers cannot access the network from the child.

Release metadata is in `src/visualize/manifest.json` and published unchanged as
`dist/visualize/manifest.json`. It records kit/protocol versions, IDs, actual
versions, paths, source provenance, script/license hashes and byte counts.
`dist/visualize/NOTICE.txt` and adjacent vendor licenses must ship too. Run
`npm run manifest:visualize` after editing project-owned kit JS/CSS, then build
and static checks; this command never rewrites the pinned vendor checksums.

No API sends messages to the Agent, reads parent DOM/storage/credentials, calls
tools or persists parameters. Expand/collapse preserves the instance; refresh
or a later open starts from author initial values. A saved valid answer without
trusted Pi completion logs requires explicit “查看作品” and keeps unknown status.
Do not claim browser tests ran when generating a fragment; the author can only
check its markup, local logic, labels, initial state and declared resources.
