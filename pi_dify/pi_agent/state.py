"""Authoritative cross-turn Pi state stored in the Dify ``agent_state`` variable.

The bundle owns the Pi session entries/leaf, active skills, session grants,
pending interaction, consumption records and run statistics. It is the only
cross-turn source of truth; browser caches are drafts and local files are not a
second store.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pi_agent_harness.session.memory_storage import MemorySessionStorage
from pi_agent_harness.session.session import build_session_context
from pi_agent_harness.types import SessionMetadata, SessionTreeEntry, SessionTreeEntryAdapter

from .errors import StateError

STATE_PREFIX = "piagent-state:v1:gzip-base64:"
SCHEMA_VERSION = 1
DEFAULT_MAX_ENCODED_BYTES = 190_000
TARGET_ENCODED_BYTES = 170_000
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
MAX_CONSUMED_RECORDS = 40


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class PiState:
    revision: int = 0
    session_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    run_id: str = ""
    entries: list[dict[str, Any]] = field(default_factory=list)
    leaf_id: str | None = None
    active_skills: list[dict[str, Any]] = field(default_factory=list)
    grants: list[dict[str, Any]] = field(default_factory=list)
    pending: dict[str, Any] | None = None
    consumed: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    last_answer: str = ""
    last_status: str = "completed"

    @classmethod
    def fresh(cls, session_id: str) -> PiState:
        stamp = now_iso()
        return cls(session_id=session_id, created_at=stamp, updated_at=stamp)


@dataclass(slots=True)
class StateLoadResult:
    state: PiState | None = None
    error: str | None = None
    encoded_bytes: int = 0
    payload_bytes: int = 0
    compacted: bool = False


@dataclass(slots=True)
class StateSaveResult:
    value: str = ""
    revision: int = 0
    persisted: bool = False
    error: str | None = None
    encoded_bytes: int = 0
    payload_bytes: int = 0
    compacted: bool = False
    summary: dict[str, Any] = field(default_factory=dict)


def decode_state(value: Any) -> StateLoadResult:
    text = str(value or "").strip()
    if not text:
        return StateLoadResult()
    if not text.startswith(STATE_PREFIX):
        return StateLoadResult(error="Invalid agent_state: unsupported prefix")
    encoded = text[len(STATE_PREFIX) :]
    try:
        raw_compressed = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return StateLoadResult(error="Invalid agent_state: malformed base64")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw_compressed)) as handle:
            raw = handle.read(MAX_PAYLOAD_BYTES + 1)
    except (OSError, EOFError):
        return StateLoadResult(error="Invalid agent_state: malformed gzip payload")
    if len(raw) > MAX_PAYLOAD_BYTES:
        return StateLoadResult(error="Invalid agent_state: payload exceeds the size limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return StateLoadResult(error="Invalid agent_state: malformed JSON payload")
    if not isinstance(payload, dict):
        return StateLoadResult(error="Invalid agent_state: expected an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        version = payload.get("schema_version")
        return StateLoadResult(error=f"Invalid agent_state: unsupported schema version {version!r}")
    try:
        state = _state_from_payload(payload)
        validate_state(state)
    except StateError as exc:
        return StateLoadResult(error=exc.message)
    return StateLoadResult(
        state=state, encoded_bytes=len(text.encode("utf-8")), payload_bytes=len(raw)
    )


def _state_from_payload(payload: dict[str, Any]) -> PiState:
    entries = payload.get("entries")
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise StateError("agent_state entries must be a list of objects.")
    skills = payload.get("active_skills")
    grants = payload.get("grants")
    consumed = payload.get("consumed")
    stats = payload.get("stats")
    pending = payload.get("pending")
    if pending is not None and not isinstance(pending, dict):
        raise StateError("agent_state pending must be an object or null.")
    return PiState(
        revision=_int(payload.get("revision")),
        session_id=str(payload.get("session_id") or ""),
        created_at=str(payload.get("created_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
        run_id=str(payload.get("run_id") or ""),
        entries=entries,
        leaf_id=payload.get("leaf_id") if isinstance(payload.get("leaf_id"), str) else None,
        active_skills=[item for item in skills or [] if isinstance(item, dict)],
        grants=[item for item in grants or [] if isinstance(item, dict)],
        pending=pending,
        consumed=[item for item in consumed or [] if isinstance(item, dict)][
            -MAX_CONSUMED_RECORDS:
        ],
        stats=stats if isinstance(stats, dict) else {},
        last_answer=str(payload.get("last_answer") or ""),
        last_status=str(payload.get("last_status") or "completed"),
    )


def validate_state(state: PiState) -> None:
    """Reject corrupt trees, orphan references and unpaired tool calls."""

    by_id: dict[str, SessionTreeEntry] = {}
    parsed: list[SessionTreeEntry] = []
    for raw in state.entries:
        try:
            entry = SessionTreeEntryAdapter.validate_python(raw)
        except Exception:
            raise StateError("agent_state contains an invalid session entry.") from None
        if entry.id in by_id:
            raise StateError("agent_state contains duplicate session entry ids.")
        parsed.append(entry)
        by_id[entry.id] = entry
    if state.leaf_id is not None and state.leaf_id not in by_id:
        raise StateError("agent_state leaf does not exist.")
    for entry in parsed:
        if entry.parentId is not None and entry.parentId not in by_id:
            raise StateError("agent_state contains a dangling parent reference.")
    _validate_branch(by_id, state.leaf_id)
    _validate_tool_pairs(_path(parsed, by_id, state.leaf_id))


def _validate_branch(by_id: dict[str, SessionTreeEntry], leaf_id: str | None) -> None:
    if leaf_id is None:
        if by_id:
            raise StateError("agent_state has entries but no leaf.")
        return
    seen: set[str] = set()
    current = by_id[leaf_id]
    while True:
        if current.id in seen:
            raise StateError("agent_state contains a session cycle.")
        seen.add(current.id)
        if current.parentId is None:
            break
        current = by_id[current.parentId]


def _path(
    entries: list[SessionTreeEntry], by_id: dict[str, SessionTreeEntry], leaf_id: str | None
) -> list[SessionTreeEntry]:
    if leaf_id is None:
        return []
    path: list[SessionTreeEntry] = []
    current = by_id[leaf_id]
    while True:
        path.append(current)
        if current.parentId is None:
            break
        current = by_id[current.parentId]
    path.reverse()
    return path


def _validate_tool_pairs(path: list[SessionTreeEntry]) -> None:
    known_calls: set[str] = set()
    results: set[str] = set()
    for entry in path:
        if entry.type != "message":
            continue
        message = entry.message
        role = message.get("role")
        if role == "assistant":
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "toolCall":
                    call_id = str(block.get("id") or "")
                    if call_id:
                        known_calls.add(call_id)
        elif role == "toolResult":
            call_id = str(message.get("toolCallId") or "")
            if call_id:
                results.add(call_id)
    missing = known_calls - results
    if missing:
        raise StateError("agent_state contains assistant tool calls without results.")


def encode_state(
    state: PiState,
    *,
    max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
    target_encoded_bytes: int = TARGET_ENCODED_BYTES,
) -> StateSaveResult:
    state.updated_at = now_iso()
    state.entries = sanitize_entries(state.entries, state.leaf_id, state.pending)
    if state.entries:
        last = state.entries[-1]
        details = (last.get("message") or {}).get("details")
        if isinstance(details, dict) and details.get("synthetic"):
            state.leaf_id = last.get("id")
    _refresh_leaf(state)
    compacted = False

    def build() -> bytes:
        payload = _payload(state)
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
        compressed = gzip.compress(raw, mtime=0)
        return base64.b64encode(compressed)

    encoded = build()
    if len(encoded) > max_encoded_bytes:
        state.entries = _trim_entries(state, target_encoded_bytes, max_encoded_bytes)
        compacted = True
        encoded = build()
    if len(encoded) > max_encoded_bytes:
        # Last resort: drop old tool result bodies while preserving pairing/ids.
        state.entries = _shrink_entry_bodies(state.entries, target_encoded_bytes // 2)
        compacted = True
        encoded = build()
    if len(encoded) > max_encoded_bytes:
        return StateSaveResult(
            revision=state.revision,
            persisted=False,
            error="state_too_large",
            encoded_bytes=len(encoded),
            summary=state_summary(state),
        )
    value = STATE_PREFIX + encoded.decode("ascii")
    return StateSaveResult(
        value=value,
        revision=state.revision,
        persisted=True,
        encoded_bytes=len(encoded),
        payload_bytes=len(gzip.decompress(base64.b64decode(encoded))),
        compacted=compacted,
        summary=state_summary(state),
    )


def _payload(state: PiState) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": state.revision,
        "session_id": state.session_id,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "run_id": state.run_id,
        "entries": state.entries,
        "leaf_id": state.leaf_id,
        "active_skills": state.active_skills[-20:],
        "grants": state.grants[-50:],
        "pending": state.pending,
        "consumed": state.consumed[-MAX_CONSUMED_RECORDS:],
        "stats": state.stats,
        "last_answer": state.last_answer,
        "last_status": state.last_status,
    }


def sanitize_entries(
    entries: list[dict[str, Any]], leaf_id: str | None, pending: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Drop failed assistant messages and synthesize missing tool results."""

    parsed: list[SessionTreeEntry] = []
    for raw in entries:
        try:
            parsed.append(SessionTreeEntryAdapter.validate_python(raw))
        except Exception:
            continue
    cleaned: list[dict[str, Any]] = []
    for entry in parsed:
        if entry.type == "message":
            message = entry.message
            if message.get("role") == "assistant" and message.get("stopReason") in {
                "error",
                "aborted",
            }:
                has_calls = any(
                    isinstance(block, dict) and block.get("type") == "toolCall"
                    for block in message.get("content") or []
                )
                if not has_calls:
                    continue
        cleaned.append(entry.model_dump(mode="json"))

    # Rebuild a single valid chain and append synthetic results for unfinished calls.
    by_id = {item["id"]: item for item in cleaned}
    ordered: list[dict[str, Any]] = []
    for item in cleaned:
        parent = item.get("parentId")
        if parent is not None and parent not in {entry["id"] for entry in ordered}:
            item = dict(item)
            item["parentId"] = ordered[-1]["id"] if ordered else None
        ordered.append(item)
    if not ordered:
        return ordered
    leaf = leaf_id if leaf_id in by_id else ordered[-1]["id"]
    path = _path(
        [SessionTreeEntryAdapter.validate_python(item) for item in ordered],
        {item["id"]: SessionTreeEntryAdapter.validate_python(item) for item in ordered},
        leaf,
    )
    known_calls: dict[str, str] = {}
    results: set[str] = set()
    for entry in path:
        if entry.type != "message":
            continue
        message = entry.message
        if message.get("role") == "assistant":
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "toolCall":
                    known_calls[str(block.get("id") or "")] = str(block.get("name") or "")
        elif message.get("role") == "toolResult":
            results.add(str(message.get("toolCallId") or ""))
    missing = [call_id for call_id in known_calls if call_id and call_id not in results]
    if missing:
        from pi_agent_core.messages import ToolResultMessage

        for call_id in missing:
            pending_note = (
                "Execution was not completed because the run was interrupted. "
                "Verify the external outcome before retrying."
            )
            result = ToolResultMessage(
                toolCallId=call_id,
                toolName=known_calls.get(call_id) or "unknown_tool",
                content=[{"type": "text", "text": pending_note}],
                details={"execution_outcome": "unknown", "synthetic": True},
                isError=True,
            )
            entry_id = f"synth_{call_id[:24]}"
            if entry_id in by_id:
                entry_id = f"synth_{call_id[-24:]}"
            ordered.append(
                {
                    "type": "message",
                    "id": entry_id,
                    "parentId": ordered[-1]["id"],
                    "timestamp": now_iso(),
                    "message": result.model_dump(mode="json"),
                }
            )
            by_id[entry_id] = ordered[-1]
    return ordered


