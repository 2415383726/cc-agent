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
# External references of any shape: attributes, CSS url(), @import.
_EXTERNAL_ATTR_RE = re.compile(
    r"""(?:src|href|poster|data)\s*=\s*["']?\s*(?:https?:)?//""", re.IGNORECASE
)
_EXTERNAL_CSS_RE = re.compile(r"""url\(\s*["']?\s*(?:https?:)?//""", re.IGNORECASE)
_EXTERNAL_IMPORT_RE = re.compile(r"@import\b", re.IGNORECASE)
# Network APIs: the frame CSP blocks them; rejecting at lint time saves a
# wasted render and teaches the contract.
_NETWORK_API_RE = re.compile(
    r"\bfetch\s*\(|\bXMLHttpRequest\b|\bnew\s+WebSocket\b|\bEventSource\s*\(|"
    r"\bnavigator\.sendBeacon\b",
    re.IGNORECASE,
)
_FORM_RE = re.compile(r"<form[\s>]", re.IGNORECASE)


class FragmentLint:
    """Coded lint over one fragment: errors raise, warnings ride the result."""

    def __init__(self, max_chars: int = MAX_FRAGMENT_CHARS, max_bytes: int = MAX_FRAGMENT_BYTES):
        self.max_chars = max_chars
        self.max_bytes = max_bytes

    def check(self, fragment: str) -> tuple[int, list[str]]:
        """Return (char_size, warnings); raise PiError on any error finding."""
        text = fragment or ""
        size = len(text)
        if size == 0:
            raise PiError(message="invalid visualization: `fragment` is empty")
        if size > self.max_chars:
            raise PiError(
                message=f"invalid visualization: fragment is {size} chars, over the "
                f"{self.max_chars}-char limit; split the content or simplify the card"
            )
        encoded = len(text.encode("utf-8"))
        if encoded > self.max_bytes:
            raise PiError(
                message=f"invalid visualization: fragment is {encoded} UTF-8 bytes, over the "
                f"{self.max_bytes}-byte limit; inline less content per card"
            )
        if _SKELETON_RE.search(text):
            raise PiError(
                message="invalid visualization: the fragment must be inline markup — "
                "<!doctype>/<html>/<head>/<body> are supplied by the card"
            )
        if _EXTERNAL_ATTR_RE.search(text) or _EXTERNAL_CSS_RE.search(text) or _EXTERNAL_IMPORT_RE.search(text):
            raise PiError(
                message="invalid visualization: external resources are rejected in this "
                "deployment (intranet-only); inline every script, style, font, "
                "and image (data: URIs are accepted)"
            )
        if _NETWORK_API_RE.search(text):
            raise PiError(
                message="invalid visualization: network APIs (fetch/XHR/WebSocket/"
                "EventSource/sendBeacon) are rejected — the card cannot reach "
                "any server"
            )
        warnings: list[str] = []
        if _FORM_RE.search(text):
            warnings.append(
                "warning: <form> submission is blocked by the card's CSP; use "
                "buttons with inline script handlers instead"
            )
        return size, warnings


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
    size, warnings = lint.check(fragment)
    visual = {
        "fragment": fragment,
        "title": title,
        "mode": mode,
        "size_bytes": len(fragment.encode("utf-8")),
    }
    text = f'Rendered "{title}" as an {mode} card ({size} chars). The user sees the interactive card in the conversation.'
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
