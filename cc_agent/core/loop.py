from __future__ import annotations

import logging
import time
from typing import Any

from .config import AgentRunConfig
from .context_budget import ContextBudget, estimate_context_tokens, limit_text_to_tokens
from .history import sanitize_history
from .internal_events import (
    InternalEvent,
    LoopIteration,
    ModelEnded,
    ModelError,
    ModelStarted,
)
from .messages import AgentRunResult, AgentState, AssistantTurn, assistant_message, tool_message
from .model_stream import AssistantTurnCompleted, TextDelta, ThinkingDelta
from .error_classifier import ContextOverflowError, classify_error, extract_context_numbers
from .guards import ToolGuard, ToolGuardConfig
from .prompt_builder import PromptBuilder
from .permissions import PermissionManager
from .result_budget import ResultBudget
from .tool_adapter import ToolAdapter
from .tool_registry import ToolRegistry
from .tool_scheduler import SerialToolScheduler

try:  # pragma: no cover - only present under Dify plugin runtime
    from dify_plugin.config.logger_format import plugin_logger_handler
except Exception:  # pragma: no cover
    plugin_logger_handler = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if plugin_logger_handler is not None and plugin_logger_handler not in logger.handlers:
    logger.addHandler(plugin_logger_handler)

SLOW_PHASE_THRESHOLD_MS = 2000.0
TRUNCATED_FINISH_REASONS = {"length", "max_tokens", "max_output_tokens", "token_limit"}


