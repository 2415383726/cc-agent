from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .app_skills import load_app_skills
from .builtin_skills import register_all as register_builtin_skills
from .config import AgentRunConfig
from .skills import filter_denied_skills, load_bundled_skills, render_skill


@dataclass(slots=True)
class SkillCatalog:
    prompt_skills: list[dict[str, Any]] = field(default_factory=list)
    local_skills: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        *,
        config: AgentRunConfig,
    ) -> "SkillCatalog":
        bundled = load_bundled_skills(config.bundled_skill_groups)
        base = bundled
        local = register_builtin_skills()
        reserved_names = {
            str(skill.get("name") or "").lower()
            for skill in [*base, *local]
            if str(skill.get("name") or "").strip()
        }
        app_snapshot = load_app_skills(config.app_skills_yaml, reserved_names=reserved_names)
        return cls(
            prompt_skills=filter_denied_skills(base + app_snapshot.skills, config.skill_denylist),
            local_skills=filter_denied_skills(local, config.skill_denylist),
            warnings=app_snapshot.warnings,
        )

    def list_visible(self) -> list[dict[str, Any]]:
        return list(self.prompt_skills)

    def all_skills(self) -> list[dict[str, Any]]:
        return [*self.prompt_skills, *self.local_skills]

    def render(self, name: str, args: dict[str, Any] | None = None) -> str:
        return render_skill(self.prompt_skills, name, args or {})


def build_skill_catalog(*, config: AgentRunConfig) -> SkillCatalog:
    return SkillCatalog.build(config=config)
