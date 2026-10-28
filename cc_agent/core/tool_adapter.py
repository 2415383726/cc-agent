from __future__ import annotations

import json
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .mcp_tools import McpToolProvider

from .internal_tools import InternalToolExecutor
from .messages import AgentState, ToolCall, ToolResult
from .tool_catalog import ToolCatalog, ToolSpec

try:  # pragma: no cover - exercised inside Dify runtime
    from dify_plugin.entities.tool import ToolProviderType
except Exception:  # pragma: no cover
    ToolProviderType = None


class ToolAdapter:
    def __init__(
        self,
        registry: ToolCatalog,
        state: AgentState,
        session: Any | None = None,
        skill_runtime: Any | None = None,
        mcp_provider: McpToolProvider | None = None,
    ):
        self.registry = registry
        self.state = state
        self.session = session
        self.mcp_provider = mcp_provider
        self.internal_executor = InternalToolExecutor(
            state, session=session, skill_runtime=skill_runtime
        )

    def execute(self, tool_call: ToolCall) -> ToolResult:
        spec = self.registry.resolve(tool_call.name)
        if not spec:
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                llm_observation=f"Tool not found: {tool_call.name}",
                is_error=True,
                synthetic=True,
            )
        if "_raw_arguments" in tool_call.arguments and len(tool_call.arguments) == 1:
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                llm_observation=f"Invalid JSON arguments for {tool_call.name}: {tool_call.arguments['_raw_arguments']}",
                is_error=True,
                synthetic=True,
            )
        if spec.kind == "internal":
            return self.internal_executor.execute(spec.name, tool_call.arguments, tool_call.id)
        if spec.kind == "mcp":
            if self.mcp_provider is not None:
                return self.mcp_provider.execute(spec, tool_call)
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                llm_observation="MCP tool session is not available.",
                is_error=True,
                synthetic=True,
            )
        return self._execute_external(spec, tool_call)

    def _execute_external(self, spec: ToolSpec, tool_call: ToolCall) -> ToolResult:
        if not self.session:
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                llm_observation="External tool session is not available.",
                is_error=True,
                synthetic=True,
            )
        entity = spec.entity
        parameters = {**_runtime_parameters(entity), **(tool_call.arguments or {})}
        try:
            responses = self.session.tool.invoke(
                provider_type=_provider_type(_tool_provider_type(entity)),
                provider=_tool_provider(entity),
                tool_name=spec.original_name,
                parameters=parameters,
            )
            observation, display_messages, metadata = normalize_tool_invoke_messages(responses)
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                llm_observation=observation or "(tool completed with no output)",
                display_messages=display_messages,
                metadata=metadata,
            )
        except Exception as exc:
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                llm_observation="External tool invocation failed. The remote execution outcome is unknown; verify it before repeating a write operation.",
                is_error=True,
                synthetic=True,
                metadata={
                    "error_code": "external_tool_failed",
                    "error_type": type(exc).__name__,
                    "execution_outcome": "unknown",
                },
            )


def normalize_tool_invoke_messages(
    responses: Iterable[Any],
) -> tuple[str, list[Any], dict[str, Any]]:
    parts: list[str] = []
    display_messages: list[Any] = []
    metadata: dict[str, Any] = {}
    for response in responses:
        response_type = _type_name(_get(response, "type"))
        message = _get(response, "message", response)
        if response_type in {"text", "textmessage"}:
            parts.append(_message_text(message))
        elif response_type == "json":
            parts.append(json.dumps(_get(message, "json_object", message), ensure_ascii=False))
        elif response_type == "link":
            parts.append(f"result link: {_message_text(message)}")
            display_messages.append(response)
        elif response_type in {"image", "image_link"}:
            parts.append(f"Image output generated: {_message_text(message)}")
            display_messages.append(response)
        elif response_type in {"blob", "blob_chunk", "file"}:
            parts.append("File output generated.")
            display_messages.append(response)
        elif response_type == "variable":
            metadata.setdefault("variables", []).append(
                _get(message, "variable_name", None) or message
            )
            parts.append(f"Variable output: {_stringify_message(message)}")
            display_messages.append(response)
        elif response_type == "retriever_resources":
            retriever_text = _format_retriever_resources(message)
            if retriever_text:
                parts.append(retriever_text)
            display_messages.append(response)
        elif response_type == "log":
            display_messages.append(response)
        else:
            text = _stringify_message(message)
            if text:
                parts.append(text)
    return "\n".join(_dedup_consecutive(parts)).strip(), display_messages, metadata


