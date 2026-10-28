from __future__ import annotations

import base64
import gzip
import json
from dataclasses import dataclass, field
from typing import Any

from .context_budget import snip_old_tool_results, summarize_messages
from .history import sanitize_history
from .interrupts import pending_tool_call_id

AGENT_STATE_PREFIX = "ccagent-state:v1:gzip-base64:"
SCHEMA_VERSION = 1
DEFAULT_HISTORY_PAYLOAD = {"messages": [], "summary": "", "version": 1}
DEFAULT_MAX_ENCODED_BYTES = 190_000
DEFAULT_TARGET_ENCODED_BYTES = 160_000


@dataclass(slots=True)
class AgentStateBundle:
    revision: int = 0
    history: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_HISTORY_PAYLOAD))
    tasks: list[dict[str, Any]] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    active_skills: list[dict[str, Any]] = field(default_factory=list)
    last_execution_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentStateLoadResult:
    bundle: AgentStateBundle = field(default_factory=AgentStateBundle)
    record: dict[str, Any] | None = field(default_factory=dict)
    error: str | None = None

    @property
    def revision(self) -> int:
        return self.bundle.revision

    @property
    def history_payload(self) -> dict[str, Any]:
        return self.bundle.history

    @property
    def tasks(self) -> list[dict[str, Any]]:
        return self.bundle.tasks

    @property
    def permissions(self) -> dict[str, Any]:
        return self.bundle.permissions

    @property
    def active_skills(self) -> list[dict[str, Any]]:
        return self.bundle.active_skills

    @property
    def last_execution_metadata(self) -> dict[str, Any]:
        return self.bundle.last_execution_metadata


@dataclass(slots=True)
class AgentStateSaveResult:
    value: str
    revision: int
    persisted: bool
    error: str | None = None
    warning: str | None = None
    payload_bytes: int = 0
    encoded_bytes: int = 0
    compacted: bool = False
    storage_version: int = SCHEMA_VERSION

    def to_state_ref(self, *, conversation_id: str, loaded_from: str) -> dict[str, Any]:
        payload = {
            "state_id": conversation_id,
            "conversation_id": conversation_id,
            "storage_key": "",
            "backend": "conversation_variable",
            "variable_name": "agent_state",
            "revision": self.revision,
            "loaded_from": loaded_from,
            "persisted": self.persisted,
            "delivery_status": "encoded" if self.persisted else "failed",
            "platform_persisted": None,
            "storage_error": self.error,
            "storage_version": self.storage_version,
            "payload_bytes": self.payload_bytes,
            "encoded_bytes": self.encoded_bytes,
            "compacted": self.compacted,
        }
        if self.warning:
            payload["storage_warning"] = self.warning
        return payload


def decode_agent_state(value: Any) -> AgentStateLoadResult:
    text = str(value or "").strip()
    if not text:
        return AgentStateLoadResult(record=None)
    if not text.startswith(AGENT_STATE_PREFIX):
        return AgentStateLoadResult(record=None, error="Invalid agent_state: unsupported prefix")
    try:
        encoded = text[len(AGENT_STATE_PREFIX) :]
        raw = gzip.decompress(base64.b64decode(encoded.encode("ascii"), validate=True))
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("expected object payload")
        if _positive_int(payload.get("schema_version"), 0) != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {payload.get('schema_version')}")
        history_candidate = payload.get("history")
        history_source = history_candidate if isinstance(history_candidate, dict) else payload
        permissions = payload.get("permissions")
        execution_metadata = payload.get("last_execution_metadata")
        history_payload = {
            "messages": sanitize_history(
                _dict_list(
                    history_source.get("messages")
                    if "messages" in history_source
                    else payload.get("recent_history")
                )
            ),
            "summary": str(
                history_source.get("summary")
                if "summary" in history_source
                else payload.get("summary") or ""
            ),
            "version": _positive_int(
                (
                    history_source.get("version")
                    if "version" in history_source
                    else payload.get("history_version")
                ),
                1,
            )
            or 1,
        }
        return AgentStateLoadResult(
            bundle=AgentStateBundle(
                revision=_positive_int(payload.get("revision"), 0),
                history=history_payload,
                tasks=_dict_list(payload.get("tasks")),
                permissions=permissions if isinstance(permissions, dict) else {},
                active_skills=_dict_list(payload.get("active_skills")),
                last_execution_metadata=(
                    execution_metadata if isinstance(execution_metadata, dict) else {}
                ),
            ),
            record=payload,
        )
    except Exception as exc:
        return AgentStateLoadResult(record=None, error=f"Invalid agent_state: {exc}")


