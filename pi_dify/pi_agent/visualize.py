"""The `visualize` internal cognitive tool: model-authored inline HTML cards.

The model passes one inline-HTML fragment as a direct argument (no document
skeleton — the rendering card supplies the document, stylesheet, and theme).
The tool validates the fragment against the zero-network inline contract and
returns a one-line confirmation for the model while projecting the fragment
into the tool result details, from which the display observer emits a `visual`
field on `tool.end` so the workbench renders a sandboxed card. The model never
re-reads the fragment: it stays in the model's own output (the argument), and
re-echoing it would double its context cost.

Security model (aligned with Nagi-ovo/dsh-visualize, BSD-3-Clause): the card
runs in `<iframe sandbox="allow-scripts">` with a frame CSP of
`default-src 'none'` — this deployment is intranet-only, so unlike the
upstream CDN allowlist, fragments must inline every resource; the lint gate
rejects external references outright instead of deferring to the frame CSP.
"""

from __future__ import annotations

import re
from typing import Any

from .errors import PiError

VISUALIZE_TOOL_NAME = "visualize"
VISUALIZE_MODES = ("inline", "wide")
DEFAULT_TITLE = "Visualization"
VISUALIZE_KIND = "visualize"

# Hard fragment ceilings. The char cap keeps the model's argument tractable;
# the UTF-8 byte cap keeps the JSON-escaped `tool.end` event inside the
# visual event budget (contract.MAX_VISUAL_EVENT_BYTES) with headroom for the
# envelope and escape expansion.
MAX_FRAGMENT_CHARS = 40_000
MAX_FRAGMENT_BYTES = 80_000

TOOL_DESCRIPTION = (
    "Show the user an interactive HTML visualization rendered as a live, "
    "sandboxed card in the conversation. Pass the whole markup in `fragment`: "
    "literal inline HTML only (no <!doctype>, <html>, <head>, or <body> — the "
    "card supplies the document, stylesheet, and theme) with every script and "
    "style inlined; external resources, network calls, and CDN references are "
    "rejected. Load the `visualize` skill for the authoring contract before "
    "your first call."
)

VISUALIZE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fragment": {
            "type": "string",
            "description": (
                "Required: the inline HTML fragment to render (markup, style, "
                "and script — no document skeleton, no external resources)."
            ),
        },
        "title": {
            "type": "string",
            "description": "Concise card title shown above the card. Defaults to 'Visualization'.",
        },
        "mode": {
            "type": "string",
            "enum": [*VISUALIZE_MODES],
            "description": (
                "Surface: `inline` (default) fits the chat column; `wide` for "
                "compact panels that need more width."
            ),
        },
    },
    "required": ["fragment"],
}

