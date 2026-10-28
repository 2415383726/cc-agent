from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .app_skills import load_app_skills
from .builtin_skills import register_all as register_builtin_skills
from .config import AgentRunConfig
from .messages import AgentState
from .skills import filter_denied_skills, load_bundled_skills, render_skill, shlex_split


@dataclass(slots=True)
class SkillCatalog:
    prompt_skills: list[dict[str, Any]] = field(default_factory=list)
    local_skills: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def build(cls, *, config: AgentRunConfig) -> SkillCatalog:
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

    def restore_active(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        visible = {str(skill.get("name") or "").casefold(): skill for skill in self.prompt_skills}
        return [
            record
            for record in records
            if isinstance(record, dict)
            and (skill := visible.get(str(record.get("name") or "").casefold())) is not None
            and record.get("complete") is True
            and record.get("definition_hash") == _definition_hash(skill)
        ][-8:]

    @staticmethod
    def activate(
        state: AgentState, name: str, args: dict[str, Any] | str, *, invocation: str = "model"
    ) -> str:
        skill = next((skill for skill in state.skills if skill.get("name") == name), None)
        if skill is None:
            raise KeyError(f"Skill not found: {name}")
        if invocation == "model" and skill.get("disable_model_invocation"):
            raise PermissionError(f"Skill '{name}' is not available for model invocation.")
        if invocation == "user" and not skill.get("user_invocable", True):
            raise PermissionError(f"Skill '{name}' is not available for user invocation.")
        if isinstance(args, str):
            argv = shlex_split(args)
            args = {
                "_raw": args,
                "_argv": argv,
                **{str(i): value for i, value in enumerate(argv, 1)},
            }
        rendered = render_skill([skill], name, args)
        active = [record for record in state.active_skills if record.get("name") != name]
        state.active_skills = [
            *active,
            {
                "name": name,
                "summary": rendered,
                "definition_hash": _definition_hash(skill),
                "complete": True,
            },
        ][-8:]
        return f"[Skill: {name}]\n{rendered}"

    def render(self, name: str, args: dict[str, Any] | None = None) -> str:
        return render_skill(self.prompt_skills, name, args or {})


def build_skill_catalog(*, config: AgentRunConfig) -> SkillCatalog:
    return SkillCatalog.build(config=config)


def _definition_hash(skill: dict[str, Any]) -> str:
    source = {key: skill.get(key) for key in ("name", "body", "version", "resources", "path")}
    return hashlib.sha256(
        json.dumps(source, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
