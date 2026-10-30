"""Minimal adapter subclass for the two seams AgentHarness 0.6.0 does not expose."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pi_agent_core.types import AgentLoopConfig, AgentMessage
from pi_agent_harness.agent_harness import AgentHarness
from pi_agent_harness.types import AgentHarnessError


class PiHarness(AgentHarness):
    """Adds a turn-stop predicate and a resume turn seeded with a custom message.

    Both changes are deliberately tiny and fixed to harness 0.6.0: the loop
    config is produced by ``super()`` and only ``should_stop_after_turn`` is
    added; resume reuses the upstream turn runner instead of copying the loop.
    Contract tests pin both seams against the pinned dependency.
    """

    def __init__(
        self,
        *args: Any,
        stop_predicate: Callable[[], bool | Awaitable[bool]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._stop_predicate = stop_predicate

    def _create_loop_config(
        self, get_turn_state: Callable[[], Any], set_turn_state: Callable[[Any], None]
    ) -> AgentLoopConfig:
        config = super()._create_loop_config(get_turn_state, set_turn_state)
        if self._stop_predicate is not None:

            async def should_stop(_ctx: Any) -> bool:
                result = self._stop_predicate()
                if hasattr(result, "__await__"):
                    result = await result
                return bool(result)

            config.should_stop_after_turn = should_stop
        return config

    async def resume_with(self, message: AgentMessage) -> Any:
        """Run one turn whose opening message is *message* rather than synthesized text."""

        if self._closed:
            raise AgentHarnessError("invalid_state", "AgentHarness is closed")
        if self.phase != "idle":
            raise AgentHarnessError("busy", "AgentHarness is busy")
        await self._ensure_extensions_loaded()
        return await self._run_turn("", message=message)
