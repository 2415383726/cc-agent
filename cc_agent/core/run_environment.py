from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AgentRunConfig
from .protocol_renderer import ProtocolRenderer
from .skill_catalog import SkillCatalog, build_skill_catalog
from .state_backend import DifyStateBackend, StateBackend, StateLoad
from .tool_catalog import ToolCatalog


@dataclass(slots=True)
class RunEnvironment:
    config: AgentRunConfig
    parameters: dict[str, Any]
    strategy: Any
    thread_id: str
    run_id: str
    state_id: str
    renderer: ProtocolRenderer
    skill_catalog: SkillCatalog
    state_backend: StateBackend
    loaded_state: StateLoad | None = None
    tool_catalog: ToolCatalog | None = None

    @classmethod
    def open(
        cls,
        *,
        config: AgentRunConfig,
        parameters: dict[str, Any],
        strategy: Any,
        thread_id: str,
        run_id: str,
        state_id: str,
        renderer: ProtocolRenderer | None = None,
    ) -> "RunEnvironment":
        return cls(
            config=config,
            parameters=parameters,
            strategy=strategy,
            thread_id=thread_id,
            run_id=run_id,
            state_id=state_id,
            renderer=renderer or ProtocolRenderer(
                config.output_protocol,
                thread_id=thread_id,
                run_id=run_id,
                show_tool_calls=config.show_tool_calls,
            ),
            skill_catalog=build_skill_catalog(config=config),
            state_backend=DifyStateBackend(config, state_id=state_id),
        )

    def load_state(self) -> dict[str, Any]:
        self.loaded_state = self.state_backend.load()
        return self.loaded_state.to_runtime_dict()

    def build_tool_catalog(self, *, external_tools: list[Any], external_prompt_tools: list[Any]) -> ToolCatalog:
        self.tool_catalog = ToolCatalog.create(
            external_tools=external_tools,
            external_prompt_tools=external_prompt_tools,
            output_protocol=self.config.output_protocol,
        )
        return self.tool_catalog
