from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .internal_events import InternalEvent
    from .model_stream import TextDelta, ThinkingDelta


def history_tool_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep recovery facts, not duplicate display payloads, in conversation history."""
    return {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            "display_messages",
            "raw_response",
            "artifacts",
            "parameters",
            "output",
            "injected_message",
            "activity",
        }
    }


def model_message_view(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project exactly the message fields consumed by the Dify model adapter."""
    projected = []
    for message in messages:
        role = message.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        item = {"role": role, "content": message.get("content") or ""}
        if role == "assistant" and message.get("tool_calls"):
            item["tool_calls"] = [
                {key: call[key] for key in ("id", "name", "arguments") if key in call}
                for call in message["tool_calls"]
            ]
        elif role == "tool":
            item.update(
                tool_call_id=message.get("tool_call_id") or "", name=message.get("name") or ""
            )
        projected.append(item)
    return projected


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""

    def to_history(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "name": self.name, "arguments": self.arguments}
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
class TextResourcePage:
    path: str
    offset: int
    text: str
    total_chars: int
    response_limit: int

    def render(self, max_chars: int) -> tuple[str, dict[str, Any]]:
        max_chars = min(max_chars, self.response_limit)
        count = min(len(self.text), max_chars)
        while True:
            end = self.offset + count
            next_offset = end if end < self.total_chars else None
            header = (
                f"Skill resource loaded: {self.path}\n"
                f"chars={self.offset}:{end}/{self.total_chars}; next_offset={next_offset}"
            )
            available = max_chars - len(header) - 2
            if available < 0 or (available < 1 and self.text):
                raise ValueError("Resource result budget is too small for paging metadata.")
            if count <= available:
                return header + "\n\n" + self.text[:count], {
                    "path": self.path,
                    "offset": self.offset,
                    "end_offset": end,
                    "next_offset": next_offset,
                    "total_chars": self.total_chars,
                }
            count = max(0, available)


@dataclass(slots=True)
class ToolResult:
    tool_call_id: str
    tool_name: str
    llm_observation: str
    display_messages: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_error: bool = False
    synthetic: bool = False
    resource_page: TextResourcePage | None = field(default=None, repr=False)

    def to_history(self) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": self.tool_name,
            "content": self.llm_observation or "(tool completed with no output)",
            "metadata": history_tool_metadata(self.metadata),
            "is_error": self.is_error,
            "synthetic": self.synthetic,
        }


@dataclass(slots=True)
class AgentState:
    history: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    history_version: int = 1
    skills: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    active_skills: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class AgentRunResult:
    answer: str
    history: list[dict[str, Any]]
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

    @property
    def run_status(self) -> str:
        reason = self.execution_metadata.get("finish_reason", "final")
        if reason == "awaiting_user":
            return "awaiting_user"
        if reason in {
            "max_iterations",
            "budget_exhausted",
            "length",
            "max_tokens",
            "max_output_tokens",
            "token_limit",
        }:
            return "budget_exhausted"
        if (
            self.execution_metadata.get("error_code")
            or reason == "context_overflow"
            or str(reason).endswith("_error")
        ):
            return "failed"
        return "completed"

    def to_output_payload(self) -> dict[str, Any]:
        """Minimal payload for Dify agent structured output."""
        payload: dict[str, Any] = {
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
        payload: dict[str, Any] = {
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
                    "tasks": self.tasks,
                    "permissions": self.permissions,
                }
            )
        return payload


def assistant_message(turn: AssistantTurn) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": turn.text or ""}
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
