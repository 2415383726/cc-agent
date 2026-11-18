"""One ledger for every real model request and tool execution in a Dify turn."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pi_agent_core.messages import Usage

from .config import RuntimeConfig
from .errors import BudgetExceeded


@dataclass(slots=True)
class BudgetSnapshot:
    run_id: str
    model_requests: int
    tool_calls: int
    reported_input_tokens: int
    reported_output_tokens: int
    reported_total_tokens: int
    reasoning_tokens: int
    estimated_tokens: int
    unknown_usage_requests: int
    elapsed_seconds: float
    duplicate_blocked: int
    consecutive_errors: int
    finish_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_requests": self.model_requests,
            "tool_calls": self.tool_calls,
            "usage": {
                "reported": {
                    "input_tokens": self.reported_input_tokens,
                    "output_tokens": self.reported_output_tokens,
                    "total_tokens": self.reported_total_tokens,
                    "reasoning_tokens": self.reasoning_tokens,
                    "requests": self.model_requests - self.unknown_usage_requests,
                },
                "estimated_tokens": self.estimated_tokens,
                "unknown_usage_requests": self.unknown_usage_requests,
            },
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "duplicate_blocked": self.duplicate_blocked,
            "consecutive_errors": self.consecutive_errors,
            "finish_reason": self.finish_reason,
        }


@dataclass(slots=True)
class RunLedger:
    config: RuntimeConfig
    run_id: str
    clock: Callable[[], float] = time.monotonic
    model_requests: int = 0
    tool_calls: int = 0
    reported_input_tokens: int = 0
    reported_output_tokens: int = 0
    reported_total_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_tokens: int = 0
    unknown_usage_requests: int = 0
    duplicate_blocked: int = 0
    consecutive_errors: int = 0
    finish_reason: str | None = None
    started_at: float = field(init=False)
    _tool_signatures: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.started_at = self.clock()

    def elapsed(self) -> float:
        return max(0.0, self.clock() - self.started_at)

    def _check_wall(self) -> None:
        if self.config.max_wall_seconds and self.elapsed() > self.config.max_wall_seconds:
            self.finish_reason = "wall_time"
            raise BudgetExceeded("wall_time")

    def before_model(self, estimated_tokens: int = 0) -> None:
        self._check_wall()
        if self.model_requests >= self.config.max_model_requests:
            self.finish_reason = "model_requests"
            raise BudgetExceeded("model_requests")
        if (
            self.config.max_reported_tokens
            and self.reported_total_tokens >= self.config.max_reported_tokens
        ):
            self.finish_reason = "tokens"
            raise BudgetExceeded("tokens")

    def record_model(
        self, usage: Usage | None, estimated_tokens: int, source: str = "normal"
    ) -> None:
        self.model_requests += 1
        if usage is None or (
            not usage.input
            and not usage.output
            and not usage.totalTokens
            and not usage.cacheRead
            and not usage.cacheWrite
        ):
            self.unknown_usage_requests += 1
            self.estimated_tokens += max(0, estimated_tokens)
            return
        self.reported_input_tokens += usage.input + usage.cacheRead + usage.cacheWrite
        self.reported_output_tokens += usage.output
        self.reported_total_tokens += usage.totalTokens or (
            usage.input + usage.output + usage.cacheRead + usage.cacheWrite
        )
        self.reasoning_tokens += usage.reasoningTokens
        self.estimated_tokens += max(0, estimated_tokens)

    def before_tool(self, name: str, arguments: dict[str, Any]) -> None:
        self._check_wall()
        if self.tool_calls >= self.config.max_tool_calls:
            self.finish_reason = "tool_calls"
            raise BudgetExceeded("tool_calls")
        if self.consecutive_errors >= self.config.max_consecutive_errors:
            self.finish_reason = "consecutive_errors"
            raise BudgetExceeded("consecutive_errors")
        key = _signature(name, arguments)
        seen = self._tool_signatures.get(key, 0)
        if seen >= self.config.max_duplicate_tool_calls:
            self.duplicate_blocked += 1
            self.finish_reason = "duplicate_tools"
            raise BudgetExceeded("duplicate_tools")
        self._tool_signatures[key] = seen + 1
        self.tool_calls += 1

    def record_tool(self, is_error: bool, result_chars: int) -> None:
        if is_error:
            self.consecutive_errors += 1
        else:
            self.consecutive_errors = 0
        self.estimated_tokens += max(1, result_chars // 4)
        if (
            self.config.max_reported_tokens
            and self.reported_total_tokens > self.config.max_reported_tokens
        ):
            self.finish_reason = "tokens"

    def mark(self, reason: str) -> None:
        self.finish_reason = reason

    def exhausted(self) -> bool:
        return self.finish_reason is not None

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            run_id=self.run_id,
            model_requests=self.model_requests,
            tool_calls=self.tool_calls,
            reported_input_tokens=self.reported_input_tokens,
            reported_output_tokens=self.reported_output_tokens,
            reported_total_tokens=self.reported_total_tokens,
            reasoning_tokens=self.reasoning_tokens,
            estimated_tokens=self.estimated_tokens,
            unknown_usage_requests=self.unknown_usage_requests,
            elapsed_seconds=self.elapsed(),
            duplicate_blocked=self.duplicate_blocked,
            consecutive_errors=self.consecutive_errors,
            finish_reason=self.finish_reason,
        )


def _signature(name: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{name}:{digest}"


def estimate_text_tokens(text: str) -> int:
    return max(0, (len(text or "") + 3) // 4)