def encode_agent_state(
    bundle: AgentStateBundle | None = None,
    *,
    previous_revision: int | None = None,
    history: dict[str, Any] | None = None,
    history_payload: dict[str, Any] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    permissions: dict[str, Any] | None = None,
    last_execution_metadata: dict[str, Any] | None = None,
    active_skills: list[dict[str, Any]] | None = None,
    max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
) -> AgentStateSaveResult:
    if bundle is not None:
        previous_revision = bundle.revision
        history = bundle.history
        tasks = bundle.tasks
        permissions = bundle.permissions
        active_skills = bundle.active_skills
        last_execution_metadata = bundle.last_execution_metadata
    revision = _positive_int(previous_revision, 0) + 1
    normalized_history = _normalize_history_payload(
        history if history is not None else history_payload
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "revision": revision,
        "history": {
            "messages": normalized_history.get("messages", []),
            "summary": normalized_history.get("summary", ""),
            "version": normalized_history.get("version", 1),
        },
        "summary": normalized_history.get("summary", ""),
        "history_version": normalized_history.get("version", 1),
        "recent_history": normalized_history.get("messages", []),
        "tasks": _dict_list(tasks or []),
        "permissions": permissions if isinstance(permissions, dict) else {},
        "active_skills": _compact_active_skills(active_skills),
        "last_execution_metadata": (
            last_execution_metadata if isinstance(last_execution_metadata, dict) else {}
        ),
    }
    max_encoded_bytes = max(1024, int(max_encoded_bytes or DEFAULT_MAX_ENCODED_BYTES))
    payload, compacted, warning = _compact_to_fit(payload, max_encoded_bytes)
    payload["history"] = {
        "messages": payload.get("recent_history", []),
        "summary": payload.get("summary", ""),
        "version": payload.get("history_version", 1),
    }
    try:
        encoded = _encode_payload(payload)
    except Exception as exc:
        return AgentStateSaveResult(
            value="",
            revision=revision,
            persisted=False,
            error=f"Invalid agent_state payload: {exc}",
        )
    payload_bytes = len(_json_bytes(payload))
    encoded_bytes = len(encoded.encode("utf-8"))
    if payload_bytes > max_encoded_bytes or encoded_bytes > max_encoded_bytes:
        return AgentStateSaveResult(
            value="",
            revision=revision,
            persisted=False,
            error="agent_state_exceeds_variable_limit",
            warning=warning,
            payload_bytes=payload_bytes,
            encoded_bytes=encoded_bytes,
            compacted=compacted,
        )
    return AgentStateSaveResult(
        value=encoded,
        revision=revision,
        persisted=bool(encoded),
        warning=warning,
        payload_bytes=payload_bytes,
        encoded_bytes=encoded_bytes,
        compacted=compacted,
    )


def state_summary(bundle: AgentStateBundle) -> dict[str, Any]:
    history = _normalize_history_payload(bundle.history)
    permissions = bundle.permissions if isinstance(bundle.permissions, dict) else {}
    allowed_candidate = permissions.get("allowed_tools")
    allowed_tools = allowed_candidate if isinstance(allowed_candidate, dict) else {}
    return {
        "revision": _positive_int(bundle.revision, 0),
        "history_message_count": len(history.get("messages") or []),
        "summary_present": bool(str(history.get("summary") or "").strip()),
        "task_count": len(_dict_list(bundle.tasks)),
        "permission_tool_count": len(allowed_tools),
        "active_skill_names": _active_skill_names(bundle.active_skills),
        "last_finish_reason": str(
            (bundle.last_execution_metadata or {}).get("finish_reason") or ""
        ),
        "awaiting_user": (bundle.last_execution_metadata or {}).get("finish_reason")
        == "awaiting_user",
    }


def bundle_from_parts(
    *,
    revision: int = 0,
    history: dict[str, Any] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    permissions: dict[str, Any] | None = None,
    active_skills: list[dict[str, Any]] | None = None,
    last_execution_metadata: dict[str, Any] | None = None,
) -> AgentStateBundle:
    return AgentStateBundle(
        revision=_positive_int(revision, 0),
        history=_normalize_history_payload(history),
        tasks=_dict_list(tasks or []),
        permissions=permissions if isinstance(permissions, dict) else {},
        active_skills=_compact_active_skills(active_skills),
        last_execution_metadata=(
            last_execution_metadata if isinstance(last_execution_metadata, dict) else {}
        ),
    )


def decode_history_variable(value: Any) -> AgentStateLoadResult:
    return decode_agent_state(value)


def encode_history_variable(
    *,
    previous_revision: int,
    history_payload: dict[str, Any],
    tasks: list[dict[str, Any]],
    permissions: dict[str, Any] | None,
    last_execution_metadata: dict[str, Any],
    active_skills: list[dict[str, Any]] | None = None,
    max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
) -> AgentStateSaveResult:
    return encode_agent_state(
        previous_revision=previous_revision,
        history=history_payload,
        tasks=tasks,
        permissions=permissions,
        last_execution_metadata=last_execution_metadata,
        active_skills=active_skills,
        max_encoded_bytes=max_encoded_bytes,
    )


HISTORY_VARIABLE_PREFIX = AGENT_STATE_PREFIX
HistoryVariableLoadResult = AgentStateLoadResult
HistoryVariableSaveResult = AgentStateSaveResult


