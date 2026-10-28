from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .guards import ToolGuard
from .internal_events import InternalEvent, ToolCompleted, ToolStarted
from .interrupts import UserInterrupts
from .messages import ToolCall, ToolResult
from .result_budget import ResultBudget
from .run_budget import RunBudget, RunBudgetExceeded
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
        interrupts: UserInterrupts | None = None,
        run_budget: RunBudget | None = None,
    ):
        self.tool_adapter = tool_adapter
        self.result_budget = result_budget or ResultBudget()
        self.guard = guard or ToolGuard()
        self.interrupts = interrupts
        self.run_budget = run_budget

    def execute(self, tool_calls: list[ToolCall], iteration: int) -> list[ScheduledToolResult]:
        return [
            item
            for item in self.iter_execute(tool_calls, iteration)
            if isinstance(item, ScheduledToolResult)
        ]

    def iter_execute(self, tool_calls: list[ToolCall], iteration: int):
        scheduled: list[ScheduledToolResult] = []
        for call_index, tool_call in enumerate(tool_calls):
            total_started = time.perf_counter()
            events: list[InternalEvent] = [
                ToolStarted(
                    iteration=iteration, tool_call_id=tool_call.id, tool_name=tool_call.name
                )
            ]
            yield events[0]
            guard_started = time.perf_counter()
            result = self.guard.before_call(tool_call)
            guard_ms = (time.perf_counter() - guard_started) * 1000
            permission_started = time.perf_counter()
            if result is None and self.interrupts is not None:
                result = self.interrupts.before_call(tool_call)
            permission_ms = (time.perf_counter() - permission_started) * 1000
            execution_started = time.perf_counter()
            if result is None:
                try:
                    if self.run_budget is not None:
                        self.run_budget.before_tool()
                    result = self.tool_adapter.execute(tool_call)
                except RunBudgetExceeded:
                    result = ToolResult(
                        tool_call.id,
                        tool_call.name,
                        "Not executed: the run execution budget has been exhausted.",
                        is_error=True,
                        synthetic=True,
                        metadata={"budget_exhausted": True, "execution_outcome": "not_executed"},
                    )
            result.metadata.setdefault(
                "execution_outcome",
                (
                    "not_executed"
                    if result.synthetic or result.metadata.get("requires_user_input")
                    else "failed" if result.is_error else "succeeded"
                ),
            )
            if self.run_budget is not None:
                result.metadata["run_id"] = self.run_budget.run_id
                self.run_budget.record_tool(result)
            execution_ms = (time.perf_counter() - execution_started) * 1000
            budget_started = time.perf_counter()
            result = self.result_budget.apply(result)
            budget_ms = (time.perf_counter() - budget_started) * 1000
            self.guard.after_result(result)
            total_ms = (time.perf_counter() - total_started) * 1000
            logger.info(
                "cc_agent tool completed: run_id=%s call_id=%s tool=%s outcome=%s duration_ms=%.3f",
                self.run_budget.run_id if self.run_budget else "",
                tool_call.id,
                tool_call.name,
                result.metadata["execution_outcome"],
                total_ms,
            )
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
            item = ScheduledToolResult(tool_call=tool_call, result=result, events=events)
            scheduled.append(item)
            yield item
            if result.metadata.get("requires_user_input"):
                for skipped_call in tool_calls[call_index + 1 :]:
                    skipped = ToolResult(
                        skipped_call.id,
                        skipped_call.name,
                        "Not executed: an earlier tool call is waiting for the user. Request this operation again only after the interrupt is resolved.",
                        synthetic=True,
                        metadata={
                            "skipped": True,
                            "skip_reason": "awaiting_user",
                            "execution_outcome": "not_executed",
                        },
                    )
                    if self.run_budget is not None:
                        skipped.metadata["run_id"] = self.run_budget.run_id
                        self.run_budget.record_tool(skipped)
                    scheduled.append(
                        ScheduledToolResult(
                            skipped_call,
                            self.result_budget.apply(skipped),
                            [
                                ToolStarted(
                                    iteration=iteration,
                                    tool_call_id=skipped_call.id,
                                    tool_name=skipped_call.name,
                                )
                            ],
                        )
                    )
                    yield scheduled[-1].events[0]
                    yield scheduled[-1]
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
