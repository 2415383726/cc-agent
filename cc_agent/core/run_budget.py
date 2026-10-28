from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class RunBudgetExceeded(RuntimeError):
    def __init__(self, resource: str):
        super().__init__(f"Run budget exhausted: {resource}.")
        self.resource = resource


@dataclass(slots=True)
class RunBudget:
    max_model_calls: int = 32
    max_tool_calls: int = 64
    max_run_seconds: float = 300
    max_run_tokens: int = 0
    run_id: str = ""
    clock: Callable[[], float] = time.monotonic
    model_calls: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    exceeded: str = ""
    tool_outcomes: Counter = field(default_factory=Counter)
    started_at: float = field(init=False)

    def __post_init__(self):
        self.started_at = self.clock()

    @classmethod
    def from_config(cls, config: Any, run_id: str = "") -> RunBudget:
        return cls(
            config.max_model_calls,
            config.max_tool_calls,
            config.max_run_seconds,
            config.max_run_tokens,
            run_id=run_id,
        )

    def check(self) -> None:
        if not self.exceeded and self.clock() - self.started_at >= self.max_run_seconds:
            self.exceeded = "elapsed_time"
        if not self.exceeded and self.max_run_tokens and self.total_tokens >= self.max_run_tokens:
            self.exceeded = "tokens"
        if self.exceeded:
            raise RunBudgetExceeded(self.exceeded)

    def before_model(self) -> None:
        self.check()
        if self.model_calls >= self.max_model_calls:
            self.exceeded = "model_calls"
            raise RunBudgetExceeded(self.exceeded)
        self.model_calls += 1

    def before_tool(self) -> None:
        self.check()
        if self.tool_calls >= self.max_tool_calls:
            self.exceeded = "tool_calls"
            raise RunBudgetExceeded(self.exceeded)
        self.tool_calls += 1

    def record_usage(self, usage: Any) -> None:
        def count(key):
            value = usage.get(key, 0) if isinstance(usage, dict) else getattr(usage, key, 0)
            try:
                return max(0, int(value or 0))
            except (ValueError, TypeError):
                return 0

        prompt, completion = count("prompt_tokens"), count("completion_tokens")
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += count("total_tokens") or prompt + completion

    def record_tool(self, result: Any) -> None:
        self.tool_outcomes[result.metadata["execution_outcome"]] += 1

    def summary(self) -> dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "elapsed_ms": round((self.clock() - self.started_at) * 1000, 3),
            "exhausted_resource": self.exceeded or None,
            "tool_outcomes": dict(self.tool_outcomes),
        }
