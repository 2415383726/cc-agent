from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DIFY_ONLY = "dify_only"
MINIO = "minio"
CAPABILITY_MODES = {DIFY_ONLY, MINIO}

AGUI = "agui"
DIFY_NATIVE = "dify_native"

BASE_INTERNAL_TOOLS = {
    "SkillList",
    "Skill",
    "SkillReadResource",
    "MemoryList",
    "MemorySearch",
    "MemorySave",
    "MemoryDelete",
    "TaskCreate",
    "TaskUpdate",
    "TaskGet",
    "TaskList",
    "UserPrompt",
}

MINIO_INTERNAL_TOOLS = {
    "list_files",
    "inspect_file",
    "read_file",
    "write_file",
    "delete_file",
    "run_python",
    "SkillRunScript",
    "SkillInstall",
    "SkillRemove",
}


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    capability_mode: str
    workspace_available: bool = False
    minio_enabled: bool = False
    runner_enabled: bool = False
    skill_management_enabled: bool = False
    skill_scripts_enabled: bool = False

    @property
    def internal_tools(self) -> set[str]:
        tools = set(BASE_INTERNAL_TOOLS)
        if self.capability_mode == MINIO:
            tools.update(MINIO_INTERNAL_TOOLS)
        return tools


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    """Immutable product-surface choices for one Dify strategy entry."""

    name: str
    output_protocol: str
    bundled_skill_groups: tuple[str, ...]
    structured_answers: bool = False
    user_skill_scripts_enabled: bool = True


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

def normalize_capability_mode(value: Any) -> str:
    mode = str(value or DIFY_ONLY).strip().lower()
    if not mode:
        mode = DIFY_ONLY
    if mode not in CAPABILITY_MODES:
        raise ValueError(f"unsupported capability_mode: {mode}")
    return mode


def profile_for_mode(mode: Any) -> RuntimeProfile:
    normalized = normalize_capability_mode(mode)
    if normalized == MINIO:
        return RuntimeProfile(
            capability_mode=MINIO,
            workspace_available=True,
            minio_enabled=True,
            runner_enabled=True,
            skill_management_enabled=True,
            skill_scripts_enabled=True,
        )
    return RuntimeProfile(capability_mode=DIFY_ONLY)


def internal_tools_for_mode(mode: Any) -> set[str]:
    return profile_for_mode(mode).internal_tools
