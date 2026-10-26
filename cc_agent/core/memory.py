from __future__ import annotations

import json
from typing import Any


def load_memory(value: str | list[dict[str, Any]] | dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = _load_json_like(value)
    if isinstance(payload, dict):
        payload = payload.get("memory", [])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def search_memory(memory: list[dict[str, Any]], query: str, memory_type: str = "") -> list[dict[str, Any]]:
    query = str(query or "").lower()
    memory_type = str(memory_type or "").lower()
    if not query:
        candidates = memory
    else:
        candidates = []
        for item in memory:
            haystack = json.dumps(item, ensure_ascii=False).lower()
            if query in haystack:
                candidates.append(item)
    if memory_type:
        candidates = [item for item in candidates if str(item.get("type") or "").lower() == memory_type]
    return sorted(candidates, key=lambda item: _float_or_default(item.get("confidence"), 1.0), reverse=True)


def save_memory(memory: list[dict[str, Any]], item: dict[str, Any]) -> dict[str, Any]:
    key = str(item.get("key") or item.get("id") or item.get("title") or f"memory_{len(memory) + 1}")
    record = {
        "key": key,
        "type": str(item.get("type") or "reference"),
        "confidence": _float_or_default(item.get("confidence"), 1.0),
        "source": str(item.get("source") or "cc_agent"),
        **item,
    }
    for index, existing in enumerate(memory):
        if str(existing.get("key") or existing.get("id") or "") == key:
            memory[index] = {**existing, **record}
            return memory[index]
    memory.append(record)
    return record


def _float_or_default(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def delete_memory(memory: list[dict[str, Any]], key: str) -> bool:
    key = str(key or "")
    before = len(memory)
    memory[:] = [
        item
        for item in memory
        if str(item.get("key") or item.get("id") or item.get("title") or "") != key
    ]
    return len(memory) != before


def _load_json_like(value: Any) -> Any:
    if not value:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value