def _runtime_parameters(entity: Any) -> dict[str, Any]:
    value = _get(entity, "runtime_parameters") or _get(entity, "tool_configuration") or {}
    return value if isinstance(value, dict) else {}


def _tool_provider(entity: Any) -> str:
    identity = _get(entity, "identity")
    return str(
        _get(identity, "provider") or _get(entity, "provider") or _get(entity, "provider_id") or ""
    )


def _tool_provider_type(entity: Any) -> Any:
    return (
        _get(entity, "provider_type")
        or _get(entity, "tool_provider_type")
        or _get(entity, "tool_type")
        or _get(entity, "type")
        or "builtin"
    )


def _provider_type(provider_type: Any) -> Any:
    if ToolProviderType is None or provider_type is None:
        return provider_type
    try:
        return ToolProviderType(provider_type)
    except Exception:
        return provider_type


def _message_text(message: Any) -> str:
    return str(_get(message, "text", message) or "")


def _format_retriever_resources(message: Any) -> str:
    resources = _extract_retriever_items(message)
    rendered = [
        _format_retriever_item(item, index) for index, item in enumerate(resources, start=1)
    ]
    rendered = [item for item in rendered if item]
    if not rendered:
        fallback = _stringify_message(message)
        rendered = [f"1. {fallback}"] if fallback else []
    return "Retrieved resources:\n" + "\n".join(rendered) if rendered else ""


def _extract_retriever_items(message: Any) -> list[Any]:
    if isinstance(message, list):
        return message
    for key in ["retriever_resources", "resources", "items", "documents"]:
        value = _get(message, key)
        if isinstance(value, list):
            return value
    return [message] if message else []


def _format_retriever_item(item: Any, index: int) -> str:
    title = _first_value(item, ["title", "document_name", "name"])
    source = _first_value(item, ["source", "url", "link", "dataset_name"])
    content = _first_value(item, ["content", "text", "page_content", "segment_content"])
    metadata = _first_value(item, ["metadata", "meta"])
    parts = []
    if title:
        parts.append(f"title={title}")
    if source:
        parts.append(f"source={source}")
    if content:
        parts.append(f"content={content}")
    if metadata:
        parts.append(f"metadata={_stringify_message(metadata)}")
    if not parts:
        fallback = _stringify_message(item)
        if fallback:
            parts.append(fallback)
    return f"{index}. " + "; ".join(parts) if parts else ""


def _first_value(obj: Any, keys: list[str]) -> Any:
    for key in keys:
        value = _get(obj, key)
        if value:
            return value
    return None


def _stringify_message(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return json.dumps(message, ensure_ascii=False)
    if hasattr(message, "model_dump"):
        return json.dumps(message.model_dump(mode="json"), ensure_ascii=False)
    if hasattr(message, "__dict__"):
        return json.dumps(message.__dict__, ensure_ascii=False, default=str)
    return str(message or "")


def _type_name(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    raw = str(raw).split(".")[-1]
    return raw.lower()


def _dedup_consecutive(parts: list[str]) -> list[str]:
    """Remove duplicate payloads from a single tool response.

    Dify external tools may emit the same text/json payload twice when the
    tool wrapper echoes both the raw result and the Dify-wrapped output.
    The JSON key order can differ between copies, so comparisons use a
    canonical fingerprint while preserving the first original payload.
    """
    parts = [part for part in parts if part]
    parts = _dedup_repeated_halves(parts)
    result: list[str] = []
    last_fingerprint = ""
    for part in parts:
        fingerprint = _part_fingerprint(part)
        if result and fingerprint == last_fingerprint:
            continue
        result.append(part)
        last_fingerprint = fingerprint
    return result


def _dedup_repeated_halves(parts: list[str]) -> list[str]:
    if len(parts) < 2 or len(parts) % 2:
        return parts
    midpoint = len(parts) // 2
    first_half = [_part_fingerprint(part) for part in parts[:midpoint]]
    second_half = [_part_fingerprint(part) for part in parts[midpoint:]]
    if first_half == second_half:
        return parts[:midpoint]
    return parts


def _part_fingerprint(part: str) -> str:
    stripped = part.strip()
    if not stripped or stripped[0] not in "[{":
        return part
    try:
        parsed = json.loads(stripped)
    except (TypeError, ValueError):
        return part
    return "json:" + json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
