from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AGUI = "agui"
DIFY_NATIVE = "dify_native"

@dataclass(frozen=True, slots=True)
class StrategyProfile:
    """Immutable product-surface choices for one Dify strategy entry."""

    name: str
    output_protocol: str
    bundled_skill_groups: tuple[str, ...]
    structured_answers: bool = False


AGUI_STRATEGY_PROFILE = StrategyProfile(
    name="agui",
    output_protocol=AGUI,
    bundled_skill_groups=("common", "agui"),
    structured_answers=True,
)

DIFY_STRATEGY_PROFILE = StrategyProfile(
    name="dify",
    output_protocol=DIFY_NATIVE,
    bundled_skill_groups=("common",),
)


def strategy_profile_for_output(output_protocol: Any) -> StrategyProfile:
    protocol = str(output_protocol or AGUI).strip().lower()
    if protocol == AGUI:
        return AGUI_STRATEGY_PROFILE
    if protocol == DIFY_NATIVE:
        return DIFY_STRATEGY_PROFILE
    raise ValueError(f"unsupported output_protocol: {output_protocol}")
