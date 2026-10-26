from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HistoryState:
    messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    version: int = 1


def load_history(value: str | list[dict[str, Any]] | dict[str, Any] | None) -> HistoryState:
    if not value:
        return HistoryState()
    payload: Any = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return HistoryState(messages=[{"role": "user", "content": value}])
    if isinstance(payload, list):
        return HistoryState(messages=sanitize_history(payload), version=1)
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if messages is None:
            messages = payload.get("history", [])
        summary = payload.get("summary") or payload.get("conversation_summary") or ""
        version = _positive_int(payload.get("version"), 1)
        if not isinstance(messages, list):
            messages = []
        return HistoryState(messages=sanitize_history(messages), summary=str(summary), version=version)
    return HistoryState()


def dump_history(messages: list[dict[str, Any]], summary: str = "") -> str:
    return json.dumps(
        {"messages": sanitize_history(messages), "summary": summary or "", "version": 1},
        ensure_ascii=False,
    )


def sanitize_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    pending_ids: set[str] = set()

    for original in messages:
        if not isinstance(original, dict):
            continue
        message = copy.deepcopy(original)
        role = message.get("role")

        if role == "tool":
            tool_call_id = str(message.get("tool_call_id") or message.get("id") or "")
            if tool_call_id and tool_call_id in pending_ids:
                message["tool_call_id"] = tool_call_id
                clean.append(_normalize_tool_message(message))
                pending_ids.remove(tool_call_id)
            continue

        if pending_ids:
            _strip_pending_tool_calls(clean, pending_ids)
            pending_ids.clear()

        if role == "assistant":
            # reasoning_content is only meaningful during the streaming turn when
            # DeepSeek compat preserves it.  Once persisted or carried into a
            # subsequent run it becomes stale and triggers unwanted fallback
            # flattening that leaks "Assistant requested tool calls:" into the
            # frontend.  Strip it here so history stays clean.
            message.pop("reasoning_content", None)
            tool_calls = _normalize_tool_calls(message.get("tool_calls") or [])
            if tool_calls:
                message["tool_calls"] = tool_calls
                pending_ids.update(str(tool_call["id"]) for tool_call in tool_calls if tool_call.get("id"))
            elif "tool_calls" in message:
                message.pop("tool_calls", None)
            clean.append(message)
        elif role in {"system", "user"}:
            clean.append(message)

    if pending_ids:
        _strip_pending_tool_calls(clean, pending_ids)
    return clean


def _strip_pending_tool_calls(messages: list[dict[str, Any]], pending_ids: set[str]) -> None:
    for message in messages:
        if message.get("role") != "assistant" or not message.get("tool_calls"):
            continue
        remaining = [
            tool_call
            for tool_call in message["tool_calls"]
            if str(tool_call.get("id") or "") not in pending_ids
        ]
        if remaining:
            message["tool_calls"] = remaining
        else:
            message.pop("tool_calls", None)


def _normalize_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, tool_call in enumerate(tool_calls):
        if not isinstance(tool_call, dict):
            continue
        call_id = str(tool_call.get("id") or f"call_{index}")
        name = str(tool_call.get("name") or "")
        arguments = tool_call.get("arguments", {})
        if not name and isinstance(tool_call.get("function"), dict):
            function = tool_call["function"]
            name = str(function.get("name") or "")
            raw_arguments = function.get("arguments", "{}")
            arguments = _parse_arguments(raw_arguments)
        if isinstance(arguments, str):
            arguments = _parse_arguments(arguments)
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}
        if name:
            normalized.append({"id": call_id, "name": name, "arguments": arguments})
    return normalized


def _normalize_tool_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": str(message.get("tool_call_id") or ""),
        "name": str(message.get("name") or ""),
        "content": str(message.get("content") or "(tool completed with no output)"),
        **({"metadata": message["metadata"]} if isinstance(message.get("metadata"), dict) else {}),
        **({"is_error": bool(message.get("is_error"))} if "is_error" in message else {}),
        **({"synthetic": bool(message.get("synthetic"))} if "synthetic" in message else {}),
    }


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        return {"_raw_arguments": str(raw or "")}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
