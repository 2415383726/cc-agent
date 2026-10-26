from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .messages import ToolCall, ToolResult


@dataclass(slots=True)
class ToolGuardConfig:
    allowlist: list[str] | None = None
    denylist: list[str] | None = None
    require_confirmation: list[str] | None = None
    max_repeated_calls: int = 3
    max_consecutive_errors: int = 3


@dataclass(slots=True)
class ToolGuard:
    config: ToolGuardConfig = field(default_factory=ToolGuardConfig)
    repeated_calls: dict[str, int] = field(default_factory=dict)
    consecutive_errors: int = 0

    def before_call(self, tool_call: ToolCall) -> ToolResult | None:
        if self.config.allowlist and tool_call.name not in self.config.allowlist:
            return self._reject(tool_call, f"Tool call rejected by policy: {tool_call.name} is not in allowlist.")
        if self.config.denylist and tool_call.name in self.config.denylist:
            return self._reject(tool_call, f"Tool call rejected by policy: {tool_call.name} is in denylist.")
        if self.config.require_confirmation and tool_call.name in self.config.require_confirmation:
            return self._confirm(tool_call)
        if self.consecutive_errors >= self.config.max_consecutive_errors:
            return self._reject(
                tool_call,
                "Tool call rejected by policy: maximum consecutive tool errors reached.",
            )
        key = f"{tool_call.name}:{json.dumps(tool_call.arguments, sort_keys=True, ensure_ascii=False)}"
        self.repeated_calls[key] = self.repeated_calls.get(key, 0) + 1
        if self.repeated_calls[key] > self.config.max_repeated_calls:
            return self._reject(
                tool_call,
                f"Tool call rejected by policy: repeated call to {tool_call.name}.",
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

    def _confirm(self, tool_call: ToolCall) -> ToolResult:
        question = _confirmation_question(tool_call)
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            llm_observation=f"Executing {tool_call.name} requires user confirmation.",
            synthetic=True,
            metadata={
                "requires_user_input": True,
                "confirmation_required": True,
                "question": question,
                "pending_tool_execution": {
                    "name": tool_call.name,
                    "arguments": dict(tool_call.arguments or {}),
                    "raw_arguments": tool_call.raw_arguments or "",
                },
            },
        )


def _confirmation_question(tool_call: ToolCall) -> dict[str, Any]:
    question = f"允许执行工具 {tool_call.name} 吗？"
    if tool_call.arguments:
        serialized = json.dumps(tool_call.arguments, ensure_ascii=False, sort_keys=True)
        question = f"{question}\n参数：{serialized}"
    return {
        "id": tool_call.id,
        "question": question,
        "text": question,
        "purpose": "permission",
        "options": [
            {"label": "继续执行", "description": f"允许调用工具 {tool_call.name}", "value": "approve"},
            {"label": "取消", "description": "不执行这个工具", "value": "deny"},
        ],
        "multiSelect": False,
        "allowCustomInput": False,
        "tool_call_id": tool_call.id,
        "tool_name": tool_call.name,
    }
