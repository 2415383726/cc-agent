from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from .internal_tools import INTERNAL_TOOL_NAMES, internal_tool_schemas


@dataclass(slots=True)
class ToolSpec:
    name: str
    kind: str
    original_name: str
    entity: Any | None = None
    prompt_tool: Any | None = None


class ToolCatalog:
    def __init__(self, specs: dict[str, ToolSpec]):
        self._specs = specs

    @classmethod
    def create(
        cls,
        external_tools: list[Any] | None = None,
        external_prompt_tools: list[Any] | None = None,
        output_protocol: str = "agui",
        mcp_tools: list[ToolSpec] | None = None,
    ) -> "ToolCatalog":
        specs: dict[str, ToolSpec] = {}
        for schema in internal_tool_schemas(output_protocol=output_protocol):
            specs[schema["name"]] = ToolSpec(
                name=schema["name"],
                kind="internal",
                original_name=schema["name"],
                prompt_tool=schema,
            )

        prompt_tools_by_name = {
            _prompt_tool_name(prompt_tool): prompt_tool
            for prompt_tool in external_prompt_tools or []
            if _prompt_tool_name(prompt_tool)
        }
        for entity in external_tools or []:
            original_name = _entity_name(entity)
            if not original_name:
                continue
            exposed_name = original_name
            if exposed_name in specs or exposed_name in INTERNAL_TOOL_NAMES:
                exposed_name = _namespaced_external_name(entity, original_name)
                while exposed_name in specs:
                    exposed_name = f"{exposed_name}_x"
            prompt_tool = prompt_tools_by_name.get(original_name)
            if prompt_tool is not None and exposed_name != original_name:
                prompt_tool = _rename_prompt_tool(prompt_tool, exposed_name)
            specs[exposed_name] = ToolSpec(
                name=exposed_name,
                kind="external",
                original_name=original_name,
                entity=entity,
                prompt_tool=prompt_tool,
            )
        for spec in mcp_tools or []:
            if spec.name in specs:
                raise ValueError("MCP tool name conflicts with an existing tool.")
            specs[spec.name] = spec
        return cls(specs)

    def resolve(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return list(self._specs.keys())

    def names_by_kind(self, kind: str) -> list[str]:
        return [name for name, spec in self._specs.items() if spec.kind == kind]

    def prompt_tools(self) -> list[Any]:
        return [spec.prompt_tool for spec in self._specs.values() if spec.prompt_tool is not None]


def _entity_name(entity: Any) -> str:
    identity = getattr(entity, "identity", None)
    if isinstance(entity, dict):
        identity = entity.get("identity", identity)
    return str(_get(identity, "name") or _get(entity, "tool_name") or _get(entity, "name") or "")


def _entity_provider(entity: Any) -> str:
    identity = getattr(entity, "identity", None)
    if isinstance(entity, dict):
        identity = entity.get("identity", identity)
    return str(
        _get(identity, "provider")
        or _get(entity, "provider")
        or _get(entity, "provider_id")
        or "external"
    )


def _namespaced_external_name(entity: Any, original_name: str) -> str:
    provider = re.sub(r"[^0-9A-Za-z_]+", "_", _entity_provider(entity)).strip("_") or "external"
    return f"dify__{provider}__{original_name}"


def _prompt_tool_name(prompt_tool: Any) -> str:
    return str(_get(prompt_tool, "name") or "")


def _rename_prompt_tool(prompt_tool: Any, name: str) -> Any:
    if isinstance(prompt_tool, dict):
        renamed = copy.deepcopy(prompt_tool)
        renamed["name"] = name
        return renamed
    if hasattr(prompt_tool, "model_copy"):
        return prompt_tool.model_copy(update={"name": name})
    if hasattr(prompt_tool, "copy"):
        return prompt_tool.copy(update={"name": name})
    renamed = copy.deepcopy(prompt_tool)
    try:
        setattr(renamed, "name", name)
    except Exception:
        return prompt_tool
    return renamed


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