# Document-skeleton tags are rejected: the frame document owns them.
_SKELETON_RE = re.compile(r"<!doctype\s+html|<html[\s>]|<head[\s>]|<body[\s>]", re.IGNORECASE)
# External references of any shape: attributes, CSS url(), @import. Anchors
# (<a href>) are stripped first — only resource-loading attributes are checked.
_ANCHOR_TAG_RE = re.compile(r"</?a\b[^>]*>", re.IGNORECASE)
_EXTERNAL_ATTR_RE = re.compile(
    r"""(?:src|href|poster|data)\s*=\s*["']?\s*(?:https?:)?//""", re.IGNORECASE
)
_EXTERNAL_CSS_RE = re.compile(r"""url\(\s*["']?\s*(?:https?:)?//""", re.IGNORECASE)
# Only remote @import targets are rejected; `@import url(data:…)` is inline
# content and allowed like any data: URI.
_EXTERNAL_IMPORT_RE = re.compile(r"@import\b[^;]*(?:https?:)?//", re.IGNORECASE)
# Relative resource URLs pass the external check but the frame CSP silently
# blocks them — warn so the model inlines the resource instead (reference
# VZ106).
_RELATIVE_RESOURCE_RE = re.compile(
    r"""(?:src|href|poster|data)\s*=\s*["']\s*"""
    r"""(?!data:|blob:|about:|javascript:|mailto:|tel:|#|https?:|//)(?:\.{1,2}/|/)?[\w@%+-]""",
    re.IGNORECASE,
)
# Network APIs: the frame CSP blocks them; rejecting at lint time saves a
# wasted render and teaches the contract.
_NETWORK_API_RE = re.compile(
    r"\bfetch\s*\(|\bXMLHttpRequest\b|\bnew\s+WebSocket\b|\bEventSource\s*\(|"
    r"\bnavigator\.sendBeacon\b",
    re.IGNORECASE,
)
# VZ008: only forms that try to submit (action / method=post / formaction) are
# an error; a bare <form> used as layout is legal.
_FORM_ACTION_RE = re.compile(r"<form\b[^>]*\baction\s*=", re.IGNORECASE)
_FORM_POST_RE = re.compile(r"""<form\b[^>]*\bmethod\s*=\s*["']?post\b""", re.IGNORECASE)
_FORMACTION_RE = re.compile(r"\bformaction\s*=", re.IGNORECASE)
# VZ009: a fragment-declared color-scheme flips every light-dark() against the
# host theme; the frame document already carries the host scheme.
_COLOR_SCHEME_CSS_RE = re.compile(r"color-scheme\s*:", re.IGNORECASE)
_COLOR_SCHEME_JS_RE = re.compile(r"\.style\.colorScheme\s*=(?!=)", re.IGNORECASE)
_COLOR_SCHEME_META_RE = re.compile(r"""<meta[^>]*name\s*=\s*["']?color-scheme""", re.IGNORECASE)
# VZ010: document.currentScript is null/ambiguous in the settled card; find
# roots by id instead.
_CURRENT_SCRIPT_RE = re.compile(r"\bcurrentScript\b")
# VZ108: browser storage throws inside the sandboxed opaque-origin frame and
# stops the card's script dead.
_STORAGE_RE = re.compile(r"\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|\bdocument\.cookie\b")
# VZ004: escape sequences that only appear in markup when it was JSON-escaped.
_ESCAPED_ATTR_RE = re.compile(r"""\b[\w-]+\s*=\s*(?:\\"|\\')""")
_ESCAPED_SCRIPT_LEAD_RE = re.compile(r"<script\b[^>]*>\s*\\[nr]", re.IGNORECASE)
_ESCAPE_SEQ_RE = re.compile(r"\\[nrt]")
# VZ101 (warn): hard-coded colours ignore the host theme. Scanned only inside
# style blocks, style attributes and JS colour writes so prose never trips it.
_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_STYLE_ATTR_RE = re.compile(r"""style\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_JS_COLOR_WRITE_RE = re.compile(
    r"""(?:fillStyle|strokeStyle|\.style\.[\w-]+)\s*=\s*["'`]([^"'`]*)["'`]"""
)
_HEX_COLOR_RE = re.compile(r"#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})\b", re.IGNORECASE)
_COLOR_FN_RE = re.compile(r"\b(?:rgba?|hsla?)\s*\(", re.IGNORECASE)


class FragmentLint:
    """Coded lint over one fragment: errors raise, warnings ride the result."""

    def __init__(self, max_chars: int = MAX_FRAGMENT_CHARS, max_bytes: int = MAX_FRAGMENT_BYTES):
        self.max_chars = max_chars
        self.max_bytes = max_bytes

    def check(self, fragment: str) -> tuple[int, list[str]]:
        """Return (char_size, warnings); raise PiError on any error finding.

        Coded rules ported from Nagi-ovo/dsh-visualize ``src/lint.ts``
        (BSD-3-Clause): the code in each message is stable, so the model can
        match the exact rule it broke without re-reading the skill.
        """
        text = fragment or ""
        size = len(text)
        if size == 0:
            raise PiError(message="[VZ001] invalid visualization: `fragment` is empty")
        if size > self.max_chars:
            raise PiError(
                message=f"[VZ002] invalid visualization: fragment is {size} chars, over the "
                f"{self.max_chars}-char limit; shrink the inline data first (fewer rows, "
                "coarser buckets, fewer decimals)"
            )
        encoded = len(text.encode("utf-8"))
        if encoded > self.max_bytes:
            raise PiError(
                message=f"[VZ002] invalid visualization: fragment is {encoded} UTF-8 bytes, "
                f"over the {self.max_bytes}-byte limit; inline less content per card"
            )
        # VZ004 first: a JSON-escaped fragment fails confusingly later, so name
        # it at the gate.
        self._check_escaped_markup(text)
        if _SKELETON_RE.search(text):
            raise PiError(
                message="[VZ003] invalid visualization: the fragment contains a document-skeleton "
                "tag — write only the inline body; the card supplies "
                "<!doctype>/<html>/<head>/<body>"
            )
        body = _ANCHOR_TAG_RE.sub("", text)
        if (
            _EXTERNAL_ATTR_RE.search(body)
            or _EXTERNAL_CSS_RE.search(body)
            or _EXTERNAL_IMPORT_RE.search(body)
        ):
            raise PiError(
                message="[VZ005] invalid visualization: external resources are rejected in this "
                "deployment (intranet-only) — inline every script, style, font, and "
                "image (data: URIs are accepted)"
            )
        if _NETWORK_API_RE.search(text):
            raise PiError(
                message="[VZ007] invalid visualization: network APIs (fetch/XHR/WebSocket/"
                "EventSource/sendBeacon) are blocked inside the card and fail without an "
                "error — inline the data in the script as a literal instead"
            )
        if (
            _FORM_ACTION_RE.search(text)
            or _FORM_POST_RE.search(text)
            or _FORMACTION_RE.search(text)
        ):
            raise PiError(
                message="[VZ008] invalid visualization: form submission is blocked inside the "
                "card — drop action/method/formaction and handle input in a submit "
                "listener that calls event.preventDefault()"
            )
        if (
            _COLOR_SCHEME_CSS_RE.search(text)
            or _COLOR_SCHEME_JS_RE.search(text)
            or _COLOR_SCHEME_META_RE.search(text)
        ):
            raise PiError(
                message="[VZ009] invalid visualization: the fragment declares color-scheme, "
                "which flips every light-dark() against the host theme — delete it; the "
                "card document already carries the host scheme"
            )
        if _CURRENT_SCRIPT_RE.search(text):
            raise PiError(
                message="[VZ010] invalid visualization: document.currentScript is used to "
                "locate the root — give the root element a unique id and find it with "
                "document.getElementById(...)"
            )
        warnings = self._check_warnings(text, body)
        return size, warnings

    def _check_escaped_markup(self, text: str) -> None:
        """VZ004: three precise signals of a JSON-escaped fragment."""
        if _ESCAPED_ATTR_RE.search(text):
            raise PiError(
                message="[VZ004] invalid visualization: the markup is string-escaped "
                "(attribute quoted as \\\") — send the markup itself, with real \" quotes "
                "and real line breaks, not a JSON-escaped rendition of it"
            )
        hits = 0
        for match in _ESCAPE_SEQ_RE.finditer(text):
            before = text[: match.start()]
            after = text[match.end() :]
            adjacent_to_tag = (
                re.search(r"[<>](?:\\[nrt]|\s)*$", before) is not None
                or re.match(r"(?:\\[nrt]|\s)*[<>]", after) is not None
            )
            if adjacent_to_tag:
                hits += 1
        if hits >= 2 or _ESCAPED_SCRIPT_LEAD_RE.search(text):
            raise PiError(
                message="[VZ004] invalid visualization: the markup is string-escaped "
                "(literal \\\\n where a real line break belongs) — send the markup itself, "
                "not a JSON-escaped rendition of it"
            )

    def _check_warnings(self, text: str, body: str) -> list[str]:
        """Non-fatal findings: relative URLs, sandbox-fatal storage, raw colours."""
        warnings: list[str] = []
        if _RELATIVE_RESOURCE_RE.search(body):
            warnings.append(
                "warning [VZ106]: relative resource URLs cannot resolve inside the sandboxed "
                "card — inline the resource (data: URLs work)"
            )
        storage = sorted({m.group(0) for m in _STORAGE_RE.finditer(text)})
        if storage:
            names = ", ".join(storage[:3])
            warnings.append(
                f"warning [VZ108]: {names} throw inside the sandboxed card and stop the "
                "script — keep state in the fragment's own variables instead"
            )
        colour_pools = [m.group(1) for m in _STYLE_BLOCK_RE.finditer(text)]
        colour_pools += [m.group(1) for m in _STYLE_ATTR_RE.finditer(text)]
        colour_pools += [m.group(1) for m in _JS_COLOR_WRITE_RE.finditer(text)]
        examples: list[str] = []
        for pool in colour_pools:
            examples += [m.group(0) for m in _HEX_COLOR_RE.finditer(pool)]
            if _COLOR_FN_RE.search(pool):
                examples.append("rgb()/hsl()")
        if examples:
            unique = list(dict.fromkeys(examples))
            warnings.append(
                f"warning [VZ101]: hard-coded colour ({', '.join(unique[:3])}) ignores the "
                "host theme — use a theme variable (var(--foreground), var(--viz-series-1), …)"
            )
        return warnings


def resolve_mode(value: Any) -> str:
    """Resolve the `mode` argument; unknown values fail loud, not into a wrong card."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "inline"
    mode = str(value).strip()
    if mode not in VISUALIZE_MODES:
        raise PiError(
            message="invalid visualization: `mode` must be one of "
            + ", ".join(f'"{item}"' for item in VISUALIZE_MODES)
        )
    return mode


def visualize_outcome(arguments: dict[str, Any], max_fragment_chars: int) -> dict[str, Any]:
    """Build the `visualize` internal-tool outcome fields.

    Returns ``{"text", "details", "is_error"}`` for ``ToolOutcome``. The
    model-facing text stays a one-line confirmation; the fragment is projected
    into ``details["visual"]`` for the display observer only.
    """
    lint = FragmentLint(max_chars=max_fragment_chars)
    fragment = arguments.get("fragment")
    if not isinstance(fragment, str):
        raise PiError(message="invalid visualization: `fragment` is required and must be a string")
    mode = resolve_mode(arguments.get("mode"))
    title = str(arguments.get("title") or "").strip() or DEFAULT_TITLE
    if len(title) > 80:
        title = title[:80]
    _size, warnings = lint.check(fragment)
    visual = {
        "fragment": fragment,
        "title": title,
        "mode": mode,
        "size_bytes": len(fragment.encode("utf-8")),
    }
    article = "an" if mode[0] in "aeiou" else "a"
    text = (
        f'Rendered "{title}" as {article} {mode} card '
        f"({visual['size_bytes']} bytes). The user sees the interactive card in the conversation."
    )
    if warnings:
        text = f"{text} " + " ".join(warnings)
    return {
        "text": text,
        "details": {
            "kind": VISUALIZE_KIND,
            "status": "ok",
            "visual": visual,
            "execution_outcome": "executed",
        },
        "is_error": False,
    }
