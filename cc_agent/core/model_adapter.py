from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .messages import AssistantTurn, ToolCall
from .model_stream import AssistantTurnCompleted, TextDelta, ThinkingDelta
from .run_budget import RunBudget

try:  # pragma: no cover - exercised inside Dify runtime
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

try:  # pragma: no cover - only present under Dify plugin runtime
    from dify_plugin.config.logger_format import plugin_logger_handler
except Exception:  # pragma: no cover
    plugin_logger_handler = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if plugin_logger_handler is not None and plugin_logger_handler not in logger.handlers:
    logger.addHandler(plugin_logger_handler)


@dataclass(slots=True)
class _DraftToolCall:
    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class StreamToolCallAccumulator:
    mode: str = "delta"
    drafts: dict[str, _DraftToolCall] = field(default_factory=dict)
    index_keys: dict[int, str] = field(default_factory=dict)
    id_keys: dict[str, str] = field(default_factory=dict)

    def add_delta(self, tool_calls: list[Any] | None) -> None:
        for position, raw_tool_call in enumerate(tool_calls or []):
            index = _int_or_default(_get(raw_tool_call, "index"), position)
            raw_id = str(_get(raw_tool_call, "id") or "")
            if not raw_id and _get(raw_tool_call, "index") is None and len(self.drafts) > 1:
                raise ValueError(
                    "A tool fragment must identify its call when multiple calls are active."
                )
            key = self.id_keys.get(raw_id, "") or self.index_keys.get(index, "")
            if key and raw_id and self.drafts[key].id not in {"", raw_id}:
                if _get(raw_tool_call, "index") is not None:
                    raise ValueError("Conflicting tool call identities for one stream index.")
                key = ""
            key = key or raw_id or f"index:{index}"
            draft = self.drafts.setdefault(key, _DraftToolCall(index=index, id=raw_id))
            self.index_keys[index] = key
            if raw_id:
                draft.id = raw_id
                self.id_keys[raw_id] = key
            function = _get(raw_tool_call, "function", {})
            name_part = str(_get(function, "name") or "")
            arguments_part = _get(function, "arguments")
            if name_part:
                if self.mode == "snapshot":
                    draft.name = name_part
                else:
                    draft.name += name_part
            if arguments_part is not None:
                if self.mode == "snapshot":
                    draft.arguments = str(arguments_part)
                else:
                    draft.arguments += str(arguments_part)

    def finalize(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for draft in sorted(self.drafts.values(), key=lambda item: item.index):
            if not draft.name:
                continue
            parsed_arguments, raw_arguments = _parse_tool_arguments(draft.arguments)
            calls.append(
                ToolCall(
                    id=draft.id or f"call_{draft.index}",
                    name=draft.name,
                    arguments=parsed_arguments,
                    raw_arguments=raw_arguments,
                )
            )
        return calls


class StreamContentSplitter:
    THINK_OPEN = "<think>"
    THINK_CLOSE = "</think>"

    def __init__(self):
        self.buffer = ""
        self.in_thinking = False

    def feed(self, content: str) -> list[TextDelta | ThinkingDelta]:
        if not content:
            return []
        self.buffer += content
        return self._drain(final=False)

    def flush(self) -> list[TextDelta | ThinkingDelta]:
        return self._drain(final=True)

    def _drain(self, final: bool) -> list[TextDelta | ThinkingDelta]:
        events: list[TextDelta | ThinkingDelta] = []
        while self.buffer:
            if self.in_thinking:
                close_index = self.buffer.find(self.THINK_CLOSE)
                if close_index >= 0:
                    if close_index:
                        events.append(ThinkingDelta(text=self.buffer[:close_index]))
                    self.buffer = self.buffer[close_index + len(self.THINK_CLOSE) :]
                    self.in_thinking = False
                    continue
                emit, keep = _split_partial_marker(self.buffer, self.THINK_CLOSE, final)
                if emit:
                    events.append(ThinkingDelta(text=emit))
                self.buffer = keep
                break

            open_index = self.buffer.find(self.THINK_OPEN)
            if open_index >= 0:
                if open_index:
                    events.append(TextDelta(text=self.buffer[:open_index]))
                self.buffer = self.buffer[open_index + len(self.THINK_OPEN) :]
                self.in_thinking = True
                continue
            emit, keep = _split_partial_marker(self.buffer, self.THINK_OPEN, final)
            if emit:
                events.append(TextDelta(text=emit))
            self.buffer = keep
            break
        return events


class DifyModelAdapter:
    def __init__(
        self,
        session: Any,
        model_config: Any,
        stream: bool = True,
        deepseek_thinking_compat: bool = False,
        keep_dify_history: bool = False,
        tool_call_stream_mode: str = "delta",
        run_budget: RunBudget | None = None,
    ):
        self.session = session
        self.model_config = model_config
        self.stream = stream
        self.keep_dify_history = keep_dify_history
        self.deepseek_thinking_compat = deepseek_thinking_compat
        if tool_call_stream_mode not in {"delta", "snapshot"}:
            raise ValueError("tool_call_stream_mode must be delta or snapshot.")
        self.tool_call_stream_mode = tool_call_stream_mode
        self.run_budget = run_budget

    def invoke(
        self, messages: list[dict[str, Any]], tools: list[Any], force_final: bool = False
    ) -> AssistantTurn:
        prompt_messages = to_dify_prompt_messages(
            messages, preserve_reasoning_content=self.deepseek_thinking_compat
        )
        prompt_tools = [] if force_final else to_dify_prompt_tools(tools)
        model_config = self._model_config()
        logger.info(
            "cc_agent model invoke: %s",
            _model_invoke_summary(
                session=self.session,
                model_config=model_config,
                messages=prompt_messages,
                tools=prompt_tools,
                stream=self.stream,
                force_final=force_final,
                run_id=self.run_budget.run_id if self.run_budget else "",
            ),
        )
        try:
            response = self._invoke_llm(model_config, prompt_messages, prompt_tools)
            if self.stream:
                return self._collect_stream(response)
            return self._collect_result(response)
        except Exception as exc:
            if not self._should_retry_with_flattened_tool_history(exc, messages):
                raise
            logger.warning(
                "cc_agent deepseek thinking compat fallback: mode=blocking error_type=%s",
                type(exc).__name__,
            )
            retry_messages = to_dify_prompt_messages(flatten_tool_history_for_prompt(messages))
            response = self._invoke_llm(model_config, retry_messages, prompt_tools)
            if self.stream:
                return self._collect_stream(response)
            return self._collect_result(response)

    def invoke_stream(
        self, messages: list[dict[str, Any]], tools: list[Any], force_final: bool = False
    ):
        prompt_messages = to_dify_prompt_messages(
            messages, preserve_reasoning_content=self.deepseek_thinking_compat
        )
        prompt_tools = [] if force_final else to_dify_prompt_tools(tools)
        model_config = self._model_config()
        logger.info(
            "cc_agent model invoke_stream: %s",
            _model_invoke_summary(
                session=self.session,
                model_config=model_config,
                messages=prompt_messages,
                tools=prompt_tools,
                stream=self.stream,
                force_final=force_final,
                run_id=self.run_budget.run_id if self.run_budget else "",
            ),
        )
        try:
            response = self._invoke_llm(model_config, prompt_messages, prompt_tools)
            if self.stream:
                yield from self.collect_stream_events(response)
                return
            turn = self._collect_result(response)
            for event in turn.stream_chunks:
                yield event
            yield self._result_event(turn)
        except Exception as exc:
            if not self._should_retry_with_flattened_tool_history(exc, messages):
                raise
            logger.warning(
                "cc_agent deepseek thinking compat fallback: mode=stream error_type=%s deepseek_thinking_fallback=True",
                type(exc).__name__,
            )
            retry_messages = to_dify_prompt_messages(flatten_tool_history_for_prompt(messages))
            response = self._invoke_llm(model_config, retry_messages, prompt_tools)
            if self.stream:
                yield from self.collect_stream_events(response)
                return
            turn = self._collect_result(response)
            for event in turn.stream_chunks:
                yield event
            yield self._result_event(turn)

    def _invoke_llm(self, model_config: Any, prompt_messages: list[Any], prompt_tools: list[Any]):
        if self.run_budget is not None:
            self.run_budget.before_model()
        return self.session.model.llm.invoke(
            model_config=model_config,
            prompt_messages=prompt_messages,
            tools=prompt_tools or None,
            stop=None,
            stream=self.stream,
        )

    def _should_retry_with_flattened_tool_history(
        self, exc: Exception, messages: list[dict[str, Any]]
    ) -> bool:
        if not self.deepseek_thinking_compat:
            return False
        from .run_budget import RunBudgetExceeded

        if isinstance(exc, RunBudgetExceeded):
            return False
        return _has_reasoned_tool_history(messages)

    def _model_config(self) -> Any:
        config = self.model_config
        if not self.keep_dify_history:
            config = strip_dify_history_from_model_config(config)
        if LLMModelConfig is None:
            return config
        if hasattr(config, "model_dump"):
            return LLMModelConfig(**_without_dify_history(config.model_dump(mode="json")))
        if isinstance(config, dict):
            return LLMModelConfig(**_without_dify_history(config))
        return config

    def _collect_stream(self, chunks: Any) -> AssistantTurn:
        events = list(self.collect_stream_events(chunks))
        if not events or not isinstance(events[-1], AssistantTurnCompleted):
            return AssistantTurn()
        return events[-1].turn

    def collect_stream_events(self, chunks: Any):
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        stream_chunks: list[TextDelta | ThinkingDelta] = []
        splitter = StreamContentSplitter()
        accumulator = StreamToolCallAccumulator(mode=self.tool_call_stream_mode)
        usage: dict[str, Any] = {}
        finish_reason = ""
        raw_message = None
        event: TextDelta | ThinkingDelta
        try:
            for chunk in chunks:
                delta = _get(chunk, "delta", chunk)
                message = _get(delta, "message", delta)
                raw_message = message or raw_message
                reasoning_content = _get(message, "reasoning_content")
                if reasoning_content:
                    event = ThinkingDelta(text=str(reasoning_content))
                    thinking_parts.append(event.text or "")
                    stream_chunks.append(event)
                    yield event
                content = _get(message, "content")
                if content:
                    for event in splitter.feed(_content_to_text(content)):
                        if isinstance(event, ThinkingDelta):
                            thinking_parts.append(event.text or "")
                        else:
                            text_parts.append(event.text or "")
                        stream_chunks.append(event)
                        yield event
                accumulator.add_delta(_get(message, "tool_calls"))
                usage = _merge_usage(usage, _get(delta, "usage"))
                finish_reason = str(_get(delta, "finish_reason") or finish_reason)
            for event in splitter.flush():
                if isinstance(event, ThinkingDelta):
                    thinking_parts.append(event.text or "")
                else:
                    text_parts.append(event.text or "")
                stream_chunks.append(event)
                yield event
        except Exception as exc:
            logger.error(
                "cc_agent model stream failed: error_type=%s text_chars=%s thinking_chars=%s tool_call_count=%s finish_reason=%s",
                type(exc).__name__,
                len("".join(text_parts)),
                len("".join(thinking_parts)),
                len(accumulator.finalize()),
                finish_reason,
            )
            raise
        tool_calls = accumulator.finalize()
        text = "".join(text_parts)
        thinking = "".join(thinking_parts)
        logger.info(
            "cc_agent model stream completed: text_chars=%s thinking_chars=%s tool_call_count=%s finish_reason=%s usage=%s",
            len(text),
            len(thinking),
            len(tool_calls),
            finish_reason,
            usage,
        )
        yield self._result_event(
            AssistantTurn(
                text=text,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=finish_reason,
                raw_message=raw_message,
                stream_chunks=stream_chunks,
                reasoning_content=thinking,
            )
        )

    def _collect_result(self, result: Any) -> AssistantTurn:
        message = _get(result, "message", result)
        accumulator = StreamToolCallAccumulator()
        accumulator.add_delta(_get(message, "tool_calls"))
        text, reasoning_content, stream_chunks = _split_content_to_turn_parts(
            _content_to_text(_get(message, "content") or "")
        )
        reasoning_field = _get(message, "reasoning_content")
        if reasoning_field:
            field_event = ThinkingDelta(text=str(reasoning_field))
            stream_chunks = [field_event, *stream_chunks]
            reasoning_content = str(reasoning_field) + reasoning_content
        return AssistantTurn(
            text=text,
            tool_calls=accumulator.finalize(),
            usage=_usage_to_dict(_get(result, "usage")),
            finish_reason=str(_get(result, "finish_reason") or ""),
            raw_message=message,
            stream_chunks=stream_chunks,
            reasoning_content=reasoning_content,
        )

    def _result_event(self, turn: AssistantTurn) -> AssistantTurnCompleted:
        return AssistantTurnCompleted(turn=turn)


def to_dify_prompt_messages(
    messages: list[dict[str, Any]], preserve_reasoning_content: bool = False
) -> list[Any]:
    if not all([SystemPromptMessage, UserPromptMessage, AssistantPromptMessage, ToolPromptMessage]):
        return messages
    converted = []
    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""
        if role == "system":
            converted.append(SystemPromptMessage(content=content))
        elif role == "user":
            converted.append(UserPromptMessage(content=content))
        elif role == "assistant":
            tool_calls = [
                _to_dify_tool_call(tool_call) for tool_call in message.get("tool_calls") or []
            ]
            reasoning_content = str(message.get("reasoning_content") or "")
            if preserve_reasoning_content and reasoning_content and tool_calls:
                converted.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [
                            (
                                tool_call.model_dump(mode="json")
                                if hasattr(tool_call, "model_dump")
                                else tool_call
                            )
                            for tool_call in tool_calls
                        ],
                        "reasoning_content": reasoning_content,
                    }
                )
            else:
                converted.append(AssistantPromptMessage(content=content, tool_calls=tool_calls))
        elif role == "tool":
            converted.append(
                ToolPromptMessage(
                    content=content,
                    tool_call_id=message.get("tool_call_id") or "",
                    name=message.get("name") or "",
                )
            )
    return converted


