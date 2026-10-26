from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .internal_events import InternalEvent
    from .model_stream import TextDelta, ThinkingDelta


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""

    def to_history(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }
        if self.raw_arguments:
            payload["raw_arguments"] = self.raw_arguments
        return payload


@dataclass(slots=True)
class AssistantTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""
    raw_message: Any | None = None
    stream_chunks: list["TextDelta | ThinkingDelta"] = field(default_factory=list)
    reasoning_content: str = ""


@dataclass(slots=True)
class ToolResult:
    tool_call_id: str
    tool_name: str
    llm_observation: str
    display_messages: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_error: bool = False
    synthetic: bool = False

    def to_history(self) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": self.tool_name,
            "content": self.llm_observation or "(tool completed with no output)",
            "metadata": {
                key: value
                for key, value in self.metadata.items()
                if key not in {"display_messages", "raw_response", "artifacts", "parameters"}
            },
            "is_error": self.is_error,
            "synthetic": self.synthetic,
        }


@dataclass(slots=True)
class AgentState:
    history: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    history_version: int = 1
    dify_memory: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    memory: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    active_skills: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class AgentRunResult:
    answer: str
    history: list[dict[str, Any]]
    memory: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    execution_metadata: dict[str, Any]
    permissions: dict[str, Any] = field(default_factory=dict)
    active_skills: list[dict[str, Any]] = field(default_factory=list)
    events: list["InternalEvent"] = field(default_factory=list)
    summary: str = ""
    history_schema_version: int = 1
    state_ref: dict[str, Any] | None = None
    emit_inline_state: bool = True
    encoded_history: str = ""
    encoded_agent_state: str = ""
    state_summary: dict[str, Any] = field(default_factory=dict)

    def to_output_payload(self) -> dict[str, Any]:
        """Minimal payload for Dify agent structured output."""
        payload = {
            "event": "agent_finished",
            "answer": self.answer,
            "execution_metadata": self.execution_metadata,
        }
        encoded = self.encoded_agent_state or self.encoded_history
        if encoded:
            payload["agent_state"] = encoded
        if self.state_summary:
            payload["state_summary"] = self.state_summary
        if self.state_ref is not None:
            payload["state_ref"] = self.state_ref
        return payload

    def to_json_payload(self) -> dict[str, Any]:
        payload = {
            "event": "agent_finished",
            "answer": self.answer,
            "execution_metadata": self.execution_metadata,
        }
        encoded = self.encoded_agent_state or self.encoded_history
        if encoded:
            payload["agent_state"] = encoded
        if self.state_summary:
            payload["state_summary"] = self.state_summary
        if self.state_ref is not None:
            payload["state_ref"] = self.state_ref
        if not encoded and self.emit_inline_state:
            payload.update(
                {
                    "history_schema_version": self.history_schema_version,
                    "history": self.history,
                    "history_payload": {
                        "messages": self.history,
                        "summary": self.summary or "",
                        "version": self.history_schema_version,
                    },
                    "memory": self.memory,
                    "tasks": self.tasks,
                    "permissions": self.permissions,
                }
            )
        return payload


def assistant_message(turn: AssistantTurn) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": turn.text or "",
    }
    if turn.tool_calls:
        message["tool_calls"] = [tool_call.to_history() for tool_call in turn.tool_calls]
    if turn.usage:
        message["usage"] = turn.usage
    if turn.finish_reason:
        message["finish_reason"] = turn.finish_reason
    # reasoning_content is streamed to the frontend as reasoning_delta events
    # during the current turn and must NOT enter the transcript.  If saved,
    # to_dify_prompt_messages(preserve_reasoning_content=True) on the next
    # iteration produces a raw dict that crashes the Dify SDK and triggers the
    # DeepSeek thinking compat fallback, which flattens tool history into
    # visible "Assistant requested tool calls:" text in the frontend.
    return message


def tool_message(result: ToolResult) -> dict[str, Any]:
    return result.to_history()
