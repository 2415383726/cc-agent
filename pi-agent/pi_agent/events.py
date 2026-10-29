"""Execution facts consumed by output adapters; no wire or SDK message types."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RunStarted:
    pass


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True, slots=True)
class TurnEnded:
    pass


@dataclass(frozen=True, slots=True)
class ToolRequested:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCompleted:
    call_id: str
    name: str
    observation: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActivityChanged:
    kind: str
    content: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RunFailed:
    message: str
    code: str


type RunEvent = (
    RunStarted | TextDelta | ReasoningDelta | TurnEnded | ToolRequested | ToolCompleted
    | ActivityChanged | RunFailed
)
