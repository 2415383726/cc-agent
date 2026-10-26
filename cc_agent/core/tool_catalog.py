from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tool_registry import ToolRegistry, ToolSpec


@dataclass(slots=True)
class ToolCatalog:
    """Single owner for model-visible internal and Dify-injected tools."""

    registry: ToolRegistry

    @classmethod
    def create(
        cls,
        *,
        external_tools: list[Any] | None = None,
        external_prompt_tools: list[Any] | None = None,
        output_protocol: str = "agui",
    ) -> "ToolCatalog":
        registry = ToolRegistry.create(
            external_tools=external_tools,
            external_prompt_tools=external_prompt_tools,
            output_protocol=output_protocol,
        )
        return cls(registry=registry)

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
