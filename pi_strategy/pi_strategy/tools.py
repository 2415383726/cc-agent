"""Controlled AgentTool adapters for Dify-injected tools, remote MCP and Pi internals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from pi_agent_core.types import AgentToolResult, AgentToolUpdateCallback

from .artifacts import Artifact, normalize_dify_responses, normalize_mcp_result
from .budget import RunLedger
from .config import RuntimeConfig
from .errors import BudgetExceeded, PiError
from .mcp import McpRuntime
from .native import clip
from .session_io import SessionAborted, SessionIO
from .skills import SkillCatalog

try:  # pragma: no cover - Dify SDK types are present in the plugin runtime
    from dify_plugin.entities.tool import ToolProviderType
except Exception:  # pragma: no cover
    ToolProviderType = None


ACTIVATE_SKILL_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string", "description": "Eligible skill name."}},
    "required": ["name"],
}

READ_SKILL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "path": {"type": "string", "description": "Resource path inside the skill."},
        "offset": {"type": "integer", "description": "Character offset for paging."},
        "limit": {"type": "integer", "description": "Maximum characters to return."},
    },
    "required": ["name", "path"],
}


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    source: str
    original_name: str
    entity: Any = None
    annotations: dict[str, Any] = field(default_factory=dict)
    server: str = ""
    identity: str = ""


@dataclass(slots=True)
class ToolOutcome:
    text: str
    details: dict[str, Any]
    is_error: bool = False
    artifacts: list[Artifact] = field(default_factory=list)


class PiTool:
    execution_mode = "sequential"

    def __init__(self, spec: ToolSpec, *, runtime: ToolRuntime) -> None:
        self.spec = spec
        self.runtime = runtime
        self.name = spec.name
        self.description = spec.description
        self.label = spec.name
        self.parameters = spec.parameters
        self.annotations = spec.annotations

    def prepare_arguments(self, args: Any) -> Any:
        return args

    async def execute(
        self,
        tool_call_id: str,
        params: Any,
        signal: Any | None = None,
        on_update: AgentToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "aborted", False):
            return AgentToolResult(
                content=[{"type": "text", "text": "Not executed: the run was stopped."}],
                details={"status": "not_executed", "execution_outcome": "not_executed"},
            )
        outcome = await self.runtime.execute(self.spec, tool_call_id, params or {})
        details = dict(outcome.details)
        details["is_error"] = outcome.is_error
        return AgentToolResult(content=[{"type": "text", "text": outcome.text}], details=details)


class ToolRuntime:
    """One per Dify request; holds per-run resources and activated skills."""

    def __init__(
        self,
        *,
        session: Any,
        config: RuntimeConfig,
        ledger: RunLedger,
        skills: SkillCatalog,
        mcp: McpRuntime | None = None,
        artifact_sink: Any = None,
        activity_sink: Any = None,
        dify_tools: list[Any] | None = None,
        stop_requested: Any = None,
        session_io: SessionIO | None = None,
    ) -> None:
        self.session = session
        self.config = config
        self.ledger = ledger
        self.skills = skills
        self.mcp = mcp
        self.artifact_sink = artifact_sink
        self.activity_sink = activity_sink
        self.stop_requested = stop_requested or (lambda: False)
        self.session_io = session_io
        self.activated_skills: list[dict[str, Any]] = []
        self.specs = build_specs(dify_tools or [], mcp)
        self._tools: dict[str, PiTool] = {
            spec.name: PiTool(spec, runtime=self) for spec in self.specs
        }

    def agent_tools(self) -> list[PiTool]:
        return list(self._tools.values())

    def resolve(self, name: str) -> ToolSpec | None:
        tool = self._tools.get(name)
        return tool.spec if tool else None

    async def execute(
        self, spec: ToolSpec, tool_call_id: str, arguments: dict[str, Any]
    ) -> ToolOutcome:
        if self.stop_requested():
            return _not_executed("The run was stopped; no tool was executed.")
        try:
            self.ledger.before_tool(spec.name, arguments)
        except BudgetExceeded as exc:
            return ToolOutcome(
                text=f"Not executed: {exc.message}",
                details={
                    "kind": "budget",
                    "status": "not_executed",
                    "reason": exc.reason,
                    "execution_outcome": "not_executed",
                },
                is_error=True,
            )
        if spec.source == "internal":
            return await self._execute_internal(spec, tool_call_id, arguments)
        if spec.source == "dify":
            return await self._execute_dify(spec, arguments)
        if spec.source == "mcp":
            return await self._execute_mcp(spec, arguments)
        return ToolOutcome(
            text=f"Tool {spec.name} is not available.",
            details={"status": "error", "execution_outcome": "not_executed"},
            is_error=True,
        )

    async def _execute_internal(
        self, spec: ToolSpec, tool_call_id: str, arguments: dict[str, Any]
    ) -> ToolOutcome:
        if spec.name == "activate_skill":
            name = str(arguments.get("name") or "")
            try:
                activation = self.skills.activate(name, activated_by="model")
            except PiError as exc:
                self.ledger.record_tool(True, len(exc.message))
                return ToolOutcome(
                    text=exc.message, details={"kind": "skill", "status": "error"}, is_error=True
                )
            self.activated_skills.append(
                {
                    "name": activation.skill.name,
                    "source": activation.skill.source,
                    "activated_by": "model",
                }
            )
            self.ledger.record_tool(False, len(activation.text))
            self._activity(
                "skill.activate",
                {
                    "tool_call_id": tool_call_id,
                    "skill": activation.skill.name,
                    "source": activation.skill.source,
                    "activated_by": "model",
                },
            )
            return ToolOutcome(
                text=clip(activation.text, self.config.max_result_chars),
                details={
                    "kind": "skill_activation",
                    "skill": activation.skill.name,
                    "source": activation.skill.source,
                    "status": "ok",
                },
            )
        if spec.name == "read_skill_resource":
            name = str(arguments.get("name") or "")
            path = str(arguments.get("path") or "")
            try:
                result = self.skills.read(
                    name,
                    path,
                    offset=_int(arguments.get("offset"), 0),
                    limit=min(
                        _int(arguments.get("limit"), self.config.skill_max_read_chars),
                        self.config.skill_max_read_chars,
                    ),
                )
            except PiError as exc:
                self.ledger.record_tool(True, len(exc.message))
                self._activity(
                    "activity",
                    {"activity": "skill.error", "text": exc.message, "skill": name, "path": path},
                )
                return ToolOutcome(
                    text=exc.message,
                    details={"kind": "skill_read", "status": "error"},
                    is_error=True,
                )
            self.ledger.record_tool(False, len(result.text))
            self._activity(
                "skill.read",
                {
                    "tool_call_id": tool_call_id,
                    "skill": result.skill,
                    "path": result.path,
                    "offset": result.offset,
                    "total_chars": result.total_chars,
                    "next_offset": result.next_offset,
                },
            )
            suffix = (
                f"\n[read {result.offset}..{result.offset + len(result.text)} of "
                f"{result.total_chars}; next_offset={result.next_offset}]"
                if result.next_offset is not None
                else ""
            )
            return ToolOutcome(
                text=clip(result.text + suffix, self.config.max_result_chars),
                details={
                    "kind": "skill_read",
                    "skill": result.skill,
                    "path": result.path,
                    "offset": result.offset,
                    "total_chars": result.total_chars,
                    "next_offset": result.next_offset,
                    "status": "ok",
                },
            )
        return ToolOutcome(
            text=f"Unknown internal tool {spec.name}.", details={"status": "error"}, is_error=True
        )

    async def _execute_dify(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolOutcome:
        entity = spec.entity
        parameters = {
            **(_get(entity, "runtime_parameters") or _get(entity, "tool_configuration") or {}),
            **arguments,
        }

        def invoke() -> Any:
            # The SDK calls are blocking stdio round-trips, so both the invoke
            # and the generator consumption happen off the run loop.
            responses = self.session.tool.invoke(
                provider_type=_provider_type(_tool_provider_type(entity)) if entity else "builtin",
                provider=_tool_provider(entity) if entity else "",
                tool_name=spec.original_name,
                parameters=parameters,
            )
            return normalize_dify_responses(responses)

        try:
            if self.session_io is None:
                normalized = invoke()
            else:
                normalized = await self.session_io.call(
                    invoke,
                    timeout=self.config.tool_timeout_seconds,
                    label="tool",
                    abort=self.stop_requested,
                )
            details = {
                "kind": "tool",
                "source": "dify",
                "status": "ok",
                "execution_outcome": "executed",
                "artifacts": [artifact.public() for artifact in normalized.artifacts],
                "display_text": clip(normalized.text, self.config.display_result_chars),
                "model_chars": len(normalized.text),
                "truncated": len(normalized.text) > self.config.max_result_chars,
            }
            if normalized.metadata:
                details["metadata"] = normalized.metadata
            self.ledger.record_tool(False, len(normalized.text))
            return ToolOutcome(
                text=clip(normalized.text, self.config.max_result_chars),
                details=details,
                artifacts=normalized.artifacts,
            )
        except SessionAborted:
            message = (
                "The run was stopped while the tool was running. The remote execution outcome "
                "is unknown; verify the business result before repeating a write operation."
            )
            self.ledger.record_tool(True, len(message))
            return ToolOutcome(
                text=message,
                details={
                    "kind": "tool",
                    "source": "dify",
                    "status": "unknown",
                    "execution_outcome": "unknown",
                    "business_ref": f"{spec.name}:{_safe_call_ref(spec.name)}",
                },
                is_error=True,
            )
        except TimeoutError:
            message = (
                "The tool call did not respond in time. The remote execution outcome is "
                "unknown; verify the business result before repeating a write operation."
            )
            self.ledger.record_tool(True, len(message))
            return ToolOutcome(
                text=message,
                details={
                    "kind": "tool",
                    "source": "dify",
                    "status": "unknown",
                    "execution_outcome": "unknown",
                    "business_ref": f"{spec.name}:{_safe_call_ref(spec.name)}",
                },
                is_error=True,
            )
        except Exception:
            message = (
                "The tool call failed or its response was lost. The remote execution outcome is "
                "unknown; verify the business result before repeating a write operation."
            )
            self.ledger.record_tool(True, len(message))
            return ToolOutcome(
                text=message,
                details={
                    "kind": "tool",
                    "source": "dify",
                    "status": "unknown",
                    "execution_outcome": "unknown",
                    "business_ref": f"{spec.name}:{_safe_call_ref(spec.name)}",
                },
                is_error=True,
            )

    async def _execute_mcp(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolOutcome:
        if self.mcp is None:
            return ToolOutcome(
                text="The MCP runtime is unavailable.",
                details={"kind": "tool", "source": "mcp", "status": "error"},
                is_error=True,
            )
        try:
            raw = await self.mcp.call(spec.original_name, arguments)
            normalized = normalize_mcp_result(raw)
        except PiError as exc:
            self.ledger.record_tool(True, len(exc.message))
            outcome = str(exc.details.get("execution_outcome") or "unknown")
            return ToolOutcome(
                text=exc.message,
                details={
                    "kind": "tool",
                    "source": "mcp",
                    "server": spec.server,
                    "status": "not_executed" if outcome == "not_executed" else "unknown",
                    "execution_outcome": outcome,
                    "business_ref": f"{spec.name}:{_safe_call_ref(spec.name)}",
                },
                is_error=True,
            )
        except Exception:
            message = "The MCP tool failed. Verify the external outcome before repeating a write."
            self.ledger.record_tool(True, len(message))
            return ToolOutcome(
                text=message,
                details={
                    "kind": "tool",
                    "source": "mcp",
                    "server": spec.server,
                    "status": "unknown",
                    "execution_outcome": "unknown",
                },
                is_error=True,
            )
        public_artifacts = []
        for artifact in normalized.artifacts:
            if artifact.data is not None and self.artifact_sink is not None:
                public_artifacts.append(self.artifact_sink(artifact))
            else:
                public_artifacts.append(artifact.public())
        is_error = bool(_get(raw, "isError", False) or _get(raw, "is_error", False))
        details = {
            "kind": "tool",
            "source": "mcp",
            "server": spec.server,
            "status": "error" if is_error else "ok",
            "execution_outcome": "executed",
            "artifacts": public_artifacts,
            "display_text": clip(normalized.text, self.config.display_result_chars),
            "model_chars": len(normalized.text),
            "truncated": len(normalized.text) > self.config.max_result_chars,
        }
        self.ledger.record_tool(is_error, len(normalized.text))
        return ToolOutcome(
            text=clip(normalized.text, self.config.max_result_chars),
            details=details,
            is_error=is_error,
            artifacts=normalized.artifacts,
        )

    def _activity(self, event_type: str, fields: dict[str, Any]) -> None:
        if self.activity_sink is not None:
            self.activity_sink(event_type, fields)


def build_specs(dify_tools: list[Any], mcp: McpRuntime | None) -> list[ToolSpec]:
    specs: list[ToolSpec] = [
        ToolSpec(
            name="activate_skill",
            description="Activate an eligible application skill listed in the system prompt.",
            parameters=ACTIVATE_SKILL_SCHEMA,
            source="internal",
            original_name="activate_skill",
        ),
        ToolSpec(
            name="read_skill_resource",
            description="Read a bounded, paged text resource belonging to an activated skill.",
            parameters=READ_SKILL_SCHEMA,
            source="internal",
            original_name="read_skill_resource",
        ),
    ]
    used = {spec.name for spec in specs}
    for entity in dify_tools:
        extracted = extract_dify_tool(entity)
        if extracted is None:
            continue
        name = extracted["name"]
        exposed = name
        if exposed in used:
            exposed = f"dify__{_sanitize(extracted.get('provider') or 'tool')}__{name}"
        while exposed in used:
            exposed = f"{exposed}_x"
        used.add(exposed)
        specs.append(
            ToolSpec(
                name=exposed,
                description=extracted["description"],
                parameters=extracted["parameters"],
                source="dify",
                original_name=name,
                entity=entity,
                annotations=extracted.get("annotations") or {},
                identity=_identity_hash(
                    {
                        "source": "dify",
                        "name": name,
                        "provider": _tool_provider(entity),
                        "provider_type": str(
                            getattr(
                                _tool_provider_type(entity), "value", _tool_provider_type(entity)
                            )
                        ),
                        "configuration": _get(entity, "runtime_parameters")
                        or _get(entity, "tool_configuration")
                        or {},
                    }
                ),
            )
        )
    for tool in (mcp.tools() if mcp is not None else []):
        name = tool.exposed_name
        while name in used:
            name = f"{name}_x"
        used.add(name)
        specs.append(
            ToolSpec(
                name=name,
                description=tool.description,
                parameters=tool.parameters,
                source="mcp",
                original_name=tool.exposed_name,
                annotations=tool.annotations,
                server=tool.server,
                identity=_identity_hash(
                    {
                        "source": "mcp",
                        "server": tool.server,
                        "name": tool.name,
                        "endpoint": next(
                            (
                                {"url": server.url, "transport": server.transport}
                                for server in getattr(mcp, "servers", [])
                                if server.name == tool.server
                            ),
                            {},
                        ),
                    }
                ),
            )
        )
    return specs


def _identity_hash(payload: dict[str, Any]) -> str:
    # Store only a digest: configuration may contain secret runtime values.
    raw = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_dify_tool(tool: Any) -> dict[str, Any] | None:
    """Accept Dify entity objects, selector dicts and prompt-schema dicts."""

    if isinstance(tool, dict):
        if isinstance(tool.get("parameters"), dict) and tool.get("name"):
            parameters = tool["parameters"]
            if parameters.get("type") == "object" or "properties" in parameters:
                return {
                    "name": str(tool["name"]),
                    "description": str(tool.get("description") or ""),
                    "parameters": _normalize_schema(parameters),
                }
        if "tool_name" in tool and "tool_parameters" in tool:
            return {
                "name": str(tool.get("tool_name") or ""),
                "description": str(tool.get("tool_description") or tool.get("description") or ""),
                "parameters": _parameters_from_selector(tool.get("tool_parameters") or {}),
            }
    identity = _get(tool, "identity")
    name = str(_get(identity, "name") or _get(tool, "tool_name") or _get(tool, "name") or "")
    if not name:
        return None
    description = _get(tool, "description") or _get(tool, "tool_description") or ""
    if isinstance(description, dict):
        description = (
            description.get("llm")
            or description.get("text")
            or description.get("description")
            or ""
        )
    raw_parameters = _get(tool, "parameters") or []
    parameters = _entity_parameters(raw_parameters)
    annotations = _get(tool, "annotations") or {}
    if hasattr(annotations, "model_dump"):
        annotations = annotations.model_dump(exclude_none=True)
    return {
        "name": name,
        "description": str(description or ""),
        "parameters": parameters,
        "provider": str(_get(identity, "provider") or _get(tool, "provider_id") or ""),
        "annotations": annotations if isinstance(annotations, dict) else {},
    }


def _entity_parameters(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        if raw.get("type") == "object" or "properties" in raw:
            return _normalize_schema(raw)
        raw = raw.get("parameters") or []
    result: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    if not isinstance(raw, list):
        return result
    for parameter in raw:
        name = str(_get(parameter, "name") or "")
        if not name:
            continue
        form = str(getattr(_get(parameter, "form"), "value", _get(parameter, "form")) or "").lower()
        if form and form != "llm":
            continue
        kind = str(
            getattr(_get(parameter, "type"), "value", _get(parameter, "type")) or "string"
        ).lower()
        if kind in {"file", "files"}:
            continue
        input_schema = _get(parameter, "input_schema")
        if isinstance(input_schema, dict):
            schema = dict(input_schema)
        else:
            if kind in {
                "select",
                "secret-input",
                "secret_input",
                "dynamic-select",
                "dynamic_select",
            }:
                kind = "string"
            schema = {
                "type": kind,
                "description": str(
                    _get(parameter, "llm_description") or _get(parameter, "description") or ""
                ),
            }
        options = _get(parameter, "options")
        if options:
            values = [
                str(getattr(_get(option, "value", option), "value", _get(option, "value", option)))
                for option in options
            ]
            values = [value for value in values if value]
            if values:
                schema["enum"] = values
        result["properties"][name] = schema
        if bool(_get(parameter, "required")):
            result["required"].append(name)
    return result


def _parameters_from_selector(selector: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for name, parameter in selector.items():
        kind = str(getattr(_get(parameter, "type"), "value", _get(parameter, "type")) or "string")
        schema = {
            "type": kind if kind not in {"select", "secret-input"} else "string",
            "description": str(_get(parameter, "description") or ""),
        }
        options = _get(parameter, "options")
        if options:
            schema["enum"] = [
                str(getattr(_get(option, "value"), "value", _get(option, "value")))
                for option in options
            ]
        result["properties"][name] = schema
        if bool(_get(parameter, "required")):
            result["required"].append(name)
    return result


def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": schema.get("properties") or {},
        "required": schema.get("required") or [],
        **{
            key: value
            for key, value in schema.items()
            if key not in {"type", "properties", "required"}
        },
    }


def _provider_type(value: Any) -> Any:
    if ToolProviderType is None:
        return value
    try:
        return ToolProviderType(value)
    except Exception:
        return value


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


def _not_executed(message: str) -> ToolOutcome:
    return ToolOutcome(
        text=f"Not executed: {message}",
        details={"status": "not_executed", "execution_outcome": "not_executed"},
    )


def _safe_call_ref(name: str) -> str:
    return name[:40]


def _sanitize(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_") or "tool"


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
