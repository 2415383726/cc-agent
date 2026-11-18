"""Dify-native output surface: message kinds, guards and terminal payloads.

The built-in Dify UI is the only consumer. Assistant text and reasoning stream
as text messages (reasoning wrapped in ``<think>`` tags), tool activity renders
as HTML tool cards, host activities and terminal facts go to logs, artifacts go
to blob messages, conversation state goes to the ``agent_state`` variable and
one final JSON payload carries the terminal run state.

There is no display contract and no workbench consumer: unknown kinds are
simply logs, and the guards below (redaction, clipping, event budgets) exist
to keep secrets and oversized payloads out of the Dify stream.
"""

from __future__ import annotations

import json
import re
from typing import Any

TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "awaiting_approval",
        "failed",
        "stopped",
        "budget_exhausted",
        "context_overflow",
        "context_too_large",
        "state_save_failed",
        "cancelled",
        "unknown",
    }
)

# Structural logs (activity, compaction, terminal facts) share a per-run budget;
# text deltas are the answer itself and bypass it.
MAX_LOG_EVENTS = 400
MAX_LOG_DATA_CHARS = 8_000
MAX_RESULT_CHARS = 8_000
MAX_ARGUMENT_CHARS = 4_000
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization\s*:\s*)(bearer\s+)?[^\s\"']+"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\s*[=:]\s*[^\s,;\"']+"),
    re.compile(r"(?i)(https?://[^/\s:@]+):([^@\s/]+)@"),
)


def redact(text: str) -> str:
    value = str(text or "")
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(lambda match: _redacted_match(match), value)
    return value


def _redacted_match(match: re.Match[str]) -> str:
    if match.re.pattern.startswith("(?i)(https?"):
        return f"{match.group(1)}:[redacted]@"
    prefix = match.group(1) or ""
    return f"{prefix}[redacted]"


def clip(text: Any, limit: int = MAX_RESULT_CHARS) -> str:
    value = redact(str(text or ""))
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 20)] + f"\n[trimmed {len(value) - limit} chars]"


def clip_arguments(value: Any, limit: int = MAX_ARGUMENT_CHARS) -> Any:
    """Return a JSON-safe, size-limited projection of tool arguments."""

    def walk(item: Any, depth: int = 0) -> Any:
        if depth > 6:
            return "[nested]"
        if isinstance(item, str):
            return clip(item, max(256, limit // 4))
        if isinstance(item, (int, float, bool)) or item is None:
            return item
        if isinstance(item, list):
            return [walk(entry, depth + 1) for entry in item[:50]]
        if isinstance(item, dict):
            return {
                clip(str(key), 120): walk(value, depth + 1)
                for key, value in list(item.items())[:60]
            }
        return clip(str(item), 256)

    projected = walk(value)
    encoded = json.dumps(projected, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(encoded) <= limit:
        return projected
    return {"preview": clip(encoded, limit)}


class NativeEvents:
    """Per-run output sequencer. One instance per Dify request; never shared.

    Text/blob/state/json messages are the run's content and always pass; only
    structural logs are budgeted so a chatty host cannot flood the stream.
    """

    def __init__(self, run_id: str, max_logs: int = MAX_LOG_EVENTS):
        self.run_id = run_id
        self.max_logs = max_logs
        self.logs = 0
        self.dropped = 0

    def log(self, label: str, data: Any, *, is_error: bool = False) -> dict[str, Any] | None:
        if self.logs >= self.max_logs:
            self.dropped += 1
            return None
        self.logs += 1
        return native_log(label, data, is_error=is_error)

    def text(self, content: str) -> dict[str, Any]:
        return {"type": "text", "content": str(content or "")}

    def state(self, value: str) -> dict[str, Any]:
        return {"type": "state", "name": "agent_state", "value": str(value or "")}

    def json(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"type": "json", "payload": payload if isinstance(payload, dict) else {}}

    def blob(self, blob: Any, meta: dict[str, Any]) -> dict[str, Any]:
        return {"type": "blob", "blob": blob, "meta": meta if isinstance(meta, dict) else {}}


def native_log(label: str, data: Any, *, is_error: bool = False) -> dict[str, Any]:
    """A Dify log message in the ``CC Agent (Dify)`` shape: raw JSON plus an
    HTML ``<details>`` rendering, both redacted and size-clipped."""
    raw = json.loads(json.dumps(_safe_data(data), ensure_ascii=False, default=str))
    return {
        "type": "log",
        "label": clip(str(label or "Log"), 200),
        "data": {"raw": raw, "html": details_html(label, raw)},
        "is_error": bool(is_error),
    }


def _safe_data(value: Any) -> Any:
    if isinstance(value, str):
        return clip(value, MAX_LOG_DATA_CHARS)
    if isinstance(value, dict):
        return {str(key): _safe_data(item) for key, item in list(value.items())[:60]}
    if isinstance(value, (list, tuple)):
        return [_safe_data(item) for item in list(value)[:60]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return clip(str(value), MAX_LOG_DATA_CHARS)


def details_html(summary: str, value: Any) -> str:
    import html

    safe_summary = html.escape(str(summary or "Log"))
    try:
        body = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        body = str(value)
    return f"<details><summary>{safe_summary}</summary><pre>{html.escape(body)}</pre></details>"


def terminal_status(status: str) -> str:
    return status if status in TERMINAL_STATUSES else "unknown"


def run_state_payload(
    *,
    status: str,
    stats: dict[str, Any],
    answer: str = "",
    state_ref: dict[str, Any] | None = None,
    state_summary: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    pending: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": terminal_status(status),
        "stats": stats,
        "answer": clip(answer, 16_000),
    }
    if state_summary:
        payload["state_summary"] = state_summary
    if state_ref:
        payload["state_ref"] = state_ref
    if error:
        payload["error"] = error
    if pending:
        payload["pending"] = pending
    return payload


def public_state_ref(
    *,
    conversation_id: str,
    revision: int,
    run_id: str,
    encoded_bytes: int,
    payload_bytes: int,
    persisted: bool,
    error: str | None = None,
    compacted: bool = False,
) -> dict[str, Any]:
    return {
        "conversation_id": conversation_id,
        "variable_name": "agent_state",
        "storage": "pistrategy-state:v1:gzip-base64:",
        "revision": revision,
        "run_id": run_id,
        "delivery_status": "encoded" if persisted else "failed",
        "platform_persisted": None,
        "encoded_bytes": encoded_bytes,
        "payload_bytes": payload_bytes,
        "compacted": compacted,
        "storage_error": error,
    }
