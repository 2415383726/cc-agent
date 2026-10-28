from __future__ import annotations

from pathlib import Path
from typing import Any

from .messages import TextResourcePage, ToolResult
from .result_budget import ResultBudget

TEXT_RESOURCE_SUFFIXES = {
    ".csv",
    ".html",
    ".json",
    ".md",
    ".svg",
    ".text",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


class SkillRuntime:
    """Read text references bundled with a skill."""

    def __init__(self, max_observation_chars: int = 8000):
        self.max_observation_chars = max_observation_chars

    def read_resource(
        self, skill: dict[str, Any], path: str, limit: int = 12000, *, offset: int = 0
    ) -> ToolResult:
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 128
        ):
            return ToolResult(
                "SkillReadResource",
                "SkillReadResource",
                "Invalid resource range: offset must be nonnegative and limit must be at least 128 characters.",
                is_error=True,
                synthetic=True,
            )
        limit = min(limit, 12000)
        skill_dir, root_error = _skill_dir(skill)
        if root_error:
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation=f"Skill resource error: {root_error} (requested: {path}).",
                is_error=True,
                synthetic=True,
            )
        assert skill_dir is not None
        normalized_path = _normalize_skill_rel_path(path, skill)
        resource_path, error = _resolve_under(skill_dir, normalized_path)
        if error:
            available = _list_skill_dir(skill_dir)
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation=(
                    f"Skill resource error: {error} (requested: {path}, normalized: {normalized_path}). "
                    f"Available under skill root:\n{available}"
                ),
                is_error=True,
                synthetic=True,
            )
        if resource_path.suffix.lower() not in TEXT_RESOURCE_SUFFIXES:
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation=f"Skill resource error: unsupported text resource type: {resource_path.suffix}",
                is_error=True,
                synthetic=True,
            )
        try:
            text = resource_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation="Skill resource error: resource is not UTF-8 text",
                is_error=True,
                synthetic=True,
            )
        except OSError as exc:
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation=f"Skill resource error: {exc}",
                is_error=True,
                synthetic=True,
            )
        result = ToolResult(
            tool_call_id="SkillReadResource",
            tool_name="SkillReadResource",
            llm_observation="",
            resource_page=TextResourcePage(
                normalized_path,
                min(offset, len(text)),
                text[offset : offset + limit],
                len(text),
                min(limit, self.max_observation_chars),
            ),
        )
        return ResultBudget(min(limit, self.max_observation_chars)).apply(result)


def _resolve_under(root: Path, rel_path: str) -> tuple[Path, str]:
    try:
        root_resolved = root.resolve()
        candidate = (root / rel_path).resolve()
        candidate.relative_to(root_resolved)
    except (OSError, ValueError):
        return root, "outside skill directory"
    if not candidate.is_file():
        return candidate, "file not found"
    return candidate, ""


def _list_skill_dir(skill_dir: Path, max_items: int = 50) -> str:
    try:
        items: list[str] = []
        for entry in sorted(skill_dir.rglob("*")):
            rel = entry.relative_to(skill_dir)
            if entry.is_dir():
                items.append(f"  {rel}/")
            else:
                items.append(f"  {rel}")
            if len(items) >= max_items:
                items.append(f"  ... ({max_items} item limit reached)")
                break
        return "\n".join(items) if items else "(empty directory)"
    except OSError:
        return "(directory not readable)"


def _skill_dir(skill: dict[str, Any]) -> tuple[Path | None, str]:
    raw_path = str(skill.get("path") or "").strip()
    if not raw_path:
        return None, "skill has no resource directory"
    path = Path(raw_path)
    skill_dir = path.parent if path.name else path
    if not skill_dir.exists() or not skill_dir.is_dir():
        return None, f"skill directory not found: {skill_dir}"
    return skill_dir, ""


def _normalize_skill_rel_path(rel_path: str, skill: dict[str, Any] | None = None) -> str:
    text = str(rel_path or "").replace("\\", "/").strip()
    if text.startswith("skill://"):
        text = text[len("skill://") :]
    skill = skill if isinstance(skill, dict) else {}
    names = [str(skill.get("name") or "").strip(), str(skill.get("id") or "").strip()]
    for _ in range(4):
        changed = False
        while text.startswith("./"):
            text = text[2:]
            changed = True
        if text.startswith("files/"):
            text = text[len("files/") :]
            changed = True
        for name in names:
            if name and text.lower().startswith(name.lower() + "/"):
                text = text[len(name) + 1 :]
                changed = True
                break
        if not changed:
            break
    return text
