from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .agui_stream import AgUiStreamWriter
from .dify_stream_writer import DifyNativeWriter


AgentEventKind = Literal[
    "run_started",
    "text_delta",
    "reasoning_delta",
    "tool_call",
    "tool_result",
    "activity",
    "variable",
    "json",
    "run_finished",
    "run_error",
]


@dataclass(frozen=True, slots=True)
class AgentEvent:
    kind: AgentEventKind
    payload: dict[str, Any] = field(default_factory=dict)


class ProtocolRenderer:
    """Render immutable AgentEvent objects through a stateful protocol writer."""

    def __init__(self, output_protocol: str, thread_id: str, run_id: str, show_tool_calls: bool = True):
        self.output_protocol = output_protocol
        if output_protocol == "agui":
            self.writer = AgUiStreamWriter(
                thread_id=thread_id,
                run_id=run_id,
                show_tool_calls=show_tool_calls,
            )
        elif output_protocol == "dify_native":
            self.writer = DifyNativeWriter(thread_id=thread_id, run_id=run_id, show_tool_calls=show_tool_calls)
        else:
            raise ValueError(f"unsupported output_protocol: {output_protocol}")

    def render(self, event: AgentEvent) -> list[dict[str, Any]]:
        payload = event.payload
        if event.kind == "run_started":
            return self.writer.write_run_started()
        if event.kind == "text_delta":
            return self.writer.write_text_delta(payload.get("text"), iteration=int(payload.get("iteration") or 0))
        if event.kind == "reasoning_delta":
            return self.writer.write_reasoning_delta(payload.get("text"), iteration=int(payload.get("iteration") or 0))
        if event.kind == "tool_call":
            return self.writer.write_tool_call(
                str(payload.get("tool_call_id") or ""),
                str(payload.get("tool_name") or ""),
                payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
            )
        if event.kind == "tool_result":
            return self.writer.write_tool_result(
                str(payload.get("tool_call_id") or ""),
                str(payload.get("tool_name") or ""),
                payload.get("observation"),
                output=payload.get("output"),
                is_error=bool(payload.get("is_error")),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
            )
        if event.kind == "activity":
            return self.writer.write_activity(
                str(payload.get("activity_type") or "activity"),
                payload.get("content") if isinstance(payload.get("content"), dict) else {},
            )
        if event.kind == "run_finished":
            return self.writer.write_run_finished(payload.get("result"))
        if event.kind == "run_error":
            return self.writer.write_run_error(payload.get("message"), code=payload.get("code"))
        if event.kind == "variable":
            return [{"type": "dify_variable", "name": str(payload.get("name") or ""), "value": payload.get("value", "")}]
        if event.kind == "json":
            return [{"type": "dify_json", "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {}}]
        return []

    def write_run_started(self) -> list[dict[str, Any]]:
        return self.render(AgentEvent("run_started"))

    def write_reasoning_delta(self, text: Any, iteration: int = 0) -> list[dict[str, Any]]:
        return self.render(AgentEvent("reasoning_delta", {"text": text, "iteration": iteration}))

    def write_text_delta(self, text: Any, iteration: int = 0) -> list[dict[str, Any]]:
        return self.render(AgentEvent("text_delta", {"text": text, "iteration": iteration}))

    def write_tool_call(self, tool_call_id: str, tool_name: str, arguments: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.render(
            AgentEvent(
                "tool_call",
                {"tool_call_id": tool_call_id, "tool_name": tool_name, "arguments": arguments or {}},
            )
        )

    def write_tool_result(
        self,
        tool_call_id: str,
        tool_name: str = "",
        observation: Any = None,
        *,
        output: Any = None,
        is_error: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.render(
            AgentEvent(
                "tool_result",
                {
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "observation": observation,
                    "output": output,
                    "is_error": is_error,
                    "metadata": metadata or {},
                },
            )
        )

    def write_activity(self, activity_type: str, content: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.render(AgentEvent("activity", {"activity_type": activity_type, "content": content or {}}))

    def write_custom(self, name: str, value: Any) -> list[dict[str, Any]]:
        method = getattr(self.writer, "write_custom", None)
        return list(method(name, value) or []) if callable(method) else []

    def write_run_finished(self, result: Any) -> list[dict[str, Any]]:
        return self.render(AgentEvent("run_finished", {"result": result}))

    def write_run_error(self, message: Any, code: str | None = None) -> list[dict[str, Any]]:
        return self.render(AgentEvent("run_error", {"message": message, "code": code}))

    def close_reasoning(self) -> list[dict[str, Any]]:
        return list(getattr(self.writer, "close_reasoning")())

    def close_text(self) -> list[dict[str, Any]]:
        return list(getattr(self.writer, "close_text")())

    def close_open_messages(self) -> list[dict[str, Any]]:
        return list(getattr(self.writer, "close_open_messages")())