def _refresh_leaf(state: PiState) -> None:
    if not state.entries:
        state.leaf_id = None
        return
    ids = {entry["id"] for entry in state.entries}
    if state.leaf_id not in ids:
        state.leaf_id = state.entries[-1]["id"]


def _trim_entries(
    state: PiState, target_encoded_bytes: int, max_encoded_bytes: int
) -> list[dict[str, Any]]:
    groups = _entry_groups(state.entries)
    if len(groups) <= 2:
        return state.entries
    pending_call = str((state.pending or {}).get("tool_call_id") or "")

    def candidate_size(candidate: list[dict[str, Any]]) -> int:
        clone = PiState(
            revision=state.revision,
            session_id=state.session_id,
            created_at=state.created_at,
            updated_at=state.updated_at,
            run_id=state.run_id,
            entries=candidate,
            leaf_id=state.leaf_id,
            active_skills=state.active_skills,
            grants=state.grants,
            pending=state.pending,
            consumed=state.consumed,
            stats=state.stats,
            last_answer=state.last_answer,
            last_status=state.last_status,
        )
        raw = json.dumps(_payload(clone), ensure_ascii=False, separators=(",", ":"), default=str)
        return len(base64.b64encode(gzip.compress(raw.encode("utf-8"), mtime=0)))

    pending_group = -1
    if pending_call:
        pending_group = next(
            (
                index
                for index, group in enumerate(groups)
                if _group_contains_call(group, pending_call)
            ),
            -1,
        )
    built = state.entries
    for drop_count in range(1, len(groups) - 1):
        if pending_group >= 0 and drop_count > pending_group:
            break
        omitted = [entry for group in groups[:drop_count] for entry in group]
        kept = [entry for group in groups[drop_count:] for entry in group]
        if not kept:
            break
        first = dict(kept[0])
        compaction = {
            "type": "compaction",
            "id": f"trim_{state.revision + 1}_{len(omitted)}",
            "parentId": None,
            "timestamp": now_iso(),
            "summary": _storage_summary(omitted),
            "firstKeptEntryId": first["id"],
            "tokensBefore": _estimate_chars(omitted),
            "details": {"storage_trim": True, "omitted_entries": len(omitted)},
        }
        first["parentId"] = compaction["id"]
        kept[0] = first
        _repair_chain(kept)
        candidate = [compaction, *kept]
        built = candidate
        if candidate_size(candidate) <= target_encoded_bytes:
            return candidate
    return built


