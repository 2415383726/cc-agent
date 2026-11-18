"""Translate Pi harness events into Dify-native messages.

Mirrors the retired ``CC Agent (Dify)`` UX: reasoning streams wrapped in
``<think>`` tags and closes lazily on the next non-thinking output, tool
results render as HTML tool cards (params + result, 8000-char clip), and host
activities go to ``<details>`` logs. The built-in Dify UI is the only consumer.
"""

from __future__ import annotations

import html
import json
import time
from collections.abc import Callable
from typing import Any

from .native import NativeEvents, clip, clip_arguments

TOOL_CARD_RESULT_CHARS = 8_000


class NativeObserver:
    def __init__(self, events: NativeEvents, emit: Callable[[dict[str, Any]], None], config: Any):
        self.events = events
        self.emit = emit
        self.config = config
        self._reasoning_open = False
        self._tool_inputs: dict[str, dict[str, Any]] = {}
        self._tool_started: dict[str, float] = {}

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
        elif kind == "tool_execution_end":
            self._tool_end(event)
        elif kind == "tool_execution_update":
            pass  # Native UX shows one finished card per tool, no partials.
        elif kind == "session_before_compact":
            preparation = getattr(event, "preparation", None)
            self._log(
                "Compaction started",
                {
                    "tokens_before": getattr(preparation, "tokensBefore", 0),
                    "messages_kept": len(getattr(preparation, "keptMessages", []) or []),
                },
            )
        elif kind == "session_compact":
            result = getattr(event, "result", None)
            self._log(
                "Compaction finished",
                {
                    "tokens_before": getattr(result, "tokensBefore", 0),
                    "summary_chars": len(str(getattr(result, "summary", "") or "")),
                    "first_kept_entry_id": getattr(result, "firstKeptEntryId", ""),
                },
            )
        elif kind == "notice":
            self._log("Notice", {"text": clip(getattr(event, "text", ""), 500)})
        elif kind == "abort":
            self._log("Run aborted", {})

    def activity(self, event_type: str, fields: dict[str, Any]) -> None:
        self._log(_activity_label(event_type), fields)

    # -- message lifecycle --------------------------------------------------

    def _message_start(self, message: Any) -> None:
        role = getattr(message, "role", None)
        if role == "custom":
            # Host notes (skill activations, continuation notes) stay logs;
            # echoing them as text would interleave with the answer stream.
            self._log(
                _activity_label(str(getattr(message, "customType", "") or "host.note")),
                {"text": clip(_message_text(message), 2_000)},
            )

    def _message_update(self, event: Any) -> None:
        inner = getattr(event, "assistant_message_event", None)
        inner_type = getattr(inner, "type", "")
        if inner_type == "text_delta":
            delta = str(getattr(inner, "delta", "") or "")
            if delta:
                self._text(self._close_reasoning_prefix() + delta)
        elif inner_type == "thinking_delta":
            delta = str(getattr(inner, "delta", "") or "")
            if delta:
                content = delta
                if not self._reasoning_open:
                    self._reasoning_open = True
                    content = "<think>" + content
                self._text(content)
        elif inner_type == "thinking_end":
            pass  # Closed lazily when the next text/tool output arrives.

    def _message_end(self, message: Any) -> None:
        if getattr(message, "role", None) != "assistant":
            return
        if self._reasoning_open:
            self._text(self._close_reasoning_prefix())

    # -- tool lifecycle -----------------------------------------------------

    def _tool_start(self, event: Any) -> None:
        call_id = str(getattr(event, "tool_call_id", "") or "")
        args = getattr(event, "args", {})
        self._tool_inputs[call_id] = args if isinstance(args, dict) else {}
        self._tool_started[call_id] = time.monotonic()

    def _tool_end(self, event: Any) -> None:
        call_id = str(getattr(event, "tool_call_id", "") or "")
        result = getattr(event, "result", None)
        details = getattr(result, "details", None) or {}
        if not isinstance(details, dict):
            details = {}
        is_error = bool(getattr(event, "is_error", False))
        display_status = display_status_for(details, is_error)
        name = str(getattr(event, "tool_name", "") or "")
        arguments = self._tool_inputs.pop(call_id, None)
        if arguments is None:
            arguments = {}
        result_text = str(
            details.get("display_text") or _content_text(getattr(result, "content", []))
        )
        result_limit = int(
            getattr(self.config, "display_result_chars", TOOL_CARD_RESULT_CHARS)
            or TOOL_CARD_RESULT_CHARS
        )
        started = self._tool_started.pop(call_id, None)
        duration_ms = int((time.monotonic() - started) * 1000) if started else 0
        card = _tool_card(
            name,
            clip_arguments(arguments),
            result_text,
            is_error=is_error,
            display_status=display_status,
            duration_ms=duration_ms,
            result_limit=result_limit,
        )
        self._text(self._close_reasoning_prefix() + card)

    # -- helpers ------------------------------------------------------------

    def _text(self, content: str) -> None:
        if content:
            self.emit(self.events.text(content))

    def _log(self, label: str, data: Any, *, is_error: bool = False) -> None:
        logged = self.events.log(label, data, is_error=is_error)
        if logged is not None:
            self.emit(logged)

    def _close_reasoning_prefix(self) -> str:
        if not self._reasoning_open:
            return ""
        self._reasoning_open = False
        return "</think>"


