"""Application/builtin skills: eligibility, activation, bounded resource reads."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pi_agent_harness.types import Skill

from .errors import PiError

SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(slots=True)
class SkillDefinition:
    name: str
    description: str
    content: str
    source: str = "app"
    resources: dict[str, str] = field(default_factory=dict)
    requires_tools: tuple[str, ...] = ()
    enabled: bool = True
    disable_model_invocation: bool = False

    def to_pi_skill(self) -> Skill:
        return Skill(
            name=self.name,
            description=self.description,
            content=self.content,
            filePath=f"skill://{self.name}/SKILL.md",
            disableModelInvocation=self.disable_model_invocation,
        )


@dataclass(slots=True)
class SkillActivation:
    skill: SkillDefinition
    text: str
    activated_by: str


@dataclass(slots=True)
class ReadResult:
    skill: str
    path: str
    text: str
    offset: int
    total_chars: int
    next_offset: int | None


class SkillCatalog:
    def __init__(self, skills: list[SkillDefinition], diagnostics: list[str] | None = None):
        self.skills = {skill.name: skill for skill in skills}
        self.diagnostics = list(diagnostics or [])

    @classmethod
    def load(
        cls,
        *,
        app_yaml: str = "",
        builtin_dir: Path | None = None,
        available_tools: set[str] | None = None,
        max_skills: int = 40,
    ) -> SkillCatalog:
        available = available_tools or set()
        definitions: list[SkillDefinition] = []
        diagnostics: list[str] = []
        if builtin_dir and builtin_dir.is_dir():
            for skill_file in sorted(builtin_dir.glob("*/SKILL.md"))[:max_skills]:
                try:
                    definition = _parse_skill_file(skill_file, source="builtin")
                except Exception:
                    diagnostics.append(f"invalid builtin skill: {skill_file.parent.name}")
                    continue
                if definition:
                    definitions.append(definition)
        for raw in _parse_app_yaml(app_yaml, diagnostics):
            definition = _definition_from_mapping(raw, source="app", diagnostics=diagnostics)
            if definition:
                definitions.append(definition)
        deduped: dict[str, SkillDefinition] = {}
        for definition in definitions:
            if definition.name in deduped:
                diagnostics.append(f"duplicate skill ignored: {definition.name}")
                continue
            deduped[definition.name] = definition
        catalog = cls(list(deduped.values())[:max_skills], diagnostics)
        catalog.available_tools = available
        return catalog

    def eligible(self) -> list[SkillDefinition]:
        available = getattr(self, "available_tools", set())
        return [
            skill
            for skill in self.skills.values()
            if skill.enabled
            and skill.name
            and SKILL_NAME.match(skill.name)
            and all(tool in available for tool in skill.requires_tools)
        ]

    def eligible_names(self) -> set[str]:
        return {skill.name for skill in self.eligible()}

    def get(self, name: str) -> SkillDefinition | None:
        skill = self.skills.get(str(name or "").strip())
        if skill is None:
            return None
        return skill if skill.name in self.eligible_names() else None

    def pi_skills(self) -> list[Skill]:
        return [skill.to_pi_skill() for skill in self.eligible()]

    def activate(self, name: str, *, activated_by: str) -> SkillActivation:
        skill = self.get(name)
        if skill is None:
            raise PiError(
                code="tool_failed",
                stage="skill",
                message=f"Skill {name!r} is not available in this application.",
            )
        if skill.disable_model_invocation and activated_by == "model":
            raise PiError(
                code="tool_failed",
                stage="skill",
                message=f"Skill {name!r} cannot be activated by the model.",
            )
        base = f"skill://{skill.name}/"
        text = (
            f"Use skill `{skill.name}`.\n"
            f"References are relative to {base}.\n\n"
            f"{skill.content.strip()}"
        )
        return SkillActivation(skill=skill, text=text, activated_by=activated_by)

    def read(self, name: str, path: str, *, offset: int = 0, limit: int = 8_000) -> ReadResult:
        skill = self.get(name)
        if skill is None:
            raise PiError(
                code="tool_failed", stage="skill", message=f"Skill {name!r} is not available."
            )
        normalized = normalize_skill_path(path)
        if normalized not in skill.resources:
            raise PiError(
                code="tool_failed",
                stage="skill",
                message="The requested resource does not belong to this skill.",
            )
        content = skill.resources[normalized]
        start = max(0, int(offset))
        if start >= len(content) and content:
            raise PiError(
                code="tool_failed",
                stage="skill",
                message="The resource read offset is past the end.",
            )
        size = max(1, min(int(limit), 20_000))
        text = content[start : start + size]
        next_offset = start + len(text) if start + len(text) < len(content) else None
        return ReadResult(
            skill=skill.name,
            path=normalized,
            text=text,
            offset=start,
            total_chars=len(content),
            next_offset=next_offset,
        )

    def system_section(self) -> str:
        skills = self.eligible()
        if not skills:
            return ""
        lines = [
            "",
            "",
            "The following application skills provide specialized instructions.",
            "Call `activate_skill` with the skill name when the task matches its description.",
            "Use `read_skill_resource` for referenced text; reads are bounded and paged.",
            "",
            "<available_skills>",
        ]
        for skill in skills:
            lines.extend(
                [
                    "  <skill>",
                    f"    <name>{_escape(skill.name)}</name>",
                    f"    <description>{_escape(skill.description)}</description>",
                    "  </skill>",
                ]
            )
        lines.append("</available_skills>")
        return "\n".join(lines)


def normalize_skill_path(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or "\x00" in text:
        raise PiError(code="tool_failed", stage="skill", message="Invalid skill resource path.")
    pure = PurePosixPath(text)
    if any(part in {"..", "."} for part in pure.parts):
        raise PiError(code="tool_failed", stage="skill", message="Invalid skill resource path.")
    return str(pure)


def _parse_app_yaml(value: str, diagnostics: list[str]) -> list[dict[str, Any]]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        diagnostics.append("invalid app_skills_yaml")
        return []
    if isinstance(payload, dict):
        payload = payload.get("skills")
    if not isinstance(payload, list):
        diagnostics.append("app_skills_yaml must contain a skills list")
        return []
    return [item for item in payload if isinstance(item, dict)]


def _definition_from_mapping(
    raw: dict[str, Any], *, source: str, diagnostics: list[str]
) -> SkillDefinition | None:
    name = str(raw.get("name") or "").strip()
    if not name or not SKILL_NAME.match(name):
        diagnostics.append(f"invalid skill name: {name or '<empty>'}")
        return None
    description = str(raw.get("description") or "").strip()
    content = str(raw.get("content") or raw.get("instructions") or raw.get("body") or "").strip()
    if not description or not content:
        diagnostics.append(f"skill {name} is missing description or content")
        return None
    resources: dict[str, str] = {}
    raw_resources = raw.get("resources") or {}
    if isinstance(raw_resources, dict):
        iterable = raw_resources.items()
    elif isinstance(raw_resources, list):
        iterable = [
            (str(item.get("path") or ""), item.get("content") or "")
            for item in raw_resources
            if isinstance(item, dict)
        ]
    else:
        iterable = []
    for path, value in iterable:
        try:
            normalized = normalize_skill_path(str(path))
        except PiError:
            diagnostics.append(f"skill {name} has an invalid resource path")
            continue
        if normalized and isinstance(value, str):
            resources[normalized] = value
    requires_tools = raw.get("requires_tools") or raw.get("tools") or []
    if isinstance(requires_tools, str):
        requires_tools = [requires_tools]
    return SkillDefinition(
        name=name,
        description=description,
        content=content,
        source=source,
        resources=resources,
        requires_tools=tuple(str(item) for item in requires_tools if str(item).strip()),
        enabled=bool(raw.get("enabled", True)),
        disable_model_invocation=bool(raw.get("disable_model_invocation", False)),
    )


def _parse_skill_file(path: Path, *, source: str) -> SkillDefinition | None:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        _, _, rest = text.partition("---")
        frontmatter, _, body = rest.partition("---")
        metadata = yaml.safe_load(frontmatter) or {}
    else:
        metadata = {}
        body = text
    if not isinstance(metadata, dict):
        return None
    resources: dict[str, str] = {}
    for resource in sorted(path.parent.rglob("*")):
        if not resource.is_file() or resource.name == "SKILL.md":
            continue
        try:
            relative = resource.relative_to(path.parent).as_posix()
            resources[normalize_skill_path(relative)] = resource.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, PiError):
            continue
    return _definition_from_mapping(
        {
            "name": metadata.get("name") or path.parent.name,
            "description": metadata.get("description") or "",
            "content": body.strip(),
            "resources": resources,
            "disable_model_invocation": metadata.get("disable-model-invocation", False),
        },
        source=source,
        diagnostics=[],
    )


def _escape(value: str) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
