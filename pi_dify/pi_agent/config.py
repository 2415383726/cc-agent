"""Validated runtime configuration for one Dify request."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from typing import Any

from .errors import PiError


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off", ""}:
            return False
    raise ValueError("expected a boolean")


def _as_int(value: Any, default: int, minimum: int = 0, maximum: int = 10_000_000) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("expected an integer")
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError(f"expected {minimum}..{maximum}")
    return number


def _as_float(value: Any, default: float, minimum: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("expected a number")
    number = float(value)
    if number < minimum:
        raise ValueError(f"expected >= {minimum}")
    return number


def _as_str(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _as_str_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        if text.startswith("["):
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError("expected a list")
            value = parsed
        else:
            return tuple(item.strip() for item in text.split(",") if item.strip())
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected a list of strings")
    return tuple(str(item).strip() for item in value if str(item).strip())


@dataclass(slots=True)
class RuntimeConfig:
    context_window: int = 128_000
    reserved_output_tokens: int = 8_192
    max_model_requests: int = 24
    max_tool_calls: int = 32
    max_wall_seconds: float = 300.0
    max_reported_tokens: int = 0
    max_result_chars: int = 12_000
    display_result_chars: int = 8_000
    tool_stream_mode: str = "delta"
    stream_mode: str = "stream"
    stream_fallback: bool = True
    thinking_tags: bool = True
    preserve_reasoning_content: bool = False
    compaction_enabled: bool = True
    compaction_reserve_tokens: int = 16_384
    compaction_keep_recent_tokens: int = 20_000
    auto_compact: bool = True
    state_max_encoded_bytes: int = 190_000
    display_max_events: int = 400
    max_duplicate_tool_calls: int = 2
    max_consecutive_errors: int = 3
    max_tool_result_bytes: int = 32_768
    approval_mode: str = "configured"
    approval_tools: tuple[str, ...] = ()
    question_timeout_seconds: float = 0.0
    max_questions: int = 10
    max_options: int = 20
    skill_max_read_chars: int = 12_000
    mcp_tool_timeout: float = 60.0
    mcp_agent_tools_only: bool = True
    mcp_tools_exclude: tuple[str, ...] = ()
    tool_timeout_seconds: float = 120.0
    show_tool_calls: bool = True
    user_skill_prefix: str = "/skill:"

    @classmethod
    def from_value(cls, value: Any) -> RuntimeConfig:
        payload: dict[str, Any] = {}
        if value:
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise PiError(
                        code="invalid_configuration",
                        stage="config",
                        message="runtime_config must be valid JSON.",
                    ) from exc
            if not isinstance(value, dict):
                raise PiError(
                    code="invalid_configuration",
                    stage="config",
                    message="runtime_config must be a JSON object.",
                )
            if isinstance(value.get("runtime_config"), (str, dict)):
                nested = value["runtime_config"]
                if isinstance(nested, str) and nested.strip():
                    try:
                        nested = json.loads(nested)
                    except json.JSONDecodeError as exc:
                        raise PiError(
                            code="invalid_configuration",
                            stage="config",
                            message="runtime_config must be valid JSON.",
                        ) from exc
                payload = nested if isinstance(nested, dict) else value
            else:
                payload = value

        config = cls()
        known = {item.name for item in fields(cls)}
        try:
            for key, raw in payload.items():
                if key not in known:
                    continue
                if key in {
                    "context_window",
                    "reserved_output_tokens",
                    "max_model_requests",
                    "max_tool_calls",
                    "max_reported_tokens",
                    "max_result_chars",
                    "display_result_chars",
                    "compaction_reserve_tokens",
                    "compaction_keep_recent_tokens",
                    "state_max_encoded_bytes",
                    "display_max_events",
                    "max_duplicate_tool_calls",
                    "max_consecutive_errors",
                    "max_tool_result_bytes",
                    "max_questions",
                    "max_options",
                    "skill_max_read_chars",
                }:
                    setattr(config, key, _as_int(raw, getattr(config, key), 0))
                elif key in {
                    "max_wall_seconds",
                    "question_timeout_seconds",
                    "mcp_tool_timeout",
                    "tool_timeout_seconds",
                }:
                    setattr(config, key, _as_float(raw, getattr(config, key)))
                elif key in {
                    "stream_fallback",
                    "compaction_enabled",
                    "auto_compact",
                    "mcp_agent_tools_only",
                    "show_tool_calls",
                    "thinking_tags",
                    "preserve_reasoning_content",
                }:
                    setattr(config, key, _as_bool(raw, getattr(config, key)))
                elif key == "approval_tools":
                    config.approval_tools = _as_str_list(raw)
                else:
                    setattr(config, key, _as_str(raw, getattr(config, key)))
        except (TypeError, ValueError) as exc:
            raise PiError(
                code="invalid_configuration",
                stage="config",
                message=f"Invalid runtime_config value ({type(exc).__name__}).",
            ) from None

        if config.tool_stream_mode not in {"delta", "snapshot"}:
            raise PiError(
                code="invalid_configuration",
                stage="config",
                message="tool_stream_mode must be delta or snapshot.",
            )
        if config.stream_mode not in {"stream", "nonstream", "auto"}:
            raise PiError(
                code="invalid_configuration",
                stage="config",
                message="stream_mode must be stream, nonstream or auto.",
            )
        if config.approval_mode not in {"off", "configured", "mcp"}:
            raise PiError(
                code="invalid_configuration",
                stage="config",
                message="approval_mode must be off, configured or mcp.",
            )
        if config.max_model_requests < 1 or config.max_tool_calls < 0:
            raise PiError(
                code="invalid_configuration",
                stage="config",
                message="Execution budgets must allow at least one model request.",
            )
        if config.context_window < 1_024:
            raise PiError(
                code="invalid_configuration", stage="config", message="context_window is too small."
            )
        config.reserved_output_tokens = min(
            config.reserved_output_tokens, config.context_window // 2
        )
        return config

    def public(self) -> dict[str, Any]:
        """A secret-free projection for logs and state summaries."""
        return {
            "context_window": self.context_window,
            "max_model_requests": self.max_model_requests,
            "max_tool_calls": self.max_tool_calls,
            "max_wall_seconds": self.max_wall_seconds,
            "tool_stream_mode": self.tool_stream_mode,
            "stream_mode": self.stream_mode,
            "compaction_enabled": self.compaction_enabled,
            "approval_mode": self.approval_mode,
        }


@dataclass(slots=True)
class RequestContext:
    query: str = ""
    model: Any = None
    tools: list[Any] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    instruction: str = ""
    conversation_id: str = ""
    user_id: str = ""
    app_id: str = ""
    app_skills_yaml: str = ""
    mcp_servers_config: str = ""
    agent_state: str = ""
    interaction: dict[str, Any] | None = None
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    raw_state_id: str = ""

    @property
    def session_id(self) -> str:
        return self.conversation_id or self.raw_state_id or "pi-dify-session"

    @property
    def state_id(self) -> str:
        return self.conversation_id or self.raw_state_id or "pi-dify-state"


def _first(mapping: dict[str, Any], inputs: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in mapping and mapping[key] is not None:
        return mapping[key]
    if key in inputs and inputs[key] is not None:
        return inputs[key]
    return default


def parse_request(parameters: dict[str, Any]) -> RequestContext:
    parameters = parameters if isinstance(parameters, dict) else {}
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}

    raw_files = _first(parameters, inputs, "files", [])
    files = _parse_files(raw_files)
    interaction = _parse_mapping(_first(parameters, inputs, "interaction"), "interaction")
    if interaction is None:
        interaction = _parse_mapping(
            _first(parameters, inputs, "structured_interaction"), "interaction"
        )

    return RequestContext(
        query=str(_first(parameters, inputs, "query", "") or ""),
        model=parameters.get("model") or inputs.get("model"),
        tools=list(parameters.get("tools") or inputs.get("tools") or []),
        files=files,
        instruction=str(_first(parameters, inputs, "instruction", "") or ""),
        conversation_id=str(
            parameters.get("conversation_id")
            or inputs.get("conversation_id")
            or parameters.get("thread_id")
            or inputs.get("thread_id")
            or ""
        ),
        user_id=str(parameters.get("user_id") or inputs.get("user_id") or "pi-dify-user"),
        app_id=str(parameters.get("app_id") or inputs.get("app_id") or ""),
        app_skills_yaml=str(_first(parameters, inputs, "app_skills_yaml", "") or ""),
        mcp_servers_config=str(
            _first(parameters, inputs, "mcp_servers_config", "")
            or _first(parameters, inputs, "mcp_servers", "")
            or ""
        ),
        agent_state=str(_first(parameters, inputs, "agent_state", "") or ""),
        interaction=interaction,
        runtime=RuntimeConfig.from_value(_first(parameters, inputs, "runtime_config", None)),
        raw_state_id=str(parameters.get("state_id") or inputs.get("state_id") or ""),
    )


def _parse_files(value: Any) -> list[dict[str, Any]]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return []
    payload = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if isinstance(payload, dict):
        payload = payload.get("files") or payload.get("data") or []
    if not isinstance(payload, list):
        return []
    result: list[dict[str, Any]] = []
    for item in payload[:50]:
        if not isinstance(item, dict):
            continue
        allowed = {
            key: str(item.get(key) or "")
            for key in ("id", "name", "filename", "mime_type", "mimeType", "type", "url")
            if item.get(key) not in (None, "")
        }
        if allowed.get("id") or allowed.get("name") or allowed.get("url"):
            size = item.get("size")
            if isinstance(size, int) and not isinstance(size, bool):
                allowed["size"] = size
            result.append(allowed)
    return result


def _parse_mapping(value: Any, name: str) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            raise PiError(
                code="invalid_configuration",
                stage="config",
                message=f"{name} must be a JSON object.",
            ) from None
        if parsed is None:
            return None
        if isinstance(parsed, dict):
            return parsed
    raise PiError(
        code="invalid_configuration", stage="config", message=f"{name} must be a JSON object."
    )