def _entry_groups(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for entry in entries:
        role = None
        if entry.get("type") == "message":
            role = (entry.get("message") or {}).get("role")
        if role == "user" and current:
            groups.append(current)
            current = []
        current.append(entry)
    if current:
        groups.append(current)
    return groups or [[]]


def _group_contains_call(group: list[dict[str, Any]], call_id: str) -> bool:
    for entry in group:
        if entry.get("type") != "message":
            continue
        message = entry.get("message") or {}
        if message.get("role") == "assistant":
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("id") == call_id:
                    return True
        if message.get("role") == "toolResult" and message.get("toolCallId") == call_id:
            return True
    return False


def _storage_summary(entries: list[dict[str, Any]]) -> str:
    parts = ["Earlier conversation history was trimmed to fit Dify's state size limit."]
    for entry in entries:
        if entry.get("type") != "message":
            continue
        message = entry.get("message") or {}
        role = message.get("role")
        if role == "user":
            text = _message_text(message)
            if text:
                parts.append(f"User: {_squash(text, 160)}")
        elif role == "assistant":
            text = _message_text(message)
            if text:
                parts.append(f"Assistant: {_squash(text, 160)}")
    return "\n".join(parts[-40:])[:4_000]


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _squash(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _repair_chain(entries: list[dict[str, Any]]) -> None:
    previous: str | None = None
    for entry in entries:
        entry["parentId"] = previous
        previous = entry["id"]


def _shrink_entry_bodies(entries: list[dict[str, Any]], target_bytes: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    budget = max(64_000, target_bytes)
    used = 0
    for entry in reversed(entries):
        encoded = len(json.dumps(entry, ensure_ascii=False, default=str).encode("utf-8"))
        if used + encoded <= budget or entry.get("type") != "message":
            result.append(entry)
            used += encoded
            continue
        message = dict(entry.get("message") or {})
        role = message.get("role")
        if role == "toolResult":
            content = message.get("content")
            if isinstance(content, list):
                message["content"] = [
                    {
                        **block,
                        "text": (
                            _squash(str(block.get("text") or ""), 2_000)
                            if isinstance(block, dict) and block.get("type") == "text"
                            else block
                        ),
                    }
                    for block in content
                ]
            message["details"] = {"trimmed": True}
        elif role == "assistant":
            message["content"] = [
                {
                    **block,
                    "text": (
                        _squash(str(block.get("text") or ""), 2_000)
                        if isinstance(block, dict) and block.get("type") == "text"
                        else block
                    ),
                }
                for block in message.get("content") or []
            ]
        shrunk = dict(entry)
        shrunk["message"] = message
        result.append(shrunk)
        used += len(json.dumps(shrunk, ensure_ascii=False, default=str).encode("utf-8"))
    result.reverse()
    return result


def _estimate_chars(entries: list[dict[str, Any]]) -> int:
    return sum(len(json.dumps(entry, ensure_ascii=False, default=str)) for entry in entries) // 4


def build_storage(state: PiState) -> MemorySessionStorage:
    metadata = SessionMetadata(
        id=state.session_id or "pi-dify-session", createdAt=state.created_at or now_iso()
    )
    entries = [SessionTreeEntryAdapter.validate_python(item) for item in state.entries]
    return MemorySessionStorage(metadata, entries, state.leaf_id)


async def export_session(session: Any) -> tuple[list[dict[str, Any]], str | None, str]:
    metadata = await session.get_metadata()
    entries = await session.get_entries()
    leaf = await session.get_leaf_id()
    return ([entry.model_dump(mode="json") for entry in entries], leaf, metadata.createdAt)


def session_messages(state: PiState) -> list[Any]:
    if not state.entries:
        return []
    try:
        storage_entries = [SessionTreeEntryAdapter.validate_python(item) for item in state.entries]
    except Exception:
        return []
    by_id = {entry.id: entry for entry in storage_entries}
    return build_session_context(_path(storage_entries, by_id, state.leaf_id)).messages


def state_summary(state: PiState) -> dict[str, Any]:
    """Read-only description of the actually-encoded snapshot."""

    return {
        "revision": state.revision,
        "run_id": state.run_id,
        "session_id": state.session_id,
        "entry_count": len(state.entries),
        "leaf_id": state.leaf_id,
        "active_skills": [item.get("name") for item in state.active_skills],
        "pending": (state.pending or {}).get("kind"),
        "grants": len(state.grants),
        "last_status": state.last_status,
    }


def prune_consumed(state: PiState) -> None:
    state.consumed = state.consumed[-MAX_CONSUMED_RECORDS:]


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