def flatten_tool_history_for_prompt(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    pending_tool_names: dict[str, str] = {}
    for message in messages:
        role = message.get("role")
        content = _content_to_text(message.get("content") or "")
        if role == "assistant":
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                flattened.append({"role": "assistant", "content": content})
                continue
            lines = []
            if content.strip():
                lines.append("Assistant message before tool call:\n" + content)
            lines.append("Assistant requested tool calls:")
            for tool_call in tool_calls:
                call_id = str(tool_call.get("id") or "")
                name = str(tool_call.get("name") or "")
                args = tool_call.get("arguments") or {}
                pending_tool_names[call_id] = name
                lines.append(
                    f"- {name or 'unknown_tool'} ({call_id}): {json.dumps(args, ensure_ascii=False)}"
                )
            flattened.append({"role": "user", "content": "\n".join(lines)})
        elif role == "tool":
            tool_call_id = str(message.get("tool_call_id") or "")
            tool_name = str(
                message.get("name") or pending_tool_names.get(tool_call_id) or "unknown_tool"
            )
            flattened.append(
                {
                    "role": "user",
                    "content": f"Tool result for {tool_name} ({tool_call_id}):\n{content}",
                }
            )
        else:
            flattened.append({"role": role, "content": content})
    return flattened


def strip_dify_history_from_model_config(model_config: Any) -> Any:
    """Return model config without Dify conversation history injection fields."""
    if isinstance(model_config, dict):
        return _without_dify_history(model_config)
    if hasattr(model_config, "model_copy"):
        try:
            return model_config.model_copy(update={"history_prompt_messages": None})
        except Exception:
            pass
    if hasattr(model_config, "model_dump"):
        try:
            return _without_dify_history(model_config.model_dump(mode="json"))
        except Exception:
            pass
    if hasattr(model_config, "history_prompt_messages"):
        clone = _namespace_without_dify_history(model_config)
        if clone is not None:
            return clone
    return model_config


def _without_dify_history(value: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(value)
    cleaned.pop("history_prompt_messages", None)
    return cleaned


def _namespace_without_dify_history(value: Any) -> Any | None:
    try:
        data = {key: item for key, item in vars(value).items() if key != "history_prompt_messages"}
    except TypeError:
        return None
    return type(value)(**data)


def from_dify_prompt_messages(messages: list[Any] | None) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages or []:
        role = _role_value(_get(message, "role"))
        content = _content_to_text(_get(message, "content") or "")
        if role in {"system", "user"}:
            converted.append({"role": role, "content": content})
        elif role == "assistant":
            tool_calls = []
            for raw_tool_call in _get(message, "tool_calls") or []:
                function = _get(raw_tool_call, "function", {})
                arguments, _ = _parse_tool_arguments(str(_get(function, "arguments") or "{}"))
                tool_calls.append(
                    {
                        "id": str(_get(raw_tool_call, "id") or ""),
                        "name": str(_get(function, "name") or ""),
                        "arguments": arguments,
                    }
                )
            payload: dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                payload["tool_calls"] = tool_calls
            converted.append(payload)
        elif role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "content": content,
                    "tool_call_id": str(_get(message, "tool_call_id") or ""),
                    "name": str(_get(message, "name") or ""),
                }
            )
    return converted


