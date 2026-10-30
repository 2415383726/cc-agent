"""Translate Pi harness events into the finite display contract."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .contract import DisplayEvents, clip, clip_arguments, log_envelope

TEXT_EVENT_TYPES = {"text_delta", "thinking_delta"}


class DisplayObserver:
    def __init__(self, events: DisplayEvents, emit: Callable[[dict[str, Any]], None], config: Any):
        self.events = events
        self.emit = emit
        self.config = config
        self._assistant_index = 0
        self._assistant_id = ""
        self._reasoning_id = ""
        self._text_buffer = ""
        self._reasoning_buffer = ""
        self._tool_started: dict[str, float] = {}
        self._tool_updates: dict[str, int] = {}

    async def __call__(self, event: Any, signal: Any | None = None) -> None:
        kind = getattr(event, "type", "")
        if kind == "message_start":
            self._message_start(getattr(event, "message", None))
        elif kind == "message_update":
            self._message_update(event)
        elif kind == "message_end":
            self._message_end(getattr(event, "message", None))
        elif kind == "tool_execution_start":
            self._tool_start(event)
        elif kind == "tool_execution_update":
            self._tool_update(event)
        elif kind == "tool_execution_end":
            self._tool_end(event)
        elif kind == "session_before_compact":
            preparation = getattr(event, "preparation", None)
            self._push(
                "compaction.start",
                {
                    "tokens_before": getattr(preparation, "tokensBefore", 0),
                    "messages_kept": len(getattr(preparation, "keptMessages", []) or []),
                },
            )
        elif kind == "session_compact":
            result = getattr(event, "result", None)
            self._push(
                "compaction.end",
                {
                    "tokens_before": getattr(result, "tokensBefore", 0),
                    "summary_chars": len(str(getattr(result, "summary", "") or "")),
                    "first_kept_entry_id": getattr(result, "firstKeptEntryId", ""),
                },
            )
        elif kind == "notice":
            self._push(
                "activity", {"activity": "notice", "text": clip(getattr(event, "text", ""), 500)}
            )
        elif kind == "abort":
            self._push("activity", {"activity": "abort"})

    def activity(self, event_type: str, fields: dict[str, Any]) -> None:
        self._push(event_type, fields)

    def _message_start(self, message: Any) -> None:
        role = getattr(message, "role", None)
        if role == "user":
            self._push(
                "message.user",
                {
                    "message_id": f"user_{self.events.run_id}_{self._assistant_index}",
                    "text": clip(_message_text(message), 8_000),
                },
            )
        elif role == "assistant":
            self._flush_text()
            self._flush_reasoning()
            self._assistant_index += 1
            self._assistant_id = f"asst_{self.events.run_id}_{self._assistant_index}"
            self._reasoning_id = f"reason_{self.events.run_id}_{self._assistant_index}"
            self._push("message.start", {"message_id": self._assistant_id, "role": "assistant"})
        elif role == "custom":
            self._push(
                "activity",
                {
                    "activity": "host.note",
                    "custom_type": getattr(message, "customType", "") or "",
                    "text": clip(_message_text(message), 2_000),
                },
            )

    def _message_update(self, event: Any) -> None:
        inner = getattr(event, "assistant_message_event", None)
        inner_type = getattr(inner, "type", "")
        if inner_type == "text_delta":
            self._push(
                "message.delta",
                {"message_id": self._assistant_id, "delta": str(getattr(inner, "delta", "") or "")},
            )
        elif inner_type == "thinking_delta":
            self._push(
                "reasoning.delta",
                {
                    "reasoning_id": self._reasoning_id,
                    "delta": str(getattr(inner, "delta", "") or ""),
                },
            )
        elif inner_type == "thinking_end":
            self._push("reasoning.end", {"reasoning_id": self._reasoning_id})

    def _message_end(self, message: Any) -> None:
        if getattr(message, "role", None) != "assistant":
            return
        self._flush_text()
        self._flush_reasoning()
        text = _message_text(message)
        self._push(
            "message.end",
            {
                "message_id": self._assistant_id,
                "text": clip(text, 16_000),
                "stop_reason": str(getattr(message, "stopReason", "stop") or "stop"),
                "has_tool_calls": any(
                    isinstance(block, dict) and block.get("type") == "toolCall"
                    for block in getattr(message, "content", []) or []
                ),
            },
        )
        if self._reasoning_id:
            self._push("reasoning.end", {"reasoning_id": self._reasoning_id})

    def _tool_start(self, event: Any) -> None:
        call_id = str(getattr(event, "tool_call_id", "") or "")
        self._tool_started[call_id] = time.monotonic()
        self._push(
            "tool.start",
            {
                "tool_call_id": call_id,
                "name": str(getattr(event, "tool_name", "") or ""),
                "arguments": clip_arguments(getattr(event, "args", {})),
            },
        )

    def _tool_update(self, event: Any) -> None:
        call_id = str(getattr(event, "tool_call_id", "") or "")
        count = self._tool_updates.get(call_id, 0)
        if count >= 3:
            return
        self._tool_updates[call_id] = count + 1
        partial = getattr(event, "partial_result", None)
        text = _content_text(getattr(partial, "content", [])) if partial is not None else ""
        self._push("tool.update", {"tool_call_id": call_id, "text": clip(text, 1_500)})

    def _tool_end(self, event: Any) -> None:
        call_id = str(getattr(event, "tool_call_id", "") or "")
        result = getattr(event, "result", None)
        details = getattr(result, "details", None) or {}
        if not isinstance(details, dict):
            details = {}
        is_error = bool(getattr(event, "is_error", False))
        status = str(details.get("status") or ("error" if is_error else "ok"))
        if status in {"awaiting_user", "awaiting_approval"}:
            display_status = status
        elif details.get("execution_outcome") == "unknown":
            display_status = "unknown"
        elif status == "not_executed":
            display_status = "not_executed"
        elif is_error or status == "error":
            display_status = "error"
        else:
            display_status = "ok"
        text = _content_text(getattr(result, "content", []))
        started = self._tool_started.pop(call_id, None)
        duration_ms = int((time.monotonic() - started) * 1000) if started else 0
        fields: dict[str, Any] = {
            "tool_call_id": call_id,
            "name": str(getattr(event, "tool_name", "") or ""),
            "status": display_status,
            "is_error": is_error,
            "execution_outcome": details.get("execution_outcome")
            or ("unknown" if display_status == "unknown" else "executed"),
            "result": clip(
                str(details.get("display_text") or text), self.config.display_result_chars
            ),
            "duration_ms": duration_ms,
        }
        if details.get("artifacts"):
            fields["artifacts"] = details["artifacts"]
        if details.get("kind"):
            fields["kind"] = details["kind"]
        if details.get("skill"):
            fields["skill"] = details["skill"]
        if details.get("path"):
            fields["path"] = details["path"]
        if details.get("business_ref"):
            fields["business_ref"] = details["business_ref"]
        if details.get("approval"):
            fields["approval"] = details["approval"]
        if details.get("questionnaire"):
            fields["questionnaire"] = details["questionnaire"]
        self._push("tool.end", fields)

    def _flush_text(self) -> None:
        if not self._text_buffer:
            return
        delta, self._text_buffer = self._text_buffer, ""
        self._push("message.delta", {"message_id": self._assistant_id, "delta": delta})

    def _flush_reasoning(self) -> None:
        if not self._reasoning_buffer:
            return
        delta, self._reasoning_buffer = self._reasoning_buffer, ""
        self._push("reasoning.delta", {"reasoning_id": self._reasoning_id, "delta": delta})

    def _push(self, event_type: str, fields: dict[str, Any]) -> None:
        event = self.events.make(event_type, **fields)
        recorded = self.events.record(event)
        if recorded is not None:
            self.emit(log_envelope(recorded))


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return _content_text(content)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(part for part in parts if part)
    return ""
