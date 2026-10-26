from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SkillRegistrySnapshot:
    skills: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)


class SkillRegistry:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parent.parent / "skills"

    def load(self) -> SkillRegistrySnapshot:
        skills: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        if not self.root.exists():
            return SkillRegistrySnapshot(skills=skills, warnings=warnings)

        for skill_path in sorted(self.root.rglob("SKILL.md")):
            try:
                skills.append(self._load_skill(skill_path))
            except ValueError as exc:
                warnings.append({"path": str(skill_path), "reason": str(exc)})
            except OSError as exc:
                warnings.append({"path": str(skill_path), "reason": f"read error: {exc}"})
        return SkillRegistrySnapshot(skills=skills, warnings=warnings)

    def _load_skill(self, skill_path: Path) -> dict[str, Any]:
        text = skill_path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        metadata = _parse_frontmatter(frontmatter)
        description = str(metadata.get("description") or "").strip()
        if not description:
            raise ValueError("missing required description")

        skill_dir = skill_path.parent
        normalized = _normalize_metadata(metadata)
        unknown = {
            key: value
            for key, value in metadata.items()
            if _canonical_key(key) not in _KNOWN_KEYS
        }
        skill_id = skill_dir.name
        display_name = str(normalized.get("name") or skill_id).strip() or skill_id
        ui_metadata = _load_ui_metadata(skill_dir)
        extra_metadata = dict(unknown)
        if isinstance(normalized.get("metadata"), dict):
            extra_metadata["metadata"] = normalized.get("metadata")
        return {
            "id": skill_id,
            "name": skill_id,
            "display_name": display_name,
            "kind": "prompt",
            "description": description,
            "body": body.strip(),
            "path": str(skill_path),
            "source": "bundled",
            "allowed_tools": _as_list(normalized.get("allowed_tools")),
            "argument_hint": _none_or_str(normalized.get("argument_hint")),
            "when_to_use": _none_or_str(normalized.get("when_to_use")),
            "version": _none_or_str(normalized.get("version")),
            "model": _none_or_str(normalized.get("model")),
            "shell": _none_or_str(normalized.get("shell")),
            "effort": _none_or_str(normalized.get("effort")),
            "context": _context_value(normalized.get("context")),
            "user_invocable": bool(normalized.get("user_invocable", True)),
            "disable_model_invocation": bool(normalized.get("disable_model_invocation", False)),
            "resources": resource_index(skill_dir),
            "ui": ui_metadata,
            "metadata": extra_metadata,
        }


def resource_index(skill_dir: str | Path) -> dict[str, list[str]]:
    root = Path(skill_dir)
    resources: dict[str, list[str]] = {}
    for folder in ("references", "assets", "scripts"):
        base = root / folder
        if not base.exists():
            resources[folder] = []
            continue
        files = []
        for path in sorted(item for item in base.rglob("*") if item.is_file()):
            files.append(path.relative_to(root).as_posix())
        resources[folder] = files
    return resources


def load_bundled_skill_snapshot(
    groups: tuple[str, ...] | list[str] | None = None,
) -> SkillRegistrySnapshot:
    group_key = None if groups is None else tuple(str(group) for group in groups)
    return _load_bundled_skill_snapshot_cached(group_key)


@lru_cache(maxsize=None)
def _load_bundled_skill_snapshot_cached(
    groups: tuple[str, ...] | None,
) -> SkillRegistrySnapshot:
    root = Path(__file__).resolve().parent.parent / "skills"
    if groups is None:
        return SkillRegistry(root).load()

    skills: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for group in groups:
        snapshot = SkillRegistry(root / group).load()
        skills.extend(snapshot.skills)
        warnings.extend(snapshot.warnings)
    return SkillRegistrySnapshot(skills=skills, warnings=warnings)


def _split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    raise ValueError("unterminated YAML frontmatter")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    current_list_key: str | None = None
    lines = text.splitlines()
    for line_index, raw_line in enumerate(lines):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1] if stack else root
        if stripped.startswith("- "):
            if not isinstance(parent, list):
                if not isinstance(stack[-2][1], dict) or current_list_key is None:
                    raise ValueError(f"invalid frontmatter list item: {stripped}")
                parent = stack[-2][1].setdefault(current_list_key, [])
                stack[-1] = (stack[-1][0], parent)
            parent.append(_parse_scalar(stripped[2:].strip()))
            continue
        if ":" not in stripped:
            raise ValueError(f"invalid frontmatter line: {stripped}")
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key or not isinstance(parent, dict):
            raise ValueError("invalid frontmatter mapping")
        if value:
            parent[key] = _parse_scalar(value)
            current_list_key = None
        else:
            next_value: list[Any] | dict[str, Any] = (
                [] if _next_content_line(lines, line_index).startswith("- ") else {}
            )
            parent[key] = next_value
            current_list_key = key
            stack.append((indent, next_value))
    return root


def _next_content_line(lines: list[str], line_index: int) -> str:
    for raw_line in lines[line_index + 1 :]:
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    if value.startswith("{") and value.endswith("}"):
        try:
            return __import__("json").loads(value)
        except Exception:
            return value
    return value


def _load_ui_metadata(skill_dir: Path) -> dict[str, Any]:
    path = skill_dir / "agents" / "openai.yaml"
    if not path.is_file():
        return {}
    try:
        parsed = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {_canonical_key(key): value for key, value in metadata.items()}


def _canonical_key(key: str) -> str:
    return key.replace("-", "_")


_KNOWN_KEYS = {
    "name",
    "description",
    "allowed_tools",
    "argument_hint",
    "when_to_use",
    "version",
    "model",
    "shell",
    "effort",
    "context",
    "metadata",
    "license",
    "compatibility",
    "agent",
    "paths",
    "hooks",
    "arguments",
    "disallowed_tools",
    "user_invocable",
    "disable_model_invocation",
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _context_value(value: Any) -> Any:
    if value is None:
        return []
    return value


def _none_or_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
