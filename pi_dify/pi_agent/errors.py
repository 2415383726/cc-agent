"""Safe, typed failures for the Dify host boundary.

Nothing in this module may carry provider headers, credentials, tracebacks or
raw exception text into a prompt, a state value or a Dify message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SAFE_ERROR_CODES = frozenset(
    {
        "agent_failed",
        "invalid_configuration",
        "invalid_state",
        "state_save_failed",
        "state_too_large",
        "context_too_large",
        "context_overflow",
        "budget_exhausted",
        "pending_invalid",
        "pending_expired",
        "pending_consumed",
        "approval_rejected",
        "approval_unknown",
        "tool_failed",
        "tool_unknown",
        "provider_failed",
        "stream_failed",
        "stopped",
        "unknown_outcome",
        "aborted",
    }
)


@dataclass(slots=True)
class PiError(Exception):
    """A failure whose code and message are safe to show to a user."""

    code: str = "agent_failed"
    stage: str = "runtime"
    message: str = "The Pi agent run failed."
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in SAFE_ERROR_CODES:
            self.code = "agent_failed"
        Exception.__init__(self, self.message)

    def public(self, run_id: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "agent_failed",
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
        }
        if run_id:
            payload["run_id"] = run_id
        if self.details:
            payload["details"] = self.details
        return payload


class BudgetExceeded(PiError):
    def __init__(self, reason: str, stage: str = "budget") -> None:
        messages = {
            "model_requests": "The model request budget for this turn is exhausted.",
            "tool_calls": "The tool call budget for this turn is exhausted.",
            "wall_time": "The time budget for this turn is exhausted.",
            "tokens": "The reported token budget for this turn is exhausted.",
            "duplicate_tools": "Repeated identical tool calls were blocked.",
            "consecutive_errors": "Too many consecutive tool failures stopped the run.",
        }
        super().__init__(
            code="budget_exhausted",
            stage=stage,
            message=messages.get(reason, "The execution budget is exhausted."),
            details={"reason": reason},
        )
        self.reason = reason


class ContextOverflow(PiError):
    def __init__(self, message: str = "The model context window was exceeded.") -> None:
        super().__init__(code="context_overflow", stage="model", message=message)


class ContextTooLarge(PiError):
    def __init__(
        self, message: str = "The fixed prompt content exceeds the model context window."
    ) -> None:
        super().__init__(code="context_too_large", stage="model", message=message)


class StateError(PiError):
    def __init__(
        self, message: str = "The saved Pi state is invalid.", code: str = "invalid_state"
    ) -> None:
        super().__init__(code=code, stage="state", message=message)


class PendingError(PiError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code=code, stage="interaction", message=message, details=details or {})


class ToolPolicyError(PiError):
    def __init__(self, message: str, code: str = "tool_failed") -> None:
        super().__init__(code=code, stage="tool", message=message)
