"""The finite Pi display contract carried through Dify logs.

Schema v1 is intentionally small: message lifecycle, reasoning lifecycle, tool
lifecycle, host activities (skills, compaction, questions, approvals) and one
terminal run state. Unknown or malformed events are ignored by the workbench,
which never treats a Pi ``message_end`` as a host terminal state.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "piagent.display.v1"
SCHEMA_VERSION = 1
TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "awaiting_user",
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

MAX_EVENT_BYTES = 24_000
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
    if match.re.pattern.startswith("(?i)\\b(authorization"):
        return f"{prefix}[redacted]"
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


@dataclass(slots=True)
class DisplayEvents:
    """Per-run event sequencer. One instance per Dify request; never shared."""

    run_id: str
    seq: int = 0
    emitted: int = 0
    max_events: int = 400
    max_bytes: int = MAX_EVENT_BYTES
    dropped: int = 0

    def make(self, event_type: str, **fields: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "type": event_type,
            "run_id": self.run_id,
            "seq": self.seq,
            "ts": int(time.time() * 1000),
        }
        self.seq += 1
        for key, value in fields.items():
            if value is not None:
                payload[key] = value
        return self.fit(payload)

    def fit(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(encoded.encode("utf-8")) <= self.max_bytes:
            return payload
        trimmed = dict(payload)
        for key in ("result", "output", "answer", "text", "arguments", "questions", "content"):
            if key in trimmed:
                trimmed[key] = clip(trimmed[key], max(512, self.max_bytes // 3))
        encoded = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(encoded.encode("utf-8")) > self.max_bytes:
            trimmed = {
                "schema": payload.get("schema"),
                "schema_version": payload.get("schema_version"),
                "type": payload.get("type"),
                "run_id": payload.get("run_id"),
                "seq": payload.get("seq"),
                "ts": payload.get("ts"),
                "truncated": True,
            }
        return trimmed

    def allow(self) -> bool:
        if self.emitted >= self.max_events:
            self.dropped += 1
            return False
        return True

    def record(self, event: dict[str, Any]) -> dict[str, Any] | None:
        if not self.allow():
            return None
        self.emitted += 1
        return event


def terminal_status(status: str) -> str:
    return status if status in TERMINAL_STATUSES else "unknown"


def run_state_payload(
    *,
    status: str,
    stats: dict[str, Any],
    answer: str = "",
    state_ref: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    pending: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": terminal_status(status),
        "stats": stats,
        "answer": clip(answer, 16_000),
    }
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
        "storage": "piagent-state:v1:gzip-base64:",
        "revision": revision,
        "run_id": run_id,
        "delivery_status": "encoded" if persisted else "failed",
        "platform_persisted": None,
        "encoded_bytes": encoded_bytes,
        "payload_bytes": payload_bytes,
        "compacted": compacted,
        "storage_error": error,
    }


@dataclass(slots=True)
class OutboxMessage:
    """A Dify-native message request produced by the runtime, not an SDK type."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
