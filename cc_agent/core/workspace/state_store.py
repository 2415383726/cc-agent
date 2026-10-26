from __future__ import annotations

from typing import Any

from ..state_variable import AgentStateBundle, bundle_from_parts, state_summary
from .manifest import utc_now_iso
from .storage_client import ConditionalWriteConflict

STATE_SCHEMA_VERSION = 1


class StateStoreConflict(RuntimeError):
    pass


def state_key(workspace_prefix: str) -> str:
    return f"{workspace_prefix.rstrip('/')}/state/current.json"


def load_state_from_storage(storage: Any, workspace_prefix: str) -> AgentStateBundle | None:
    payload = storage.get_json(state_key(workspace_prefix))
    if not isinstance(payload, dict):
        return None
    return bundle_from_parts(
        revision=int(payload.get("revision") or 0),
        history=payload.get("history") if isinstance(payload.get("history"), dict) else None,
        memory=payload.get("memory") if isinstance(payload.get("memory"), list) else [],
        tasks=payload.get("tasks") if isinstance(payload.get("tasks"), list) else [],
        permissions=payload.get("permissions") if isinstance(payload.get("permissions"), dict) else {},
        active_skills=payload.get("active_skills") if isinstance(payload.get("active_skills"), list) else [],
        last_execution_metadata=payload.get("last_execution_metadata")
        if isinstance(payload.get("last_execution_metadata"), dict)
        else {},
    )


def save_state_to_storage(
    storage: Any,
    workspace_prefix: str,
    bundle: AgentStateBundle,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    key = state_key(workspace_prefix)
    if hasattr(storage, "get_json_with_etag"):
        current_payload, current_etag = storage.get_json_with_etag(key)
    else:
        current_payload, current_etag = storage.get_json(key), None
    current_revision = int((current_payload or {}).get("revision") or 0)
    if expected_revision is not None and current_revision != int(expected_revision):
        raise StateStoreConflict(f"state revision conflict: expected {expected_revision}, got {current_revision}")
    next_bundle = bundle_from_parts(
        revision=current_revision + 1,
        history=bundle.history,
        memory=bundle.memory,
        tasks=bundle.tasks,
        permissions=bundle.permissions,
        active_skills=bundle.active_skills,
        last_execution_metadata=bundle.last_execution_metadata,
    )
    payload: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "revision": next_bundle.revision,
        "history": next_bundle.history,
        "memory": next_bundle.memory,
        "tasks": next_bundle.tasks,
        "permissions": next_bundle.permissions,
        "active_skills": next_bundle.active_skills,
        "last_execution_metadata": next_bundle.last_execution_metadata,
        "state_summary": state_summary(next_bundle),
        "updated_at": utc_now_iso(),
    }
    try:
        if hasattr(storage, "put_json_conditional"):
            storage.put_json_conditional(key, payload, current_etag)
        else:
            storage.put_json(key, payload)
    except ConditionalWriteConflict as exc:
        raise StateStoreConflict(f"state changed while writing revision {next_bundle.revision}") from exc
    return payload
