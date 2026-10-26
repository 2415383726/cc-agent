from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .guards import ToolGuard
from .internal_events import InternalEvent, ToolCompleted, ToolStarted
from .messages import ToolCall, ToolResult
from .permissions import PermissionManager
from .result_budget import ResultBudget
from .tool_adapter import ToolAdapter


logger = logging.getLogger(__name__)
SLOW_TOOL_THRESHOLD_MS = 2000.0


@dataclass(slots=True)
class ScheduledToolResult:
    tool_call: ToolCall
    result: ToolResult
    events: list[InternalEvent]


class SerialToolScheduler:
    def __init__(
        self,
        tool_adapter: ToolAdapter,
        result_budget: ResultBudget | None = None,
        guard: ToolGuard | None = None,
        permission_manager: PermissionManager | None = None,
    ):
        self.tool_adapter = tool_adapter
        self.result_budget = result_budget or ResultBudget()
        self.guard = guard or ToolGuard()
        self.permission_manager = permission_manager

    def execute(self, tool_calls: list[ToolCall], iteration: int) -> list[ScheduledToolResult]:
        scheduled: list[ScheduledToolResult] = []
        for tool_call in tool_calls:
            total_started = time.perf_counter()
            events = [
                ToolStarted(iteration=iteration, tool_call_id=tool_call.id, tool_name=tool_call.name)
            ]
            permission_started = time.perf_counter()
            result = self.permission_manager.before_call(tool_call) if self.permission_manager else None
            permission_ms = (time.perf_counter() - permission_started) * 1000
            guard_started = time.perf_counter()
            if result is None:
                result = self.guard.before_call(tool_call)
            guard_ms = (time.perf_counter() - guard_started) * 1000
            execution_started = time.perf_counter()
            if result is None:
                result = self.tool_adapter.execute(tool_call)
            execution_ms = (time.perf_counter() - execution_started) * 1000
            budget_started = time.perf_counter()
            result = self.result_budget.apply(result)
            budget_ms = (time.perf_counter() - budget_started) * 1000
            self.guard.after_result(result)
            total_ms = (time.perf_counter() - total_started) * 1000
            result.metadata = {
                **(result.metadata or {}),
                "total_duration_ms": round(total_ms, 3),
                "phase_durations_ms": {
                    "permission": round(permission_ms, 3),
                    "guard": round(guard_ms, 3),
                    "execution": round(execution_ms, 3),
                    "result_budget": round(budget_ms, 3),
                },
            }
            if total_ms >= SLOW_TOOL_THRESHOLD_MS:
                logger.warning(
                    "cc_agent slow tool: tool=%s duration_ms=%.3f iteration=%s",
                    tool_call.name,
                    total_ms,
                    iteration,
                )
            scheduled.append(ScheduledToolResult(tool_call=tool_call, result=result, events=events))
            if result.metadata.get("requires_user_input"):
                break

        self.result_budget.apply_batch([item.result for item in scheduled])
        for item in scheduled:
            result = item.result
            item.events.append(
                ToolCompleted(
                    iteration=iteration,
                    tool_call_id=item.tool_call.id,
                    tool_name=item.tool_call.name,
                    observation=result.llm_observation,
                    output=result.metadata.get("output"),
                    is_error=result.is_error,
                    synthetic=result.synthetic,
                    display_messages=list(result.display_messages),
                    metadata=dict(result.metadata),
                )
            )
        return scheduled
