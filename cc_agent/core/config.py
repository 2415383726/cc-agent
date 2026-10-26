from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import Any

from .mcp_config import McpServerConfig, parse_mcp_servers

from .profiles import (
    StrategyProfile,
    strategy_profile_for_output,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentRunConfig:
    query: str = ""
    instruction: str = ""
    model: Any | None = None
    think_model: Any | None = None
    flash_model: Any | None = None
    multimodal_model: Any | None = None
    tools: list[Any] | None = None
    mcp_servers: list[McpServerConfig] = field(default_factory=list, repr=False)
    maximum_iterations: int = 8
    max_observation_chars: int = 8000
    max_history_messages: int = 40
    max_total_context_tokens: int = 131072
    # Deprecated compatibility alias. Internally all context limits are tokens.
    max_total_context_chars: int | None = None
    resolved_context_limit: int = 0
    tool_allowlist: list[str] | None = None
    tool_denylist: list[str] | None = None
    tool_confirmation_list: list[str] | None = None
    max_repeated_tool_calls: int = 3
    max_consecutive_tool_errors: int = 3
    show_tool_calls: bool = True
    conversation_id: str = ""
    state_id: str = ""
    agent_state_variable: str = ""
    history_variable: str = ""
    state_reset: bool = False
    emit_inline_state: bool = True
    use_dify_history: bool = True
    stream: bool = True
    model_features: list[str] | None = None
    tool_call_supported: bool = True
    user_prompt_response: dict[str, Any] | None = None
    deepseek_thinking_compat: bool = False
    output_protocol: str = "agui"
    strategy_profile: StrategyProfile | None = None
    app_skills_yaml: str = ""
    skill_denylist: list[str] | None = None
    files: list[Any] | None = None
    runtime_config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        legacy_limit = _optional_positive_int(self.max_total_context_chars)
        canonical_limit = _positive_int(self.max_total_context_tokens, 131072)
        if legacy_limit is not None and canonical_limit == 131072:
            canonical_limit = legacy_limit
        self.max_total_context_tokens = canonical_limit
        self.max_total_context_chars = canonical_limit
        if self.resolved_context_limit <= 0:
            self.resolved_context_limit = canonical_limit

    @classmethod
    def from_parameters(
        cls,
        parameters: dict[str, Any],
        *,
        strategy_profile: StrategyProfile | None = None,
    ) -> "AgentRunConfig":
        inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
        param = lambda key, default=None: _parameter_value(parameters, inputs, key, default)
        model = parameters.get("model")
        model_features = extract_model_features(model)
        requested_stream = bool(param("stream", True))
        runtime_config = _runtime_config(param("runtime_config", ""))
        node_context_limit = _optional_positive_int(param("max_total_context_tokens"))
        runtime_context_limit = _optional_positive_int(runtime_config.get("max_total_context_tokens"))
        legacy_context_limit = _optional_positive_int(runtime_config.get("max_total_context_chars"))
        configured_context_limit = node_context_limit or runtime_context_limit or legacy_context_limit
        resolved_context_limit = configured_context_limit or extract_model_context_limit(model, 131072)
        selected_strategy_profile = strategy_profile or strategy_profile_for_output(
            _output_protocol(param("output_protocol", True))
        )
        return cls(
            query=str(parameters.get("query") or ""),
            instruction=str(param("instruction", "") or ""),
            model=model,
            tools=parameters.get("tools") or [],
            mcp_servers=parse_mcp_servers(param("mcp_servers_config")),
            maximum_iterations=_positive_int(runtime_config.get("maximum_iterations"), 8),
            max_observation_chars=_positive_int(runtime_config.get("max_observation_chars"), 8000),
            max_history_messages=_positive_int(runtime_config.get("max_history_messages"), 40),
            max_total_context_tokens=resolved_context_limit,
            max_total_context_chars=resolved_context_limit,
            resolved_context_limit=resolved_context_limit,
            max_repeated_tool_calls=_positive_int(runtime_config.get("max_repeated_tool_calls"), 3),
            max_consecutive_tool_errors=_positive_int(runtime_config.get("max_consecutive_tool_errors"), 3),
            show_tool_calls=_bool(param("show_tool_calls"), True),
            conversation_id=str(param("conversation_id", parameters.get("conversation_id") or "") or ""),
            state_id=str(param("state_id", "") or ""),
            agent_state_variable=str(param("agent_state", "") or ""),
            history_variable=str(param("agent_state", "") or ""),
            state_reset=_bool(runtime_config.get("state_reset"), False),
            emit_inline_state=True,
            stream=resolve_stream_mode(requested_stream, model_features),
            model_features=model_features,
            tool_call_supported=_tool_call_supported(model_features),
            user_prompt_response=_user_prompt_response(parameters, inputs),
            deepseek_thinking_compat=_bool(param("deepseek_thinking_compat"), False),
            output_protocol=selected_strategy_profile.output_protocol,
            strategy_profile=selected_strategy_profile,
            app_skills_yaml=str(param("app_skills_yaml", "") or ""),
            skill_denylist=_string_list(param("skill_denylist")),
            files=_file_list(param("files")),
            runtime_config=runtime_config,
        )

    @property
    def bundled_skill_groups(self) -> tuple[str, ...] | None:
        if self.strategy_profile is None:
            return None
        groups = list(self.strategy_profile.bundled_skill_groups)
        return tuple(dict.fromkeys(groups))

    @property
    def model_profiles(self) -> dict[str, Any | None]:
        return {
            "default": self.model,
            "think": self.model,
            "flash": self.model,
            "multimodal": self.model,
        }

    def model_for(self, profile: str = "default") -> Any | None:
        key = str(profile or "default").strip().lower()
        aliases = {
            "main": "default",
            "primary": "default",
            "reasoning": "think",
            "fast": "flash",
            "vision": "multimodal",
            "multimodal_model": "multimodal",
            "think_model": "think",
            "flash_model": "flash",
        }
        return self.model_profiles.get(aliases.get(key, key), self.model)


def _safe_len(value: Any) -> int:
    try:
        return len(value)
    except TypeError:
        return -1


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _optional_positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parameter_value(parameters: dict[str, Any], inputs: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in parameters and parameters[key] is not None:
        return parameters[key]
    return inputs.get(key, default)


_RUNTIME_CONFIG_KEYS = {
    "maximum_iterations",
    "max_observation_chars",
    "max_history_messages",
    "max_total_context_chars",
    "max_total_context_tokens",
    "max_repeated_tool_calls",
    "max_consecutive_tool_errors",
    "state_reset",
}


def _runtime_config(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    payload = _json_object(value, field_name="runtime_config")
    unknown = sorted(set(payload) - _RUNTIME_CONFIG_KEYS)
    if unknown:
        logger.warning("Ignoring unknown runtime_config fields: %s", unknown)
    return {key: payload[key] for key in _RUNTIME_CONFIG_KEYS if key in payload}


def _json_object(value: Any, field_name: str = "value") -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {field_name} JSON: {exc}") from exc
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid {field_name} JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Invalid {field_name} JSON: expected object")
    return parsed


def _bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return bool(value)


def extract_model_features(model: Any) -> list[str]:
    entity = _get(model, "entity")
    features = _get(entity, "features")
    if features is None and isinstance(entity, dict):
        features = entity.get("features")
    if not isinstance(features, list):
        return []
    return [_feature_value(feature) for feature in features if _feature_value(feature)]


def _feature_value(feature: Any) -> str:
    value = _get(feature, "value")
    if value:
        return str(value)
    if isinstance(feature, dict):
        value = feature.get("value") or feature.get("name")
        if value:
            return str(value)
    return str(feature)


def resolve_stream_mode(requested_stream: bool, model_features: list[str]) -> bool:
    if not requested_stream:
        return False
    if not model_features:
        return True
    return "stream-tool-call" in model_features


def _tool_call_supported(model_features: list[str]) -> bool:
    if not model_features:
        return True
    return "tool-call" in model_features


def extract_model_context_limit(model: Any, default: int) -> int:
    entity = _get(model, "entity", model)
    for source in (entity, model):
        for key in ("context_size", "context_window", "max_context_tokens"):
            parsed = _positive_int(_get(source, key), 0)
            if parsed:
                return parsed
        model_properties = _get(source, "model_properties") or _get(source, "properties") or {}
        parsed = _positive_int(_get(model_properties, "context_size"), 0)
        if parsed:
            return parsed
        parsed = _positive_int(_get(model_properties, "context_window"), 0)
        if parsed:
            return parsed
    return default


def _string_list(value: Any) -> list[str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = __import__("json").loads(stripped)
        except Exception:
            separator = ";" if ";" in stripped else ","
            parsed = [part.strip() for part in stripped.split(separator)]
        value = parsed
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or None
    return [str(value)]


def _file_list(value: Any) -> list[Any]:
    if value is None or value == "":
        logger.info("cc_agent _file_list: empty value type=%s", type(value).__name__)
        return []
    if isinstance(value, str):
        stripped = value.strip()
        logger.info("cc_agent _file_list: str len=%s head=%s tail=%s", len(stripped), stripped[:120], stripped[-60:])
        if not stripped:
            return []
        # Dify string templates may double-wrap JSON in extra quotes
        parsed = _try_parse_json(stripped)
        if parsed is not None:
            value = parsed
        else:
            # Unwrap: Dify template re-stringifies without escaping inner quotes
            # e.g. raw string is "[{"name":"f"}]" — strip outer quotes, parse inner
            unwrapped = _strip_outer_quotes(stripped)
            if unwrapped != stripped:
                parsed = _try_parse_json(unwrapped)
                if parsed is not None:
                    value = parsed
        if isinstance(value, str):
            logger.warning("cc_agent _file_list: JSON parse failed after unwrap head=%s tail=%s", stripped[:120], stripped[-60:])
            return []
    if isinstance(value, dict):
        # Dify may pass the Code node output directly as a dict with a files_json key
        inner_json = value.get("files_json") or value.get("files")
        if isinstance(inner_json, str):
            parsed = _try_parse_json(inner_json.strip())
            if parsed is not None:
                return list(parsed) if isinstance(parsed, list) else [parsed] if isinstance(parsed, dict) else [parsed]
        # Treat the dict itself as a single file entry
        logger.info("cc_agent _file_list: dict keys=%s", sorted(value.keys()))
        return [value]
    if isinstance(value, (list, tuple)):
        logger.info("cc_agent _file_list: list items=%s", len(value))
        return list(value)
    logger.warning("cc_agent _file_list: unexpected type=%s", type(value).__name__)
    return [value]


def _try_parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _strip_outer_quotes(text: str) -> str:
    """Strip one pair of matching outer quotes (single or double)."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _user_prompt_response(parameters: dict[str, Any], inputs: dict[str, Any] | None = None) -> dict[str, Any] | None:
    inputs = inputs if isinstance(inputs, dict) else {}
    response = _parameter_value(parameters, inputs, "user_prompt_response")
    return response if isinstance(response, dict) else None


def _output_protocol(value: Any) -> str:
    if value is None or value == "":
        return "agui"
    if isinstance(value, bool):
        return "agui" if value else "dify_native"
    if isinstance(value, (int, float)):
        return "agui" if value != 0 else "dify_native"
    if not isinstance(value, str):
        raise ValueError(f"unsupported output_protocol: {value}")
    protocol = value.strip().lower()
    if protocol in {"true", "yes", "1", "on"}:
        return "agui"
    if protocol in {"false", "no", "0", "off"}:
        return "dify_native"
    raise ValueError(f"unsupported output_protocol boolean value: {protocol}")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