def display_status_for(details: dict[str, Any], is_error: bool) -> str:
    """Map a tool outcome's details onto the card display status."""
    status = str(details.get("status") or ("error" if is_error else "ok"))
    if details.get("execution_outcome") == "unknown":
        return "unknown"
    if status == "not_executed":
        return "not_executed"
    if is_error or status == "error":
        return "error"
    return "ok"


def _activity_label(event_type: str) -> str:
    return {
        "activity": "Activity",
        "host.note": "Host note",
        "skills.discovered": "Skills discovered",
        "skill.activate": "Skill activated",
        "skill.rejected": "Skill rejected",
        "skill.read": "Skill Read",
        "mcp.error": "MCP error",
        "compaction.start": "Compaction started",
        "compaction.end": "Compaction finished",
    }.get(event_type, event_type.replace("_", " ").replace(".", " ").strip().title() or "Activity")


def _tool_card(
    tool_name: str,
    arguments: Any,
    result: Any,
    *,
    is_error: bool = False,
    display_status: str = "ok",
    duration_ms: int = 0,
    result_limit: int = TOOL_CARD_RESULT_CHARS,
) -> str:
    """HTML tool card in the ``CC Agent (Dify)`` shape.

    Arguments and result are escaped and clipped before rendering.
    """
    safe_name = html.escape(str(tool_name or "unknown_tool"))
    safe_params = html.escape(_json_pretty(arguments if isinstance(arguments, dict) else {}))
    safe_result = html.escape(
        _truncate(clip(_display_text(result), result_limit), TOOL_CARD_RESULT_CHARS)
    )
    ok = display_status == "ok"
    dot_color = (
        "#10b981"
        if ok
        else (
            "#f59e0b"
            if display_status == "unknown" or display_status == "not_executed"
            else "#ef4444"
        )
    )
    dot_shadow = {
        "#10b981": "rgba(16, 185, 129, 0.2)",
        "#f59e0b": "rgba(245, 158, 11, 0.2)",
        "#ef4444": "rgba(239, 68, 68, 0.2)",
    }[dot_color]
    title = {"ok": "已运行", "unknown": "结果未知", "not_executed": "未执行"}.get(
        display_status, "运行失败"
    )
    result_label = "错误" if is_error else "结果"
    duration_note = f" · {duration_ms} ms" if duration_ms else ""
    sections = f"""
                <div>
                    <div style="font-size: 12px; font-weight: 600; opacity: 0.55; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
                        参数 (Params)
                    </div>
                    <pre style="margin: 0; padding: 10px 12px; background-color: rgba(128, 128, 128, 0.05); border-radius: 6px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; opacity: 0.85;">{safe_params}</pre>
                </div>
                <div>
                    <div style="font-size: 12px; font-weight: 600; opacity: 0.55; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                        {result_label} (Result)
                    </div>
                    <pre style="margin: 0; padding: 10px 12px; background-color: rgba(16, 185, 129, 0.04); border-left: 3px solid rgba(16, 185, 129, 0.4); border-radius: 0 6px 6px 0; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; opacity: 0.9;">{safe_result}</pre>
                </div>"""
    return (
        '<div style="margin: 12px 0; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 8px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif;">'
        "<details style=\"width: 100%;\">"
        '<summary style="padding: 10px 16px; background-color: rgba(128, 128, 128, 0.04); cursor: pointer; display: flex; align-items: center; gap: 8px; list-style: none; outline: none; user-select: none;">'
        f'<span style="display: block; width: 6px; height: 6px; border-radius: 50%; background-color: {dot_color}; box-shadow: 0 0 0 2px {dot_shadow}; flex-shrink: 0;"></span>'
        f'<span style="font-weight: 600; font-size: 13px; opacity: 0.9;">{title}{duration_note}</span>'
        '<span style="display: inline-flex; align-items: center; padding: 2px 10px; background-color: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.15); border-radius: 999px; color: #6366f1; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; font-weight: 600;">'
        ">_&nbsp;"
        f"{safe_name}"
        "</span>"
        "</summary>"
        '<div style="padding: 16px; border-top: 1px solid rgba(128, 128, 128, 0.15); background-color: rgba(128, 128, 128, 0.015); display: flex; flex-direction: column; gap: 14px;">'
        f"{sections}"
        "</div>"
        "</details>"
        "</div>"
    )


def _display_text(value: Any) -> str:
    if value is None or value == "":
        return "(tool completed with no output)"
    if isinstance(value, str):
        return value
    return _json_pretty(value)


def _truncate(value: str, limit: int = TOOL_CARD_RESULT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_pretty(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return str(value)


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
