from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .app_skills import load_app_skills
from .builtin_skills import register_all as register_builtin_skills
from .config import AgentRunConfig
from .skills import filter_denied_skills, load_bundled_skills, merge_prompt_skills, render_skill


SKILL_MANAGEMENT_REQUIRES_MINIO = "Skill management requires MinIO storage"


@dataclass(slots=True)
class SkillCatalog:
    prompt_skills: list[dict[str, Any]] = field(default_factory=list)
    local_skills: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    skill_library: Any | None = None

    @classmethod
    def build(
        cls,
        *,
        config: AgentRunConfig,
        skill_library: Any | None = None,
    ) -> "SkillCatalog":
        bundled = load_bundled_skills(config.bundled_skill_groups)
        minio_skills = list(getattr(skill_library, "skills", []) or [])
        library_warnings = list(getattr(skill_library, "warnings", []) or [])
        base = merge_prompt_skills(bundled, minio_skills, warnings=library_warnings)
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
            warnings=[*library_warnings, *app_snapshot.warnings],
            skill_library=skill_library,
        )

    def list_visible(self) -> list[dict[str, Any]]:
        return list(self.prompt_skills)

    def all_skills(self) -> list[dict[str, Any]]:
        return [*self.prompt_skills, *self.local_skills]

    def render(self, name: str, args: dict[str, Any] | None = None) -> str:
        return render_skill(self.prompt_skills, name, args or {})

    def install_user_skill(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(SKILL_MANAGEMENT_REQUIRES_MINIO)

    def remove_user_skill(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(SKILL_MANAGEMENT_REQUIRES_MINIO)

    def close(self) -> None:
        if self.skill_library is not None:
            self.skill_library.close()


class MinioSkillCatalog(SkillCatalog):
    def install_user_skill(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if self.skill_library is None:
            raise NotImplementedError(SKILL_MANAGEMENT_REQUIRES_MINIO)
        return self.skill_library.install(*args, **kwargs)

    def remove_user_skill(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if self.skill_library is None:
            raise NotImplementedError(SKILL_MANAGEMENT_REQUIRES_MINIO)
        return self.skill_library.remove(*args, **kwargs)


def build_skill_catalog(*, config: AgentRunConfig, skill_library: Any | None = None) -> SkillCatalog:
    base = SkillCatalog.build(config=config, skill_library=skill_library)
    if skill_library is None:
        return base
    return MinioSkillCatalog(
        prompt_skills=base.prompt_skills,
        local_skills=base.local_skills,
        warnings=base.warnings,
        skill_library=skill_library,
    )
