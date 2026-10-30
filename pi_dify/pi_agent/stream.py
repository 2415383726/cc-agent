"""Dify-backed ``StreamFn`` for the Pi core loop.

Only this module talks to the Dify model SDK. It translates Dify text, real
reasoning fields, complete tool-call streams, usage and the necessary
non-stream fallback into Pi ``AssistantMessageEventStream`` values.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from pi_agent_core.event_stream import AssistantMessageEventStream
from pi_agent_core.messages import AssistantMessage, Usage
from pi_agent_core.types import (
    DoneEvent,
    ErrorEvent,
    LlmContext,
    Model,
    StartEvent,
    StreamOptions,
    TextDeltaEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)

from .budget import RunLedger, estimate_text_tokens
from .config import RuntimeConfig
from .errors import BudgetExceeded, ContextOverflow, ContextTooLarge

try:  # pragma: no cover - Dify SDK is present inside the plugin runtime
    from dify_plugin.entities.model.llm import LLMModelConfig
    from dify_plugin.entities.model.message import (
        AssistantPromptMessage,
        PromptMessageTool,
        SystemPromptMessage,
        ToolPromptMessage,
        UserPromptMessage,
    )
except Exception:  # pragma: no cover
    LLMModelConfig = None
    AssistantPromptMessage = None
    PromptMessageTool = None
    SystemPromptMessage = None
    ToolPromptMessage = None
    UserPromptMessage = None


OVERFLOW_PATTERNS = (
    "context length",
    "context_length_exceeded",
    "maximum context",
    "max context",
    "prompt is too long",
    "too many tokens",
    "reduce the length",
    "token limit",
    "exceeds the model",
    "input is too long",
    "request too large",
)
ERROR_MARKER = "pi_error:"


class _AbortedError(Exception):
    pass


@dataclass(slots=True)
class _DraftCall:
    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""
    started: bool = False


@dataclass(slots=True)
class ToolCallAccumulator:
    mode: str = "delta"
    drafts: dict[str, _DraftCall] = field(default_factory=dict)
    index_keys: dict[int, str] = field(default_factory=dict)
    id_keys: dict[str, str] = field(default_factory=dict)
    malformed_identity: bool = False

    def add_delta(self, tool_calls: list[Any] | None) -> list[tuple[str, _DraftCall, str]]:
        """Return ``(key, draft, raw_fragment)`` for newly observed fragments."""

        observed: list[tuple[str, _DraftCall, str]] = []
        for position, raw in enumerate(tool_calls or []):
            index = _int(_get(raw, "index"), position)
            raw_id = str(_get(raw, "id") or "")
            key = self.id_keys.get(raw_id) or self.index_keys.get(index) or ""
            if key and raw_id and self.drafts[key].id not in {"", raw_id}:
                if _get(raw, "index") is not None:
                    self.malformed_identity = True
                    continue
                key = ""
            key = key or raw_id or f"index:{index}"
            draft = self.drafts.setdefault(key, _DraftCall(index=index, id=raw_id))
            self.index_keys[index] = key
            if raw_id:
                draft.id = raw_id
                self.id_keys[raw_id] = key
            function = _get(raw, "function", {}) or {}
            name_part = str(_get(function, "name") or "")
            arguments_part = _get(function, "arguments")
            fragment = ""
            if name_part:
                draft.name = name_part if self.mode == "snapshot" else draft.name + name_part
                fragment += name_part
            if arguments_part is not None:
                text = (
                    json.dumps(arguments_part, ensure_ascii=False)
                    if isinstance(arguments_part, (dict, list))
                    else str(arguments_part)
                )
                draft.arguments = text if self.mode == "snapshot" else draft.arguments + text
                fragment += text
            observed.append((key, draft, fragment))
        return observed

    def finalize(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        calls: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        for draft in sorted(self.drafts.values(), key=lambda item: item.index):
            if not draft.name:
                invalid.append({"index": draft.index, "reason": "missing_tool_name"})
                continue
            parsed = _parse_arguments(draft.arguments)
            if parsed is None:
                invalid.append(
                    {"index": draft.index, "name": draft.name, "reason": "invalid_arguments"}
                )
                continue
            calls.append(
                {
                    "type": "toolCall",
                    "id": draft.id or f"call_{draft.index}",
                    "name": draft.name,
                    "arguments": parsed,
                }
            )
        if self.malformed_identity:
            invalid.append({"index": -1, "reason": "conflicting_tool_identity"})
        return calls, invalid


class ThinkingTagSplitter:
    """Split provider-emitted ``<think>`` blocks when no reasoning field is sent."""

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self) -> None:
        self.buffer = ""
        self.inside = False

    def feed(self, content: str) -> list[tuple[str, str]]:
        if not content:
            return []
        self.buffer += content
        return self._drain(final=False)

    def flush(self) -> list[tuple[str, str]]:
        return self._drain(final=True)

    def _drain(self, final: bool) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        while self.buffer:
            if self.inside:
                index = self.buffer.find(self.CLOSE)
                if index >= 0:
                    if index:
                        events.append(("thinking", self.buffer[:index]))
                    self.buffer = self.buffer[index + len(self.CLOSE) :]
                    self.inside = False
                    continue
                emit, keep = _split_partial_marker(self.buffer, self.CLOSE, final)
                if emit:
                    events.append(("thinking", emit))
                self.buffer = keep
                break
            index = self.buffer.find(self.OPEN)
            if index >= 0:
                if index:
                    events.append(("text", self.buffer[:index]))
                self.buffer = self.buffer[index + len(self.OPEN) :]
                self.inside = True
                continue
            emit, keep = _split_partial_marker(self.buffer, self.OPEN, final)
            if emit:
                events.append(("text", emit))
            self.buffer = keep
            break
        return events


class DifyModelStream:
    """Callable ``StreamFn`` bound to one Dify request and one ledger."""

    def __init__(
        self,
        *,
        session: Any,
        model_config: Any,
        ledger: RunLedger,
        config: RuntimeConfig,
        model: Model | None = None,
        thinking_tags: bool = True,
        preserve_reasoning_content: bool = False,
        stop_requested: Any = None,
    ) -> None:
        self.session = session
        self.model_config = model_config
        self.ledger = ledger
        self.config = config
        self.model = model
        self.thinking_tags = thinking_tags
        self.preserve_reasoning_content = preserve_reasoning_content
        self.stop_requested = stop_requested or (lambda: False)
        self._producers: set[asyncio.Task] = set()

    async def __call__(
        self, model: Model, context: LlmContext, options: StreamOptions | None = None
    ) -> AssistantMessageEventStream:
        self.model = model
        prompt_messages = _to_prompt_messages(
            context, preserve_reasoning_content=self.preserve_reasoning_content
        )
        prompt_tools = _to_prompt_tools(context.tools or [])
        fixed_tokens = (
            estimate_text_tokens(context.system_prompt or "")
            + estimate_text_tokens(json.dumps(_tool_schema_json(context.tools or []), default=str))
            + self.config.reserved_output_tokens
        )
        history_tokens = sum(_message_tokens(message) for message in context.messages)
        total_estimate = fixed_tokens + history_tokens
        if fixed_tokens >= self.config.context_window:
            return _error_stream(model, "context_too_large", options, usage=None)
        if total_estimate >= self.config.context_window:
            return _error_stream(model, "context_overflow", options, usage=None)
        stream = AssistantMessageEventStream()
        producer = asyncio.create_task(
            self._produce(stream, model, prompt_messages, prompt_tools, options, total_estimate)
        )
        self._producers.add(producer)
        producer.add_done_callback(self._producers.discard)
        return stream

    def _check_stop(self, options: StreamOptions | None) -> None:
        if self.stop_requested() or (
            options is not None
            and options.signal is not None
            and getattr(options.signal, "aborted", False)
        ):
            raise _AbortedError()

    async def close(self) -> None:
        tasks = list(self._producers)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _produce(
        self,
        stream: AssistantMessageEventStream,
        model: Model,
        prompt_messages: list[Any],
        prompt_tools: list[Any],
        options: StreamOptions | None,
        total_estimate: int,
    ) -> None:
        try:
            self._check_stop(options)
            self.ledger.before_model(total_estimate)
            if self.config.stream_mode == "nonstream":
                await self._nonstream(
                    model, prompt_messages, prompt_tools, options, total_estimate, output=stream
                )
                return
            try:
                response = self._invoke(prompt_messages, prompt_tools, stream=True)
            except Exception as exc:
                self.ledger.record_model(None, total_estimate, source="stream_failed")
                if self.config.stream_fallback and not _is_overflow(exc):
                    self._check_stop(options)
                    self.ledger.before_model(total_estimate)
                    await self._nonstream(
                        model,
                        prompt_messages,
                        prompt_tools,
                        options,
                        total_estimate,
                        fallback=True,
                        output=stream,
                    )
                else:
                    _error_stream(model, _marker_for(exc), options, usage=None, stream=stream)
                return
            await self._consume(stream, response, model, options, total_estimate)
        except BudgetExceeded as exc:
            self.ledger.mark(exc.reason)
            _error_stream(model, "budget_exhausted", options, usage=None, stream=stream)
        except (_AbortedError, asyncio.CancelledError):
            _error_stream(model, "aborted", options, usage=None, stream=stream)
        except Exception:
            _error_stream(model, "provider_failed", options, usage=None, stream=stream)

    async def _nonstream(
        self,
        model: Model,
        prompt_messages: list[Any],
        prompt_tools: list[Any],
        options: StreamOptions | None,
        estimated_tokens: int,
        *,
        fallback: bool = False,
        output: AssistantMessageEventStream | None = None,
    ) -> AssistantMessageEventStream:
        stream = output if output is not None else AssistantMessageEventStream()
        try:
            response = self._invoke(prompt_messages, prompt_tools, stream=False)
            final = _message_from_nonstream(response, model)
            self.ledger.record_model(
                final.usage,
                estimated_tokens,
                source="nonstream_fallback" if fallback else "nonstream",
            )
            _emit_start(stream, final)
            stream.set_final_message(final)
            stream.push(DoneEvent(partial=final, reason="toolUse" if _has_calls(final) else "stop"))
            return stream
        except Exception as exc:
            self.ledger.record_model(None, estimated_tokens, source="nonstream_failed")
            return _error_stream(model, _marker_for(exc), options, usage=None, stream=stream)

    def _invoke(self, prompt_messages: list[Any], prompt_tools: list[Any], *, stream: bool) -> Any:
        return self.session.model.llm.invoke(
            model_config=_model_config(self.model_config),
            prompt_messages=prompt_messages,
            tools=prompt_tools or None,
            stop=None,
            stream=stream,
        )

    async def _consume(
        self,
        stream: AssistantMessageEventStream,
        response: Any,
        model: Model,
        options: StreamOptions | None,
        estimated_tokens: int = 0,
    ) -> AssistantMessage:
        blocks: list[dict[str, Any]] = []
        accumulator = ToolCallAccumulator(mode=self.config.tool_stream_mode)
        splitter = ThinkingTagSplitter() if self.thinking_tags else None
        usage = Usage()
        text_open = False
        thinking_open = False
        saw_reasoning_field = False
        partial = AssistantMessage(
            content=[], api=model.api, provider=model.provider, model=model.model_id
        )
        _emit_start(stream, partial)

        def sync_partial() -> AssistantMessage:
            nonlocal partial
            partial = AssistantMessage(
                content=[dict(block) for block in blocks],
                api=model.api,
                provider=model.provider,
                model=model.model_id,
                usage=usage,
            )
            return partial

        def push_text(text: str) -> None:
            nonlocal text_open, thinking_open
            if not text:
                return
            if thinking_open:
                thinking_open = False
            if not text_open:
                blocks.append({"type": "text", "text": ""})
                text_open = True
                stream.push(TextStartEvent(partial=sync_partial(), content_index=len(blocks) - 1))
            blocks[-1]["text"] += text
            stream.push(
                TextDeltaEvent(partial=sync_partial(), delta=text, content_index=len(blocks) - 1)
            )

        def push_thinking(text: str) -> None:
            nonlocal thinking_open, text_open
            if not text:
                return
            if text_open:
                text_open = False
            if not thinking_open:
                blocks.append({"type": "thinking", "thinking": ""})
                thinking_open = True
                stream.push(
                    ThinkingStartEvent(partial=sync_partial(), content_index=len(blocks) - 1)
                )
            blocks[-1]["thinking"] += text
            stream.push(
                ThinkingDeltaEvent(
                    partial=sync_partial(), delta=text, content_index=len(blocks) - 1
                )
            )

        tool_started: dict[str, int] = {}
        try:
            for chunk in response:
                self._check_stop(options)
                delta = _get(chunk, "delta", chunk)
                message = _get(delta, "message", delta) or delta
                reasoning = _get(message, "reasoning_content")
                if reasoning is None:
                    reasoning = _get(message, "reasoning")
                if reasoning:
                    saw_reasoning_field = True
                    push_thinking(str(reasoning))
                content = _content_to_text(_get(message, "content"))
                if content:
                    if splitter is not None and not saw_reasoning_field:
                        for kind, piece in splitter.feed(content):
                            if kind == "thinking":
                                push_thinking(piece)
                            else:
                                push_text(piece)
                    else:
                        push_text(content)
                for key, draft, fragment in accumulator.add_delta(_get(message, "tool_calls")):
                    if key not in tool_started:
                        tool_started[key] = draft.index
                        stream.push(
                            ToolCallStartEvent(
                                partial=sync_partial(),
                                content_index=len(blocks),
                                tool_call_index=draft.index,
                            )
                        )
                    if fragment:
                        stream.push(
                            ToolCallDeltaEvent(
                                partial=sync_partial(),
                                delta=fragment,
                                content_index=len(blocks),
                                tool_call_index=draft.index,
                            )
                        )
                usage = _merge_usage(usage, _get(delta, "usage") or _get(chunk, "usage"))
                # Let the harness consume queued deltas and the stop watcher run
                # before asking a synchronous provider for its next chunk.
                await asyncio.sleep(0)
            self._check_stop(options)
            if splitter is not None:
                for kind, piece in splitter.flush():
                    if kind == "thinking":
                        push_thinking(piece)
                    else:
                        push_text(piece)
        except Exception as exc:
            aborted = isinstance(exc, _AbortedError)
            marker = "aborted" if aborted else _marker_for(exc)
            self.ledger.record_model(usage, estimated_tokens, source="stream_error")
            final = AssistantMessage(
                content=[dict(block) for block in blocks],
                api=model.api,
                provider=model.provider,
                model=model.model_id,
                usage=usage,
                stopReason="aborted" if aborted else "error",
                errorMessage=f"{ERROR_MARKER}{marker}",
            )
            stream.set_final_message(final)
            stream.push(
                ErrorEvent(
                    partial=final,
                    reason="aborted" if aborted else "error",
                    error_message=final.errorMessage,
                )
            )
            return final

        calls, invalid = accumulator.finalize()
        if invalid:
            notes = []
            for item in invalid:
                if item.get("name"):
                    notes.append(f"Invalid arguments for tool {item['name']} were not executed.")
                elif item.get("reason") == "conflicting_tool_identity":
                    notes.append("Conflicting tool call identities were not executed.")
                else:
                    notes.append("A malformed tool call was not executed.")
            push_text("\n" + " ".join(dict.fromkeys(notes)))
        for call in calls:
            blocks.append(call)
            index = len(blocks) - 1
            stream.push(
                ToolCallEndEvent(
                    partial=sync_partial(),
                    tool_call=call,
                    content_index=index,
                    tool_call_index=index,
                )
            )
        final = AssistantMessage(
            content=[dict(block) for block in blocks],
            api=model.api,
            provider=model.provider,
            model=model.model_id,
            usage=usage,
            stopReason="toolUse" if calls else "stop",
        )
        self.ledger.record_model(usage, estimated_tokens, source="stream")
        stream.set_final_message(final)
        stream.push(DoneEvent(partial=final, reason="toolUse" if calls else "stop"))
        return final


def _emit_start(stream: AssistantMessageEventStream, partial: AssistantMessage) -> None:
    stream.push(StartEvent(partial=partial))


def _error_stream(
    model: Model,
    marker: str,
    options: StreamOptions | None,
    *,
    usage: Usage | None,
    stream: AssistantMessageEventStream | None = None,
) -> AssistantMessageEventStream:
    stream = stream if stream is not None else AssistantMessageEventStream()
    final = AssistantMessage(
        content=[{"type": "text", "text": ""}],
        api=model.api,
        provider=model.provider,
        model=model.model_id,
        usage=usage or Usage(),
        stopReason="aborted" if marker == "aborted" else "error",
        errorMessage=f"{ERROR_MARKER}{marker}",
    )
    stream.set_final_message(final)
    stream.push(
        ErrorEvent(partial=final, reason=final.stopReason, error_message=final.errorMessage)
    )
    return stream


def _marker_for(exc: Exception) -> str:
    if isinstance(exc, BudgetExceeded):
        return "budget_exhausted"
    if isinstance(exc, ContextTooLarge):
        return "context_too_large"
    if isinstance(exc, ContextOverflow) or _is_overflow(exc):
        return "context_overflow"
    return "provider_failed"


def _is_overflow(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(pattern in text for pattern in OVERFLOW_PATTERNS)


def error_code_from_message(message: AssistantMessage) -> str | None:
    raw = str(message.errorMessage or "")
    if raw.startswith(ERROR_MARKER):
        return raw[len(ERROR_MARKER) :]
    return None


def _has_calls(message: AssistantMessage) -> bool:
    return any(
        isinstance(block, dict) and block.get("type") == "toolCall" for block in message.content
    )


def _message_from_nonstream(response: Any, model: Model) -> AssistantMessage:
    message = _get(response, "message", response) or response
    blocks: list[dict[str, Any]] = []
    reasoning = _get(message, "reasoning_content")
    if reasoning:
        blocks.append({"type": "thinking", "thinking": str(reasoning)})
    content = _content_to_text(_get(message, "content"))
    if content:
        blocks.append({"type": "text", "text": content})
    accumulator = ToolCallAccumulator(mode="snapshot")
    accumulator.add_delta(_get(message, "tool_calls"))
    calls, _invalid = accumulator.finalize()
    blocks.extend(calls)
    return AssistantMessage(
        content=blocks,
        api=model.api,
        provider=model.provider,
        model=model.model_id,
        usage=_merge_usage(Usage(), _get(response, "usage") or _get(message, "usage")),
        stopReason="toolUse" if calls else "stop",
    )


def _to_prompt_messages(context: LlmContext, *, preserve_reasoning_content: bool) -> list[Any]:
    converted: list[Any] = []
    if context.system_prompt and SystemPromptMessage is not None:
        converted.append(SystemPromptMessage(content=context.system_prompt))
    for message in context.messages:
        role = getattr(message, "role", None)
        if role == "user":
            converted.append(UserPromptMessage(content=_text_of(message.content)))
        elif role == "assistant":
            tool_calls = [
                _to_dify_tool_call(block)
                for block in message.content
                if isinstance(block, dict) and block.get("type") == "toolCall"
            ]
            text = "".join(
                str(block.get("text") or "")
                for block in message.content
                if isinstance(block, dict) and block.get("type") == "text"
            )
            thinking = "".join(
                str(block.get("thinking") or "")
                for block in message.content
                if isinstance(block, dict) and block.get("type") == "thinking"
            )
            if preserve_reasoning_content and thinking and tool_calls:
                converted.append(
                    {
                        "role": "assistant",
                        "content": text,
                        "tool_calls": [
                            call.model_dump(mode="json") if hasattr(call, "model_dump") else call
                            for call in tool_calls
                        ],
                        "reasoning_content": thinking,
                    }
                )
            elif AssistantPromptMessage is not None:
                converted.append(AssistantPromptMessage(content=text, tool_calls=tool_calls))
        elif role == "toolResult" and ToolPromptMessage is not None:
            converted.append(
                ToolPromptMessage(
                    content=_text_of(message.content),
                    tool_call_id=str(getattr(message, "toolCallId", "") or ""),
                    name=str(getattr(message, "toolName", "") or ""),
                )
            )
    return converted


def _to_prompt_tools(tools: list[Any]) -> list[Any]:
    if PromptMessageTool is None:
        return []
    result = []
    for tool in tools:
        parameters = getattr(tool, "parameters", None) or {"type": "object", "properties": {}}
        result.append(
            PromptMessageTool(
                name=str(getattr(tool, "name", "")),
                description=str(getattr(tool, "description", "") or ""),
                parameters=parameters if isinstance(parameters, dict) else {"type": "object"},
            )
        )
    return result


def _to_dify_tool_call(block: dict[str, Any]) -> Any:
    if AssistantPromptMessage is None:
        return block
    function = AssistantPromptMessage.ToolCall.ToolCallFunction(
        name=str(block.get("name") or ""),
        arguments=json.dumps(block.get("arguments") or {}, ensure_ascii=False),
    )
    return AssistantPromptMessage.ToolCall(
        id=str(block.get("id") or ""), type="function", function=function
    )


def _model_config(value: Any) -> Any:
    if LLMModelConfig is None:
        return value
    if isinstance(value, LLMModelConfig):
        return value
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    elif isinstance(value, dict):
        payload = dict(value)
    else:
        return value
    payload.pop("history_prompt_messages", None)
    if not {"model", "provider", "mode"}.issubset(payload):
        return value
    return LLMModelConfig(**payload)


def _tool_schema_json(tools: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": getattr(tool, "name", ""),
            "description": getattr(tool, "description", ""),
            "parameters": getattr(tool, "parameters", {}),
        }
        for tool in tools
    ]


def _message_tokens(message: Any) -> int:
    total = 0
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return estimate_text_tokens(content)
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in {"text", "thinking"}:
                    total += estimate_text_tokens(
                        str(block.get("text") or block.get("thinking") or "")
                    )
                elif block.get("type") == "toolCall":
                    total += estimate_text_tokens(
                        json.dumps(block.get("arguments") or {}, ensure_ascii=False, default=str)
                    )
    return total


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif block.get("type") == "image":
                    parts.append("[image attachment]")
        return "".join(parts)
    return str(content or "")


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("data") or item.get("content") or ""))
            else:
                # Dify TextPromptMessageContent stores text in ``data``.
                parts.append(
                    str(
                        getattr(item, "text", None)
                        or getattr(item, "data", None)
                        or getattr(item, "content", None)
                        or ""
                    )
                )
        return "".join(parts)
    return str(content or "")


def _parse_arguments(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def _merge_usage(current: Usage, raw: Any) -> Usage:
    if not raw:
        return current
    data = (
        raw
        if isinstance(raw, dict)
        else (raw.model_dump(mode="json") if hasattr(raw, "model_dump") else {})
    )
    if not data:
        return current
    input_tokens = _int(data.get("prompt_tokens") or data.get("input_tokens"), current.input)
    output_tokens = _int(data.get("completion_tokens") or data.get("output_tokens"), current.output)
    total = _int(data.get("total_tokens"), 0)
    details = data.get("completion_tokens_details") or {}
    reasoning = _int(
        details.get("reasoning_tokens") if isinstance(details, dict) else None,
        current.reasoningTokens,
    )
    prompt_details = data.get("prompt_tokens_details") or {}
    cached = _int(
        prompt_details.get("cached_tokens") if isinstance(prompt_details, dict) else None,
        current.cacheRead,
    )
    return Usage(
        input=max(current.input, input_tokens),
        output=max(current.output, output_tokens),
        cacheRead=max(current.cacheRead, cached),
        cacheWrite=current.cacheWrite,
        totalTokens=max(current.totalTokens, total or input_tokens + output_tokens),
        reasoningTokens=max(current.reasoningTokens, reasoning),
        cost=current.cost,
    )


def _split_partial_marker(buffer: str, marker: str, final: bool) -> tuple[str, str]:
    if final:
        return buffer, ""
    max_prefix = min(len(buffer), len(marker) - 1)
    for size in range(max_prefix, 0, -1):
        if marker.startswith(buffer[-size:]):
            return buffer[:-size], buffer[-size:]
    return buffer, ""


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