def _compact_to_fit(
    payload: dict[str, Any], max_encoded_bytes: int
) -> tuple[dict[str, Any], bool, str | None]:
    compacted = False
    warning: str | None = None
    payload = dict(payload)
    payload["recent_history"] = sanitize_history(list(payload.get("recent_history") or []))

    if _fits(payload, max_encoded_bytes):
        return payload, False, None

    compacted = True
    history = list(payload["recent_history"])
    pending_start = _pending_start_index(history, payload.get("last_execution_metadata"))
    while history and not _fits({**payload, "recent_history": history}, max_encoded_bytes):
        removable_limit = pending_start if pending_start is not None else max(0, len(history) - 6)
        if removable_limit <= 0:
            break
        remove_count = max(1, removable_limit // 2)
        removed = history[:remove_count]
        history = sanitize_history(history[remove_count:])
        pending_start = None if pending_start is None else max(0, pending_start - remove_count)
        payload["summary"] = _merge_summary(
            payload.get("summary"), summarize_messages(removed), max_encoded_bytes
        )

    snip_old_tool_results(history, max_chars=800, preserve_last_n_messages=4)
    payload["recent_history"] = sanitize_history(history)
    payload["summary"] = _trim_text(
        str(payload.get("summary") or ""), max(1000, max_encoded_bytes // 3)
    )

    if not _fits(payload, max_encoded_bytes):
        payload["recent_history"] = _minimal_history(
            payload["recent_history"], payload.get("last_execution_metadata")
        )
        payload["summary"] = _trim_text(
            str(payload.get("summary") or ""), max(500, max_encoded_bytes // 4)
        )
        warning = "state_compacted_to_fit_variable_limit"

    if not _fits(payload, max_encoded_bytes) and pending_start is None:
        payload["summary"] = _trim_text(
            _merge_summary(
                payload.get("summary"),
                summarize_messages(payload["recent_history"]),
                max_encoded_bytes,
            ),
            max_encoded_bytes // 4,
        )
        payload["recent_history"] = []
        payload["active_skills"] = []

    if not _fits(payload, max_encoded_bytes):
        payload["tasks"] = []
        payload["active_skills"] = _compact_active_skills(
            payload.get("active_skills"), max_items=3, max_summary_chars=1000
        )
        warning = "state_compacted_to_minimal_variable_limit"

    return payload, compacted, warning


def _fits(payload: dict[str, Any], max_encoded_bytes: int) -> bool:
    raw_size = len(_json_bytes(payload))
    encoded_size = len(_encode_payload(payload).encode("utf-8"))
    return raw_size <= max_encoded_bytes and encoded_size <= max_encoded_bytes


def _encode_payload(payload: dict[str, Any]) -> str:
    compressed = gzip.compress(_json_bytes(payload), compresslevel=9)
    encoded = base64.b64encode(compressed).decode("ascii")
    return AGENT_STATE_PREFIX + encoded


def _json_bytes(payload: dict[str, Any]) -> bytes:
    if "recent_history" in payload:
        payload = {
            **payload,
            "history": {
                "messages": payload.get("recent_history", []),
                "summary": payload.get("summary", ""),
                "version": payload.get("history_version", 1),
            },
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _normalize_history_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = dict(DEFAULT_HISTORY_PAYLOAD)
    messages = value.get("messages")
    if messages is None:
        messages = value.get("history", [])
    if not isinstance(messages, list):
        messages = []
    return {
        "messages": sanitize_history(
            [message for message in messages if isinstance(message, dict)]
        ),
        "summary": str(value.get("summary") or value.get("conversation_summary") or ""),
        "version": _positive_int(value.get("version"), 1) or 1,
    }


def _pending_start_index(history: list[dict[str, Any]], metadata: Any) -> int | None:
    tool_call_id = pending_tool_call_id(metadata)
    if not tool_call_id:
        return None
    for index, message in enumerate(history):
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            if isinstance(tool_call, dict) and str(tool_call.get("id") or "") == tool_call_id:
                return index
    return None


def _minimal_history(history: list[dict[str, Any]], metadata: Any) -> list[dict[str, Any]]:
    start = _pending_start_index(history, metadata)
    if start is not None:
        return sanitize_history(history[start:])
    return sanitize_history(history[-4:])


def _merge_summary(existing: Any, addition: Any, max_encoded_bytes: int) -> str:
    existing_text = str(existing or "").strip()
    addition_text = str(addition or "").strip()
    if not addition_text:
        return existing_text
    merged = f"{existing_text}\n\n{addition_text}" if existing_text else addition_text
    return _trim_text(merged, max(1000, max_encoded_bytes // 3))


def _trim_text(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _compact_active_skills(
    value: Any, *, max_items: int = 8, max_summary_chars: int = 5000
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or "").strip()
        if not name:
            continue
        record: dict[str, Any] = {
            "name": name,
            "summary": _trim_text(
                str(item.get("summary") or item.get("description") or ""), max_summary_chars
            ),
        }
        if "definition_hash" in item:
            record["definition_hash"] = str(item["definition_hash"])
            record["complete"] = (
                item.get("complete") is True
                and len(str(item.get("summary") or "")) <= max_summary_chars
            )
        if item.get("last_used"):
            record["last_used"] = str(item.get("last_used"))
        result.append(record)
    return result[-max_items:]


def _active_skill_names(value: Any) -> list[str]:
    names: list[str] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or "").strip()
        if name:
            names.append(name)
    return names


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default