def to_dify_prompt_tools(tools: list[Any]) -> list[Any]:
    if PromptMessageTool is None:
        return tools
    converted = []
    for tool in tools:
        if isinstance(tool, dict):
            converted.append(PromptMessageTool(**tool))
        else:
            converted.append(tool)
    return converted


def _to_dify_tool_call(tool_call: dict[str, Any]) -> Any:
    if AssistantPromptMessage is None:
        return tool_call
    function = AssistantPromptMessage.ToolCall.ToolCallFunction(
        name=tool_call.get("name") or "",
        arguments=json.dumps(tool_call.get("arguments") or {}, ensure_ascii=False),
    )
    return AssistantPromptMessage.ToolCall(
        id=tool_call.get("id") or "", type="function", function=function
    )


def _has_reasoned_tool_history(messages: list[dict[str, Any]]) -> bool:
    return any(
        message.get("role") == "assistant"
        and message.get("tool_calls")
        and message.get("reasoning_content")
        for message in messages
    )


def _split_partial_marker(buffer: str, marker: str, final: bool) -> tuple[str, str]:
    if final:
        return buffer, ""
    max_prefix = min(len(buffer), len(marker) - 1)
    for size in range(max_prefix, 0, -1):
        if marker.startswith(buffer[-size:]):
            return buffer[:-size], buffer[-size:]
    return buffer, ""


