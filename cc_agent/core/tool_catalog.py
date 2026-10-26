from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .profiles import RuntimeProfile, profile_for_mode
from .tool_registry import ToolRegistry, ToolSpec


@dataclass(slots=True)
class ToolCatalog:
    """Single policy owner for model-visible tools in a run profile."""

    profile: RuntimeProfile
    registry: ToolRegistry

    @classmethod
    def create(
        cls,
        *,
        capability_mode: str,
        external_tools: list[Any] | None = None,
        external_prompt_tools: list[Any] | None = None,
        output_protocol: str = "agui",
    ) -> "ToolCatalog":
        profile = profile_for_mode(capability_mode)
        registry = ToolRegistry.create(
            external_tools=external_tools,
            external_prompt_tools=external_prompt_tools,
            capability_mode=profile.capability_mode,
            output_protocol=output_protocol,
        )
        return cls(profile=profile, registry=registry)

    def resolve(self, name: str) -> ToolSpec | None:
        return self.registry.resolve(name)

    def names(self) -> list[str]:
        return self.registry.names()

    def names_by_kind(self, kind: str) -> list[str]:
        return self.registry.names_by_kind(kind)

    def prompt_tools(self) -> list[Any]:
        return self.registry.prompt_tools()

    def assert_available(self, name: str) -> None:
        spec = self.resolve(name)
        if spec is None:
            raise ValueError(f"Tool not found: {name}")
        if spec.kind == "internal" and name not in self.profile.internal_tools:
            raise ValueError(f"{name} is not available in capability_mode={self.profile.capability_mode}")
