from __future__ import annotations

from typing import Any

from .manifest import utc_now_iso

HISTORY_SCHEMA_VERSION = 1


class HistoryStoreConflict(RuntimeError):
    pass


def history_key(workspace_prefix: str) -> str:
    return f"{workspace_prefix.rstrip('/')}/history/recent.json"


def load_history_from_storage(storage: Any, workspace_prefix: str) -> dict[str, Any] | None:
    key = history_key(workspace_prefix)
    payload = storage.get_json(key)
    if not isinstance(payload, dict):
        return None
    return _normalize_payload(payload)


def save_history_to_storage(
    storage: Any,
    workspace_prefix: str,
    messages: list[dict[str, Any]],
    summary: str = "",
    version: int = 1,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    key = history_key(workspace_prefix)
    current = load_history_from_storage(storage, workspace_prefix)
    current_revision = int((current or {}).get("revision") or 0)
    if expected_revision is not None and current_revision != int(expected_revision):
        raise HistoryStoreConflict(
            f"history revision conflict: expected {expected_revision}, got {current_revision}"
        )
    payload: dict[str, Any] = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "revision": current_revision + 1,
        "messages": messages,
        "summary": summary or "",
        "version": version,
        "updated_at": utc_now_iso(),
    }
    storage.put_json(key, payload)
    return payload


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": int(payload.get("schema_version") or HISTORY_SCHEMA_VERSION),
        "revision": int(payload.get("revision") or 0),
        "messages": payload.get("messages") if isinstance(payload.get("messages"), list) else [],
        "summary": str(payload.get("summary") or ""),
        "version": int(payload.get("version") or 1),
        "updated_at": str(payload.get("updated_at") or ""),
    }