def _split_content_to_turn_parts(content: str) -> tuple[str, str, list[TextDelta | ThinkingDelta]]:
    splitter = StreamContentSplitter()
    events = splitter.feed(content)
    events.extend(splitter.flush())
    text = "".join(event.text or "" for event in events if isinstance(event, TextDelta))
    reasoning_content = "".join(
        event.text or "" for event in events if isinstance(event, ThinkingDelta)
    )
    return text, reasoning_content, events


def _parse_tool_arguments(raw_arguments: str) -> tuple[dict[str, Any], str]:
    if not raw_arguments:
        return {}, ""
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return {"_raw_arguments": raw_arguments}, raw_arguments
    if isinstance(parsed, dict):
        return parsed, raw_arguments
    return {"value": parsed}, raw_arguments


def _merge_usage(current: dict[str, Any], usage: Any) -> dict[str, Any]:
    incoming = _usage_to_dict(usage)
    if not incoming:
        return current
    merged = dict(current)
    for key, value in incoming.items():
        if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
            merged[key] += value
        else:
            merged[key] = value
    return merged


def _usage_to_dict(usage: Any) -> dict[str, Any]:
    if not usage:
        return {}
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")
    return {
        key: getattr(usage, key)
        for key in ["prompt_tokens", "completion_tokens", "total_tokens", "total_price", "currency"]
        if hasattr(usage, key)
    }


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content or "")


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _role_value(role: Any) -> str:
    return str(getattr(role, "value", role) or "")


def _model_invoke_summary(
    session: Any,
    model_config: Any,
    messages: list[Any],
    tools: list[Any],
    stream: bool,
    force_final: bool,
    run_id: str = "",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "install_method": str(
            getattr(
                getattr(session, "install_method", None),
                "value",
                getattr(session, "install_method", None),
            )
        ),
        "daemon_url": _redact_url(getattr(session, "dify_plugin_daemon_url", None)),
        "session_id_present": bool(getattr(session, "session_id", None)),
        "conversation_id_present": bool(getattr(session, "conversation_id", None)),
        "app_id_present": bool(getattr(session, "app_id", None)),
        "model_provider": _get(model_config, "provider"),
        "model_name": _get(model_config, "model"),
        "model_mode": _get(model_config, "mode"),
        "stream": stream,
        "force_final": force_final,
        "message_count": len(messages or []),
        "tool_count": len(tools or []),
        "history_prompt_messages_present": bool(_get(model_config, "history_prompt_messages")),
    }


def _redact_url(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        from yarl import URL

        url = URL(text)
        if url.password or url.user:
            return str(url.with_user(None).with_password(None))
    except Exception:
        pass
    return text
