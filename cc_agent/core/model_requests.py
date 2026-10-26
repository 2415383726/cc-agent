from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

from .config import AgentRunConfig
from .context_budget import ContextBudget, estimate_context_tokens, limit_text_to_tokens
from .error_classifier import ContextOverflowError, classify_error, extract_context_numbers
from .messages import AgentState
from .model_stream import AssistantTurnCompleted, TextDelta, ThinkingDelta
from .prompt_builder import PromptBuilder
from .tool_catalog import ToolCatalog


class ModelRequests:
    """Own request budgets, compaction and the single overflow retry for all model turns."""

    def __init__(
        self,
        config: AgentRunConfig,
        state: AgentState,
        catalog: ToolCatalog,
        model_adapter: Any,
        summarizer: Any,
        emit: Callable[..., list[dict[str, Any]]],
        record_timing: Callable[..., float],
    ):
        self.config = config
        self.state = state
        self.registry = catalog
        self.model_adapter = model_adapter
        self.summarizer = summarizer
        self._write = emit
        self._record_timing = record_timing
        self.context_budget = ContextBudget(
            max_history_messages=config.max_history_messages,
            max_observation_chars=config.max_observation_chars,
            max_total_context_tokens=config.resolved_context_limit
            or config.max_total_context_tokens,
        )
        self.prompt_builder = PromptBuilder(
            config, state, summarizer=summarizer, budget=self.context_budget
        )
        self.reset()

    def reset(self) -> None:
        self.last_budget_metadata: dict[str, Any] = {}
        self.recovery_metadata: dict[str, Any] = {
            "context_overflow_detected": False,
            "context_retry_count": 0,
            "context_error_numbers": [],
        }
        self.recovery_compaction: dict[str, Any] = {
            "compressed": False,
            "compressed_reason": [],
            "truncated_observations": 0,
            "summarized_messages": 0,
        }

    def stream(
        self,
        prompt_messages: list[dict[str, Any]],
        transcript: list[dict[str, Any]],
        force_final: bool,
        iteration: int,
    ) -> Iterator[Any]:
        try:
            yield from self._events(prompt_messages, force_final, iteration)
            return
        except Exception as error:
            if classify_error(error) != "context_overflow":
                raise
            self.recovery_metadata["context_overflow_detected"] = True
            self.recovery_metadata["context_retry_count"] += 1
            self.recovery_metadata["context_error_numbers"] = list(
                dict.fromkeys(
                    [
                        *self.recovery_metadata["context_error_numbers"],
                        *extract_context_numbers(error),
                    ]
                )
            )
        compression_id = f"compression:context_overflow:{iteration}"
        yield from self._write(
            "write_activity",
            "cc_agent.compression",
            _compression_activity("started", "context_overflow", compression_id),
        )
        metadata = self.compact(transcript, force=True)
        prompt_messages, prepared = self.prepare(transcript, force_final)
        for item in (metadata, prepared):
            self.recovery_compaction["compressed"] |= bool(item.get("compressed"))
            self.recovery_compaction["compressed_reason"].extend(
                item.get("compressed_reason") or []
            )
            for key in ("truncated_observations", "summarized_messages"):
                self.recovery_compaction[key] += int(item.get(key) or 0)
        yield from self._write(
            "write_activity",
            "cc_agent.compression",
            {
                **_compression_activity("completed", "context_overflow", compression_id, metadata),
                **self.recovery_metadata,
            },
        )
        # A second provider failure leaves this module; never start a third attempt.
        yield from self._events(prompt_messages, force_final, iteration)

    def prepare(
        self, transcript: list[dict[str, Any]], force_final: bool = False
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        tools = self.tools(force_final)
        preflight_compactions = 0
        combined_reasons: list[str] = []
        combined_truncated = 0
        combined_summarized = 0
        try:
            for attempt in range(4):
                prompt, metadata = self.prompt_builder.build(transcript, tools=tools)
                if not metadata.get("request_over_budget"):
                    if preflight_compactions:
                        metadata["compressed"] = True
                        combined_reasons.append("request_budget")
                    metadata["compressed_reason"] = list(
                        dict.fromkeys(
                            [*combined_reasons, *(metadata.get("compressed_reason") or [])]
                        )
                    )
                    metadata["truncated_observations"] = combined_truncated + int(
                        metadata.get("truncated_observations") or 0
                    )
                    metadata["summarized_messages"] = combined_summarized + int(
                        metadata.get("summarized_messages") or 0
                    )
                    metadata["preflight_compactions"] = preflight_compactions
                    self.last_budget_metadata = dict(metadata)
                    return prompt, metadata
                if attempt >= 3:
                    break
                before = (len(transcript), estimate_context_tokens(transcript), self.state.summary)
                compacted = self.compact(transcript, force=True)
                preflight_compactions += 1
                combined_reasons.extend(compacted.get("compressed_reason") or [])
                combined_truncated += int(compacted.get("truncated_observations") or 0)
                combined_summarized += int(compacted.get("summarized_messages") or 0)
                summary_limit = min(8192, max(512, self.context_budget.input_budget_tokens // 5))
                self.state.summary = limit_text_to_tokens(self.state.summary, summary_limit)
                after = (len(transcript), estimate_context_tokens(transcript), self.state.summary)
                if after == before:
                    break

            prompt, metadata = self.prompt_builder.build(transcript, tools=tools)
            reason = (
                "static_context_too_large"
                if int(metadata.get("static_context_tokens") or 0)
                >= int(metadata.get("input_budget_tokens") or 0)
                else "history_could_not_be_compacted_to_fit"
            )
            self.last_budget_metadata = dict(metadata)
            self.recovery_metadata["context_overflow_detected"] = True
            raise ContextOverflowError(
                "CC Agent request exceeds the configured input budget before model invocation: "
                f"reason={reason}, estimated_tokens={metadata.get('request_estimated_tokens')}, "
                f"input_budget_tokens={metadata.get('input_budget_tokens')}"
            )
        finally:
            self._record_timing("prompt_build_ms", started)

    def compact(self, transcript: list[dict[str, Any]], force: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = self.context_budget.compact_history(
                transcript,
                existing_summary=self.state.summary,
                summarizer=self.summarizer,
                force=force,
                max_summary_tokens=min(
                    8192, max(512, self.context_budget.input_budget_tokens // 5)
                ),
            )
            if result.metadata.get("compressed"):
                transcript[:] = result.messages
                self.state.summary = result.summary
            return result.metadata
        finally:
            self._record_timing("compaction_ms", started)

    def needs_compaction(self, transcript: list[dict[str, Any]], force: bool = False) -> bool:
        if force:
            return True
        threshold = self.context_budget.input_budget_tokens
        return (
            len(transcript) > self.context_budget.max_history_messages
            or estimate_context_tokens(transcript) > threshold
        )

    def _events(self, prompt_messages: list[dict[str, Any]], force_final: bool, iteration: int):
        started = time.perf_counter()
        try:
            tools = self.tools(force_final)
            if hasattr(self.model_adapter, "invoke_stream"):
                events = self.model_adapter.invoke_stream(
                    prompt_messages, tools, force_final=force_final
                )
            else:
                turn = self.model_adapter.invoke(prompt_messages, tools, force_final=force_final)
                stream_chunks = turn.stream_chunks or (
                    [TextDelta(text=turn.text)] if turn.text else []
                )
                events = [*stream_chunks, AssistantTurnCompleted(turn=turn)]
            for event in events:
                if isinstance(event, AssistantTurnCompleted):
                    yield event
                    continue
                if isinstance(event, TextDelta):
                    yield from self._write("write_text_delta", event.text, iteration=iteration)
                    continue
                if isinstance(event, ThinkingDelta):
                    yield from self._write("write_reasoning_delta", event.text, iteration=iteration)
                    continue
                yield event
        finally:
            self._record_timing("model_ms", started, iteration=iteration)

    def tools(self, force_final: bool) -> list[Any]:
        if force_final:
            return []
        tools = self.registry.prompt_tools()
        if not tools:
            return []
        return tools


def _compression_activity(
    status: str, trigger: str, compression_id: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload.update(
        {
            "status": status,
            "trigger": trigger,
            "compressionId": compression_id,
            "messageId": compression_id,
        }
    )
    return payload