class AgentLoop:
    def __init__(
        self,
        config: AgentRunConfig,
        state: AgentState,
        registry: ToolRegistry,
        model_adapter: Any,
        tool_adapter: ToolAdapter,
        summarizer: Any | None = None,
        include_user_query: bool = True,
        writer: Any | None = None,
        permission_manager: PermissionManager | None = None,
    ):
        self.config = config
        self.state = state
        self.registry = registry
        self.model_adapter = model_adapter
        self.tool_adapter = tool_adapter
        self.summarizer = summarizer
        self.include_user_query = include_user_query
        self.writer = writer
        self.final_result: AgentRunResult | None = None
        self.prompt_builder = PromptBuilder(config, state, summarizer=summarizer)
        self.context_budget = ContextBudget(
            max_history_messages=config.max_history_messages,
            max_observation_chars=config.max_observation_chars,
            max_total_context_chars=config.resolved_context_limit or config.max_total_context_tokens,
        )
        self.guard = ToolGuard(
            ToolGuardConfig(
                allowlist=config.tool_allowlist,
                denylist=config.tool_denylist,
                require_confirmation=config.tool_confirmation_list,
                max_repeated_calls=config.max_repeated_tool_calls,
                max_consecutive_errors=config.max_consecutive_tool_errors,
            )
        )
        self.scheduler = SerialToolScheduler(
            tool_adapter=tool_adapter,
            result_budget=ResultBudget(config.max_observation_chars),
            guard=self.guard,
            permission_manager=permission_manager,
        )
        self.events: list[InternalEvent] = []
        self._timings_ms = {
            "prompt_build_ms": 0.0,
            "model_ms": 0.0,
            "tool_ms": 0.0,
            "compaction_ms": 0.0,
        }
        self._last_budget_metadata: dict[str, Any] = {}
        self._tool_batch_truncated = False

    def _write(self, method_name: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        if self.writer is None:
            return []
        method = getattr(self.writer, method_name, None)
        if not callable(method):
            return []
        return list(method(*args, **kwargs) or [])

    def run(self):
        for key in self._timings_ms:
            self._timings_ms[key] = 0.0
        self._last_budget_metadata = {}
        self._tool_batch_truncated = False
        initial_messages = [*self.state.history]
        if self.include_user_query:
            initial_messages.append({"role": "user", "content": self.config.query})
        transcript = sanitize_history(initial_messages)
        total_tool_calls = 0
        total_tokens = 0
        compressed = False
        compressed_reason: list[str] = []
        truncated_observations = 0
        summarized_messages = 0
        finish_reason = "final"
        answer = ""
        awaiting_user_question: dict[str, Any] | None = None
        context_overflow_detected = False
        context_retry_count = 0
        context_error_numbers: list[int] = []
        continuation_count = 0
        continuation_error = ""

        for iteration in range(1, self.config.maximum_iterations + 1):
            logger.info(
                "cc_agent loop iteration started: iteration=%s transcript_count=%s",
                iteration,
                len(transcript),
            )
            compression_id = self._compression_id("auto", iteration)
            if self._should_compact_transcript(transcript, force=False):
                yield from self._write(
                    "write_activity",
                    "cc_agent.compression",
                    _compression_activity("started", "auto", compression_id),
                )
            compaction_metadata = self._compact_transcript(transcript, force=False)
            compressed = compressed or bool(compaction_metadata.get("compressed"))
            compressed_reason.extend(compaction_metadata.get("compressed_reason") or [])
            truncated_observations += int(compaction_metadata.get("truncated_observations") or 0)
            summarized_messages += int(compaction_metadata.get("summarized_messages") or 0)
            if compaction_metadata.get("compressed"):
                yield from self._write(
                    "write_activity",
                    "cc_agent.compression",
                    _compression_activity("completed", "auto", compression_id, compaction_metadata),
                )

            try:
                prompt_messages, budget_metadata = self._build_prompt(transcript, force_final=False)
            except ContextOverflowError as exc:
                context_overflow_detected = True
                self._set_final_result(
                    self._error_result(
                        "context_overflow",
                        exc,
                        transcript,
                        compressed,
                        total_tool_calls,
                        total_tokens,
                    )
                )
                return
            compressed = compressed or bool(budget_metadata.get("compressed"))
            compressed_reason.extend(budget_metadata.get("compressed_reason") or [])
            truncated_observations += int(budget_metadata.get("truncated_observations") or 0)
            summarized_messages += int(budget_metadata.get("summarized_messages") or 0)
            event = LoopIteration(iteration=iteration, budget=budget_metadata)
            self.events.append(event)
            if budget_metadata.get("compressed"):
                budget_compression_id = self._compression_id("auto_budget", iteration)
                yield from self._write(
                    "write_activity",
                    "cc_agent.compression",
                    _compression_activity("started", "auto", budget_compression_id),
                )
                yield from self._write(
                    "write_activity",
                    "cc_agent.compression",
                    _compression_activity("completed", "auto", budget_compression_id, budget_metadata),
                )
            event = ModelStarted(
                iteration=iteration,
                tools_enabled=self.config.tool_call_supported,
                stream_mode=self.config.stream,
            )
            self.events.append(event)

            try:
                turn = None
                for event in self._model_events(prompt_messages, force_final=False, iteration=iteration):
                    if isinstance(event, AssistantTurnCompleted):
                        turn = event.turn
                    else:
                        yield event
                if turn is None:
                    raise RuntimeError("model stream finished without assistant turn")
            except Exception as exc:
                logger.exception(
                    "cc_agent model iteration failed: iteration=%s error_type=%s error=%s",
                    iteration,
                    type(exc).__name__,
                    exc,
                )
                classified = classify_error(exc)
                if classified == "context_overflow":
                    context_overflow_detected = True
                    context_error_numbers.extend(extract_context_numbers(exc))
                    context_retry_count += 1
                    compression_id = self._compression_id("context_overflow", iteration)
                    yield from self._write(
                        "write_activity",
                        "cc_agent.compression",
                        _compression_activity("started", "context_overflow", compression_id),
                    )
                    forced_metadata = self._compact_transcript(transcript, force=True)
                    compressed = compressed or bool(forced_metadata.get("compressed"))
                    compressed_reason.extend(forced_metadata.get("compressed_reason") or [])
                    truncated_observations += int(forced_metadata.get("truncated_observations") or 0)
                    summarized_messages += int(forced_metadata.get("summarized_messages") or 0)
                    yield from self._write(
                        "write_activity",
                        "cc_agent.compression",
                        {
                            **_compression_activity("completed", "context_overflow", compression_id, forced_metadata),
                            "context_overflow_detected": True,
                            "context_retry_count": context_retry_count,
                            "context_error_numbers": list(dict.fromkeys(context_error_numbers)),
                        },
                    )
                    try:
                        prompt_messages, retry_budget_metadata = self._build_prompt(
                            transcript, force_final=False
                        )
                        compressed = compressed or bool(retry_budget_metadata.get("compressed"))
                        compressed_reason.extend(retry_budget_metadata.get("compressed_reason") or [])
                        turn = None
                        for event in self._model_events(prompt_messages, force_final=False, iteration=iteration):
                            if isinstance(event, AssistantTurnCompleted):
                                turn = event.turn
                            else:
                                yield event
                        if turn is None:
                            raise RuntimeError("model stream finished without assistant turn")
                    except Exception as retry_exc:
                        if isinstance(retry_exc, ContextOverflowError):
                            self._set_final_result(
                                self._error_result(
                                    "context_overflow",
                                    retry_exc,
                                    transcript,
                                    compressed,
                                    total_tool_calls,
                                    total_tokens,
                                )
                            )
                            return
                        if classify_error(retry_exc) != "context_overflow":
                            self._set_final_result(self._error_result(classify_error(retry_exc), retry_exc, transcript, compressed, total_tool_calls, total_tokens))
                            return
                        context_error_numbers.extend(extract_context_numbers(retry_exc))
                        context_retry_count += 1
                        try:
                            turn = None
                            for event in self._model_events(self._reactive_compact(prompt_messages), force_final=False, iteration=iteration):
                                if isinstance(event, AssistantTurnCompleted):
                                    turn = event.turn
                                else:
                                    yield event
                            if turn is None:
                                raise RuntimeError("model stream finished without assistant turn")
                            compressed = True
                            compressed_reason.append("reactive_compact")
                        except Exception as reactive_exc:
                            self._set_final_result(self._error_result(classify_error(reactive_exc), reactive_exc, transcript, compressed, total_tool_calls, total_tokens))
                            return
                else:
                    self._set_final_result(self._error_result(classified, exc, transcript, compressed, total_tool_calls, total_tokens))
                    return
            total_tokens += int(turn.usage.get("total_tokens") or 0)
            transcript.append(assistant_message(turn))
            event = ModelEnded(
                iteration=iteration,
                text=turn.text,
                tool_calls=[tool_call.to_history() for tool_call in turn.tool_calls],
                usage=turn.usage,
                force_final=False,
            )
            self.events.append(event)

            if not turn.tool_calls:
                answer = turn.text
                if _is_truncated_finish_reason(turn.finish_reason):
                    continuation_count = 1
                    continuation_message = {
                        "role": "user",
                        "content": (
                            "Continue from the exact point where the previous response stopped. "
                            "Do not repeat any prior text. Finish the answer concisely."
                        ),
                        "metadata": {"internal": True, "reason": "output_truncated"},
                    }
                    transcript.append(continuation_message)
                    try:
                        continuation_prompt, continuation_budget = self._build_prompt(
                            transcript, force_final=True
                        )
                        compressed = compressed or bool(continuation_budget.get("compressed"))
                        compressed_reason.extend(continuation_budget.get("compressed_reason") or [])
                        self.events.append(
                            ModelStarted(
                                iteration=iteration,
                                tools_enabled=False,
                                stream_mode=self.config.stream,
                                force_final=True,
                            )
                        )
                        continuation_turn = None
                        for event in self._model_events(
                            continuation_prompt,
                            force_final=True,
                            iteration=iteration,
                        ):
                            if isinstance(event, AssistantTurnCompleted):
                                continuation_turn = event.turn
                            else:
                                yield event
                        if continuation_turn is None:
                            raise RuntimeError("model continuation finished without assistant turn")
                        total_tokens += int(continuation_turn.usage.get("total_tokens") or 0)
                        transcript.append(assistant_message(continuation_turn))
                        self.events.append(
                            ModelEnded(
                                iteration=iteration,
                                text=continuation_turn.text,
                                tool_calls=[],
                                usage=continuation_turn.usage,
                                force_final=True,
                            )
                        )
                        answer = f"{turn.text or ''}{continuation_turn.text or ''}"
                        finish_reason = continuation_turn.finish_reason or "final"
                    except Exception as exc:
                        continuation_error = str(exc)
                        logger.warning(
                            "cc_agent truncated answer continuation failed: error_type=%s error=%s",
                            type(exc).__name__,
                            exc,
                        )
                        finish_reason = turn.finish_reason or "length"
                    break
                if not answer.strip() and total_tool_calls > 0:
                    try:
                        final_prompt_messages, final_budget_metadata = self._build_prompt(
                            transcript, force_final=True
                        )
                    except ContextOverflowError as exc:
                        self._set_final_result(
                            self._error_result(
                                "context_overflow",
                                exc,
                                transcript,
                                compressed,
                                total_tool_calls,
                                total_tokens,
                            )
                        )
                        return
                    compressed = compressed or bool(final_budget_metadata.get("compressed"))
                    compressed_reason.extend(final_budget_metadata.get("compressed_reason") or [])
                    truncated_observations += int(final_budget_metadata.get("truncated_observations") or 0)
                    summarized_messages += int(final_budget_metadata.get("summarized_messages") or 0)
                    event = ModelStarted(
                        iteration=iteration,
                        tools_enabled=False,
                        stream_mode=self.config.stream,
                        force_final=True,
                    )
                    self.events.append(event)
                    try:
                        final_turn = None
                        for event in self._model_events(final_prompt_messages, force_final=True, iteration=iteration):
                            if isinstance(event, AssistantTurnCompleted):
                                final_turn = event.turn
                            else:
                                yield event
                        if final_turn is None:
                            raise RuntimeError("model stream finished without assistant turn")
                    except Exception as exc:
                        self._set_final_result(self._error_result(classify_error(exc), exc, transcript, compressed, total_tool_calls, total_tokens))
                        return
                    total_tokens += int(final_turn.usage.get("total_tokens") or 0)
                    transcript.append(assistant_message(final_turn))
                    answer = final_turn.text or "工具已执行，但模型没有返回最终回答。"
                    if not final_turn.text:
                        yield from self._write("write_text_delta", answer, iteration=iteration)
                    finish_reason = final_turn.finish_reason or "final"
                    break
                finish_reason = turn.finish_reason or "final"
                break

            for tool_call in turn.tool_calls:
                yield from self._write("write_tool_call", tool_call.id, tool_call.name, tool_call.arguments)

            tool_started = time.perf_counter()
            scheduled_results = self.scheduler.execute(turn.tool_calls, iteration)
            self._record_timing("tool_ms", tool_started, iteration=iteration)
            self._tool_batch_truncated = self._tool_batch_truncated or any(
                bool((scheduled.result.metadata or {}).get("batch_truncated"))
                for scheduled in scheduled_results
            )
            for scheduled in scheduled_results:
                tool_call = scheduled.tool_call
                result = scheduled.result
                total_tool_calls += 1
                for scheduled_event in scheduled.events:
                    self.events.append(scheduled_event)
                tool_metadata = _safe_tool_metadata(result.metadata)
                yield from self._write(
                    "write_tool_result",
                    result.tool_call_id,
                    result.tool_name,
                    result.llm_observation,
                    output=tool_metadata.get("output"),
                    is_error=result.is_error,
                    metadata=tool_metadata,
                )
                yield from self._tool_activity_events(result)
                for display_message in result.display_messages:
                    if isinstance(display_message, dict) and display_message.get("type") == "dify_blob":
                        yield display_message
                transcript.append(tool_message(result))
                if result.metadata.get("inject_user_message"):
                    yield from self._write(
                        "write_activity",
                        "cc_agent.skill_apply",
                        _drop_none(
                            {
                                "toolName": result.tool_name,
                                "toolCallId": result.tool_call_id,
                                "skillName": result.metadata.get("skill_name"),
                                "text": result.metadata.get("injected_message") or result.llm_observation,
                            }
                        ),
                    )
                    transcript.append(
                        {
                            "role": "user",
                            "content": result.metadata.get("injected_message") or result.llm_observation,
                            "metadata": {"internal": True, "source_tool": result.tool_name},
                        }
                    )
                if result.metadata.get("requires_user_input"):
                    raw_question = result.metadata.get("question") or result.llm_observation
                    if isinstance(raw_question, dict):
                        awaiting_user_question = {
                            **raw_question,
                            "tool_call_id": raw_question.get("tool_call_id") or result.tool_call_id,
                            "tool_name": raw_question.get("tool_name") or result.tool_name,
                        }
                    else:
                        question_text = str(raw_question)
                        awaiting_user_question = {
                            "id": result.tool_call_id,
                            "question": question_text,
                            "text": question_text,
                            "purpose": "clarification",
                            "options": [],
                            "multiSelect": False,
                            "allowCustomInput": True,
                            "tool_call_id": result.tool_call_id,
                            "tool_name": result.tool_name,
                        }
                    answer = str(awaiting_user_question["question"])
                    finish_reason = "awaiting_user"
                    break
            if awaiting_user_question:
                break
            logger.info(
                "cc_agent tool iteration completed: iteration=%s tool_calls=%s transcript_count=%s awaiting_user=%s",
                iteration,
                len(turn.tool_calls),
                len(transcript),
                bool(awaiting_user_question),
            )
            finish_reason = "tool_calls"
        else:
            finish_reason = "max_iterations"
            final_iteration = self.config.maximum_iterations + 1
            try:
                prompt_messages, budget_metadata = self._build_prompt(transcript, force_final=True)
            except ContextOverflowError as exc:
                self._set_final_result(
                    self._error_result(
                        "context_overflow",
                        exc,
                        transcript,
                        compressed,
                        total_tool_calls,
                        total_tokens,
                    )
                )
                return
            compressed = compressed or bool(budget_metadata.get("compressed"))
            event = ModelStarted(
                iteration=final_iteration,
                tools_enabled=False,
                stream_mode=self.config.stream,
                force_final=True,
            )
            self.events.append(event)
            try:
                final_turn = None
                for event in self._model_events(prompt_messages, force_final=True, iteration=final_iteration):
                    if isinstance(event, AssistantTurnCompleted):
                        final_turn = event.turn
                    else:
                        yield event
                if final_turn is None:
                    raise RuntimeError("model stream finished without assistant turn")
            except Exception as exc:
                self._set_final_result(self._error_result(classify_error(exc), exc, transcript, compressed, total_tool_calls, total_tokens))
                return
            total_tokens += int(final_turn.usage.get("total_tokens") or 0)
            answer = final_turn.text or "Maximum iteration limit reached before a final answer was produced."
            if not final_turn.text:
                yield from self._write("write_text_delta", answer, iteration=final_iteration)
            event = ModelEnded(iteration=final_iteration, text=answer, tool_calls=[], force_final=True)
            self.events.append(event)
            transcript.append(assistant_message(AssistantTurn(text=answer, usage=final_turn.usage, finish_reason="max_iterations")))

        self.state.history = sanitize_history(transcript)
        metadata = {
            "finish_reason": finish_reason,
            "iterations": min(self.config.maximum_iterations, len([e for e in self.events if isinstance(e, LoopIteration)])),
            "tool_calls": total_tool_calls,
            "compressed": compressed,
            "compressed_reason": list(dict.fromkeys(compressed_reason)),
            "truncated_observations": truncated_observations,
            "summarized_messages": summarized_messages,
            "total_tokens": total_tokens,
            "model_features": self.config.model_features or [],
            "stream_mode": self.config.stream,
            "tool_call_supported": self.config.tool_call_supported,
            "context_overflow_detected": context_overflow_detected,
            "context_retry_count": context_retry_count,
            "context_error_numbers": list(dict.fromkeys(context_error_numbers)),
            "continuation_count": continuation_count,
            "compaction_failures": int(getattr(self.summarizer, "failure_count", 0) or 0),
            "tool_batch_truncated": self._tool_batch_truncated,
            **self._budget_execution_metadata(),
            **self._timing_metadata(),
        }
        if continuation_error:
            metadata["continuation_error"] = continuation_error
        if awaiting_user_question:
            metadata["question"] = awaiting_user_question
        logger.info(
            "cc_agent loop finished: finish_reason=%s answer_chars=%s history_count=%s tool_calls=%s iterations=%s",
            finish_reason,
            len(str(answer or "")),
            len(self.state.history),
            total_tool_calls,
            metadata["iterations"],
        )
        self._set_final_result(
            AgentRunResult(
                answer=answer,
                history=self.state.history,
                memory=self.state.memory,
                tasks=self.state.tasks,
                permissions=self.state.permissions,
                active_skills=self.state.active_skills,
                execution_metadata=metadata,
                events=self.events,
                summary=self.state.summary,
                history_schema_version=self.state.history_version,
            )
        )

    def _build_prompt(
        self,
        transcript: list[dict[str, Any]],
        force_final: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        tools = self._model_tools(force_final)
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
                        dict.fromkeys([*combined_reasons, *(metadata.get("compressed_reason") or [])])
                    )
                    metadata["truncated_observations"] = (
                        combined_truncated + int(metadata.get("truncated_observations") or 0)
                    )
                    metadata["summarized_messages"] = (
                        combined_summarized + int(metadata.get("summarized_messages") or 0)
                    )
                    metadata["preflight_compactions"] = preflight_compactions
                    self._last_budget_metadata = dict(metadata)
                    return prompt, metadata
                if attempt >= 3:
                    break
                before = (len(transcript), estimate_context_tokens(transcript), self.state.summary)
                compacted = self._compact_transcript(transcript, force=True)
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
            self._last_budget_metadata = dict(metadata)
            raise ContextOverflowError(
                "CC Agent request exceeds the configured input budget before model invocation: "
                f"reason={reason}, estimated_tokens={metadata.get('request_estimated_tokens')}, "
                f"input_budget_tokens={metadata.get('input_budget_tokens')}"
            )
        finally:
            self._record_timing("prompt_build_ms", started)

    def _compact_transcript(self, transcript: list[dict[str, Any]], force: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = self.context_budget.compact_history(
                transcript,
                existing_summary=self.state.summary,
                summarizer=self.summarizer,
                force=force,
                max_summary_tokens=min(8192, max(512, self.context_budget.input_budget_tokens // 5)),
            )
            if result.metadata.get("compressed"):
                transcript[:] = result.messages
                self.state.summary = result.summary
            return result.metadata
        finally:
            self._record_timing("compaction_ms", started)

    def _should_compact_transcript(self, transcript: list[dict[str, Any]], force: bool = False) -> bool:
        if force:
            return True
        threshold = self.context_budget.input_budget_tokens
        return len(transcript) > self.context_budget.max_history_messages or estimate_context_tokens(transcript) > threshold

    def _compression_id(self, trigger: str, iteration: int) -> str:
        return f"compression:{trigger}:{iteration}"

    def _invoke_model(self, prompt_messages: list[dict[str, Any]], force_final: bool) -> AssistantTurn:
        return self.model_adapter.invoke(
            prompt_messages,
            self._model_tools(force_final),
            force_final=force_final,
        )

    def _model_events(self, prompt_messages: list[dict[str, Any]], force_final: bool, iteration: int):
        started = time.perf_counter()
        try:
            tools = self._model_tools(force_final)
            if hasattr(self.model_adapter, "invoke_stream"):
                events = self.model_adapter.invoke_stream(prompt_messages, tools, force_final=force_final)
            else:
                turn = self.model_adapter.invoke(prompt_messages, tools, force_final=force_final)
                stream_chunks = turn.stream_chunks or (
                    [TextDelta(text=turn.text)] if turn.text else []
                )
                events = [*stream_chunks, AssistantTurnCompleted(turn=turn)]
            seq = 0
            for event in events:
                if isinstance(event, AssistantTurnCompleted):
                    yield event
                    continue
                seq += 1
                if isinstance(event, TextDelta):
                    normalized = TextDelta(text=event.text, iteration=iteration, seq=seq)
                    yield from self._write("write_text_delta", normalized.text, iteration=iteration)
                    continue
                if isinstance(event, ThinkingDelta):
                    normalized = ThinkingDelta(text=event.text, iteration=iteration, seq=seq)
                    yield from self._write("write_reasoning_delta", normalized.text, iteration=iteration)
                    continue
                yield event
        finally:
            self._record_timing("model_ms", started, iteration=iteration)

    def _model_tools(self, force_final: bool) -> list[Any]:
        if force_final:
            return []
        tools = self.registry.prompt_tools()
        if not tools:
            return []
        return tools

    def _set_final_result(self, result: AgentRunResult) -> AgentRunResult:
        self.final_result = result
        return result

    def _tool_activity_events(self, result) -> list[dict[str, Any]]:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        events: list[dict[str, Any]] = []
        activity_type = metadata.get("activity_type")
        activity = metadata.get("activity")
        if activity_type and isinstance(activity, dict):
            events.extend(self._write("write_activity", str(activity_type), activity))
        if metadata.get("guard_rejected"):
            events.extend(
                self._write(
                    "write_activity",
                    "cc_agent.guard_triggered",
                    {
                        "toolName": result.tool_name,
                        "toolCallId": result.tool_call_id,
                        "observation": result.llm_observation,
                        "level": "block",
                        "guardName": "tool_guard",
                    },
                )
            )
        return events

    def _reactive_compact(self, prompt_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": self.prompt_builder.system_prompt()}]
        summary = limit_text_to_tokens(
            self.state.summary,
            min(8192, max(512, self.context_budget.input_budget_tokens // 5)),
        )
        if summary:
            messages.append({"role": "system", "content": f"Conversation summary:\n{summary}"})
        messages.append({"role": "user", "content": self.config.query})
        prepared, metadata = self.context_budget.prepare(
            messages,
            tools=self._model_tools(force_final=False),
        )
        if metadata.get("request_over_budget"):
            raise ContextOverflowError(
                "Reactive compact request still exceeds the configured input budget: "
                f"estimated_tokens={metadata.get('request_estimated_tokens')}, "
                f"input_budget_tokens={metadata.get('input_budget_tokens')}"
            )
        return prepared

    def _record_timing(self, key: str, started: float, iteration: int = 0) -> float:
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._timings_ms[key] = self._timings_ms.get(key, 0.0) + elapsed_ms
        if elapsed_ms >= SLOW_PHASE_THRESHOLD_MS:
            logger.warning(
                "cc_agent slow phase: phase=%s duration_ms=%.3f iteration=%s",
                key,
                elapsed_ms,
                iteration,
            )
        return elapsed_ms

    def _timing_metadata(self) -> dict[str, float]:
        return {key: round(value, 3) for key, value in self._timings_ms.items()}

    def _budget_execution_metadata(self) -> dict[str, int | bool]:
        metadata = self._last_budget_metadata
        return {
            "request_estimated_tokens": int(metadata.get("request_estimated_tokens") or 0),
            "input_budget_tokens": int(metadata.get("input_budget_tokens") or 0),
            "static_context_tokens": int(metadata.get("static_context_tokens") or 0),
            "request_over_budget": bool(metadata.get("request_over_budget")),
        }

    def _error_result(
        self,
        finish_reason: str,
        exc: Exception,
        transcript: list[dict[str, Any]],
        compressed: bool,
        total_tool_calls: int,
        total_tokens: int,
    ) -> AgentRunResult:
        self.events.append(ModelError(message=str(exc), finish_reason=finish_reason, error=exc))
        self.state.history = sanitize_history(transcript)
        return AgentRunResult(
            answer="",
            history=self.state.history,
            memory=self.state.memory,
            tasks=self.state.tasks,
            permissions=self.state.permissions,
            active_skills=self.state.active_skills,
            execution_metadata={
                "finish_reason": finish_reason,
                "iterations": len([e for e in self.events if isinstance(e, LoopIteration)]),
                "tool_calls": total_tool_calls,
                "compressed": compressed,
                "compressed_reason": [],
                "truncated_observations": 0,
                "summarized_messages": 0,
                "total_tokens": total_tokens,
                "model_features": self.config.model_features or [],
                "stream_mode": self.config.stream,
                "tool_call_supported": self.config.tool_call_supported,
                "error": str(exc),
                "compaction_failures": int(getattr(self.summarizer, "failure_count", 0) or 0),
                "tool_batch_truncated": self._tool_batch_truncated,
                **self._budget_execution_metadata(),
                **self._timing_metadata(),
            },
            events=self.events,
            summary=self.state.summary,
            history_schema_version=self.state.history_version,
        )


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _is_truncated_finish_reason(value: Any) -> bool:
    return str(value or "").strip().lower() in TRUNCATED_FINISH_REASONS


def _safe_tool_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    safe = {key: value for key, value in metadata.items() if key != "artifacts"}
    artifacts = metadata.get("artifacts")
    if isinstance(artifacts, list):
        safe["artifacts"] = [
            {
                key: artifact.get(key)
                for key in ("name", "path", "mime_type", "size", "status", "download_url", "expires_at")
                if isinstance(artifact, dict) and artifact.get(key) not in (None, "")
            }
            for artifact in artifacts
            if isinstance(artifact, dict)
        ]
    return safe


def _compression_activity(
    status: str,
    trigger: str,
    compression_id: str,
    metadata: dict[str, Any] | None = None,
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
