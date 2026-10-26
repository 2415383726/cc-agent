from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .config import AgentRunConfig
from .history import load_history
from .messages import AgentRunResult
from .state_variable import (
    AgentStateBundle,
    bundle_from_parts,
    decode_agent_state,
    encode_agent_state,
    state_summary,
)
from .workspace import StateStoreConflict, load_state_from_storage, save_state_to_storage, state_key


@dataclass(slots=True)
class StateLoad:
    history_state: Any
    memory: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    permissions: dict[str, Any]
    active_skills: list[dict[str, Any]]
    last_execution_metadata: dict[str, Any]
    loaded_from: str
    previous_revision: int = 0
    storage_error: str | None = None
    state_storage_revision: int = 0

    def to_runtime_dict(self) -> dict[str, Any]:
        return {
            "history_state": self.history_state,
            "memory": self.memory,
            "tasks": self.tasks,
            "permissions": self.permissions,
            "active_skills": self.active_skills,
            "last_execution_metadata": self.last_execution_metadata,
            "loaded_from": self.loaded_from,
            "previous_revision": self.previous_revision,
            "storage_error": self.storage_error,
            "delete_error": None,
            "state_storage_revision": self.state_storage_revision,
        }


class StateBackend(Protocol):
    def load(self) -> StateLoad:
        ...

    def commit(self, result: AgentRunResult, *, expected_revision: int | None = None) -> list[dict[str, Any]]:
        ...


class DifyStateBackend:
    def __init__(self, config: AgentRunConfig, state_id: str):
        self.config = config
        self.state_id = state_id

    def load(self) -> StateLoad:
        if self.config.state_reset:
            return empty_state_load("empty")
        loaded = decode_agent_state(self.config.agent_state_variable)
        if loaded.error:
            state = empty_state_load("error")
            state.storage_error = loaded.error
            return state
        if loaded.record is None:
            return empty_state_load("empty")
        return StateLoad(
            history_state=load_history(loaded.history_payload),
            memory=loaded.memory,
            tasks=loaded.tasks,
            permissions=loaded.permissions,
            active_skills=loaded.active_skills,
            last_execution_metadata=loaded.last_execution_metadata,
            loaded_from="conversation_variable",
            previous_revision=loaded.revision,
            state_storage_revision=0,
        )

    def commit(self, result: AgentRunResult, *, expected_revision: int | None = None) -> list[dict[str, Any]]:
        bundle = bundle_from_result(result, revision=int(expected_revision or 0))
        save_result = encode_agent_state(bundle)
        state_ref = save_result.to_state_ref(conversation_id=self.state_id, loaded_from="conversation_variable")
        result.state_ref = state_ref
        result.emit_inline_state = self.config.emit_inline_state or not save_result.persisted
        result.state_summary = state_summary(
            bundle_from_parts(
                revision=save_result.revision,
                history=bundle.history,
                memory=bundle.memory,
                tasks=bundle.tasks,
                permissions=bundle.permissions,
                active_skills=bundle.active_skills,
                last_execution_metadata=bundle.last_execution_metadata,
            )
        )
        result.encoded_agent_state = save_result.value
        result.encoded_history = save_result.value
        return []


class MinioStateBackend:
    def __init__(self, workspace: Any, state_id: str):
        self.workspace = workspace
        self.state_id = state_id

    def load(self) -> StateLoad:
        if self.workspace is None or getattr(self.workspace, "storage", None) is None:
            return empty_state_load("minio_workspace")
        try:
            stored = load_state_from_storage(self.workspace.storage, self.workspace.scope.workspace_prefix)
        except Exception as exc:
            state = empty_state_load("minio_workspace")
            state.storage_error = str(exc)
            return state
        if stored is None:
            return empty_state_load("minio_workspace")
        return StateLoad(
            history_state=load_history(stored.history),
            memory=stored.memory,
            tasks=stored.tasks,
            permissions=stored.permissions,
            active_skills=stored.active_skills,
            last_execution_metadata=stored.last_execution_metadata,
            loaded_from="minio_workspace",
            previous_revision=int(stored.revision or 0),
            state_storage_revision=int(stored.revision or 0),
        )

    def commit(self, result: AgentRunResult, *, expected_revision: int | None = None) -> list[dict[str, Any]]:
        if self.workspace is None or getattr(self.workspace, "storage", None) is None:
            result.execution_metadata["state_commit_error"] = "workspace storage unavailable"
            result.state_summary = state_summary(bundle_from_result(result, revision=int(expected_revision or 0)))
            return []
        try:
            saved = save_state_to_storage(
                self.workspace.storage,
                self.workspace.scope.workspace_prefix,
                bundle_from_result(result, revision=0),
                expected_revision=expected_revision,
            )
        except StateStoreConflict:
            raise
        revision = int(saved.get("revision") or (expected_revision or 0))
        result.state_summary = saved.get("state_summary") or state_summary(bundle_from_result(result, revision=revision))
        result.state_ref = {
            "state_id": self.state_id,
            "conversation_id": self.state_id,
            "storage_key": state_key(self.workspace.scope.workspace_prefix),
            "backend": "minio",
            "revision": revision,
            "persisted": True,
            "storage_error": None,
            "storage_version": 1,
        }
        result.emit_inline_state = False
        result.encoded_agent_state = ""
        result.encoded_history = ""
        return []


def empty_state_load(loaded_from: str = "temporary") -> StateLoad:
    return StateLoad(
        history_state=load_history(None),
        memory=[],
        tasks=[],
        permissions={},
        active_skills=[],
        last_execution_metadata={},
        loaded_from=loaded_from,
    )


def bundle_from_result(result: AgentRunResult, revision: int = 0) -> AgentStateBundle:
    return bundle_from_parts(
        revision=revision,
        history={
            "messages": result.history,
            "summary": result.summary or "",
            "version": result.history_schema_version,
        },
        memory=result.memory,
        tasks=result.tasks,
        permissions=result.permissions,
        active_skills=result.active_skills,
        last_execution_metadata=result.execution_metadata,
    )
