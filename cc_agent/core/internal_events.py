from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias


@dataclass(slots=True)
class ModelStarted:
    iteration: int
    tools_enabled: bool = True
    stream_mode: bool = True
    force_final: bool = False


@dataclass(slots=True)
class ModelEnded:
    iteration: int
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    force_final: bool = False


@dataclass(slots=True)
class ModelError:
    message: str
    finish_reason: str
    iteration: int = 0
    error: Any = None


@dataclass(slots=True)
class ToolStarted:
    tool_call_id: str
    tool_name: str
    iteration: int = 0


@dataclass(slots=True)
class ToolCompleted:
    """Includes successful, failed, and synthetic tool results."""

    tool_call_id: str
    tool_name: str
    observation: Any
    output: Any = None
    is_error: bool = False
    synthetic: bool = False
    display_messages: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    iteration: int = 0


@dataclass(slots=True)
class LoopIteration:
    iteration: int
    budget: dict[str, Any]


InternalEvent: TypeAlias = ModelStarted | ModelEnded | ModelError | ToolStarted | ToolCompleted | LoopIteration


def validate_internal_events(events: list[InternalEvent]) -> None:
    started: dict[str, ToolStarted] = {}
    completed: set[str] = set()

    for event in events:
        if isinstance(event, ToolStarted):
            if event.tool_call_id in started:
                raise ValueError(f"duplicate tool_call_id: {event.tool_call_id}")
            started[event.tool_call_id] = event
            continue
        if isinstance(event, ToolCompleted):
            if event.tool_call_id and event.tool_call_id not in started:
                raise ValueError(f"orphan tool result: {event.tool_call_id}")
            if event.tool_call_id in completed:
                raise ValueError(f"duplicate tool result: {event.tool_call_id}")
            completed.add(event.tool_call_id)

    missing = sorted(set(started) - completed)
    if missing:
        raise ValueError(f"missing tool result for tool_call_id(s): {', '.join(missing)}")

