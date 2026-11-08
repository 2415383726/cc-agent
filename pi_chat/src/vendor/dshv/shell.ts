/**
 * Pure assembly of the sandboxed frame document a visualization renders in.
 * DOM-free so specs exercise it directly; the browser card is the only
 * production caller.
 *
 * Ported from Nagi-ovo/dsh-visualize `src/shell.ts` (BSD-3-Clause), adapted:
 * - FRAME_CSP is zero-network (intranet deployment): inline script/style only,
 *   `connect-src` limited to blob:/data:, no CDN allowlist, no nested frames,
 *   no form posts. The tool-side lint gate rejects external references.
 * - The card style pack, the dshViz helper (state/prompt bridge) and the
 *   streaming shell are out of scope for this port (v1: settled cards only);
 *   the height reporter stays identical.
 *
 * Security model (aligned with Codex's /visualize render pipeline): the card
 * mounts `<iframe sandbox="allow-scripts">` — an opaque origin with no access
 * to the host page — and this document's own CSP meta tag confines what runs
 * inside.
 *
 * @module vendor/dshv/shell
 */

import { FRAME_CSS } from './frame-css.ts'

/** The frame document's Content-Security-Policy (zero-network). `data:` URIs
 * are self-contained inline content — no network fetch — so they stay usable
 * like the upstream frame, minus the CDN allowlist. */
export const FRAME_CSP = [
  "default-src 'none'",
  "script-src 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob: data:",
  "style-src 'unsafe-inline' blob: data:",
  'img-src blob: data:',
  "font-src blob: data:",
  'media-src blob: data:',
  'worker-src blob:',
  'connect-src blob: data:',
  "frame-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ')

/** Wire type of the frame→card height report message. */
export const HEIGHT_MESSAGE_TYPE = 'dsh-viz:height'

/** Inputs to one frame document assembly. */
export interface FrameDocOptions {
  /** The validated fragment body. */
  fragment: string
  /** Document title (escaped here). */
  title: string
  /**
   * Host palette bridged into the frame as `--dsh-viz-*` custom properties on
   * `:root`. Values pass through {@link sanitizeCssValue}; entries that
   * sanitize to empty are dropped so the stylesheet fallbacks apply.
   */
  themeVars: Record<string, string>
  /** Host `color-scheme` so `light-dark()` in the frame follows the host theme. */
  colorScheme: 'light' | 'dark'
  /**
   * Correlation token echoed in every height report, letting a card with
   * several sibling frames attribute messages; the tool callId in production.
   */
  reportToken: string
}

/**
 * Assemble the complete srcdoc document for one visualization frame.
 * @param options - fragment, title, bridged palette, and report token.
 * @returns the HTML document string for the iframe's `srcDoc`.
 */
export function buildFrameDoc(options: FrameDocOptions): string {
  const rootVars = Object.entries(options.themeVars)
    .map(([name, value]) => [name, sanitizeCssValue(value)] as const)
    .filter(([, value]) => value.length > 0)
    .map(([name, value]) => `--dsh-viz-${name}: ${value};`)
    .join(' ')
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="${FRAME_CSP}">
<title>${escapeHtml(options.title)}</title>
<style>${FRAME_CSS}
:root { ${rootVars} color-scheme: ${options.colorScheme}; }
body { padding: 4px 2px; }</style>
</head>
<body>
${options.fragment}
<script>${heightReporter(options.reportToken)}</script>
</body>
</html>
`
}

/**
 * The frame-side height reporter: posts the document's scroll height to the
 * parent on load and on every resize, so the card can size the iframe to its
 * content (a sandboxed frame's document is unreachable from the parent).
 * @param reportToken - correlation token echoed in each message.
 * @returns the inline script body.
 */
function heightReporter(reportToken: string): string {
  const token = JSON.stringify(reportToken)
  return `
(function () {
  var post = function () {
    parent.postMessage({
      type: ${JSON.stringify(HEIGHT_MESSAGE_TYPE)},
      token: ${token},
      height: document.documentElement.scrollHeight,
    }, '*');
  };
  new ResizeObserver(post).observe(document.documentElement);
  addEventListener('load', post);
  post();
})();
`
}

/**
 * Keep one bridged palette value inert inside a style block: resolved
 * computed-style colors never contain declaration or block delimiters, so any
 * occurrence marks a malformed value, dropped rather than repaired.
 * @param value - the raw computed-style value.
 * @returns the trimmed value, or empty when it must be dropped.
 */
export function sanitizeCssValue(value: string): string {
  const trimmed = value.trim()
  return /[;{}<>]/u.test(trimmed) ? '' : trimmed
}

/**
 * Minimal HTML text escape for the frame `<title>`.
 * @param text - raw text.
 * @returns the escaped text.
 */
function escapeHtml(text: string): string {
  return text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
}
