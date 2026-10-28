from __future__ import annotations

import json
from dataclasses import dataclass, field

from .messages import ToolCall, ToolResult


@dataclass(slots=True)
class ToolGuardConfig:
    max_repeated_calls: int = 3
    max_consecutive_errors: int = 3


@dataclass(slots=True)
class ToolGuard:
    config: ToolGuardConfig = field(default_factory=ToolGuardConfig)
    repeated_calls: dict[str, int] = field(default_factory=dict)
    consecutive_errors: int = 0

    def before_call(self, tool_call: ToolCall) -> ToolResult | None:
        if self.consecutive_errors >= self.config.max_consecutive_errors:
            return self._reject(
                tool_call, "Tool call rejected by policy: maximum consecutive tool errors reached."
            )
        key = f"{tool_call.name}:{json.dumps(tool_call.arguments, sort_keys=True, ensure_ascii=False)}"
        self.repeated_calls[key] = self.repeated_calls.get(key, 0) + 1
        if self.repeated_calls[key] > self.config.max_repeated_calls:
            return self._reject(
                tool_call, f"Tool call rejected by policy: repeated call to {tool_call.name}."
            )
        return None

    def after_result(self, result: ToolResult) -> None:
        if result.is_error:
            self.consecutive_errors += 1
        else:
            self.consecutive_errors = 0

    def _reject(self, tool_call: ToolCall, observation: str) -> ToolResult:
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            llm_observation=observation,
            is_error=True,
            synthetic=True,
            metadata={"guard_rejected": True},
        )
