from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TextDelta:
    text: str | None
    iteration: int = 0
    seq: int = 0


@dataclass(slots=True)
class ThinkingDelta:
    text: str | None
    iteration: int = 0
    seq: int = 0


@dataclass(slots=True)
class AssistantTurnCompleted:
    turn: object

