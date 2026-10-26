from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any


@dataclass(slots=True)
class AppSkillSnapshot:
    skills: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)


_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_KNOWN_KEYS = {
    "name",
    "display_name",
    "description",
    "instructions",
    "when_to_use",
    "argument_hint",
    "allowed_tools",
    "user_invocable",
    "disable_model_invocation",
}


def load_app_skills(raw: Any, reserved_names: set[str] | None = None) -> AppSkillSnapshot:
    text = str(raw or "").strip()
    if not text:
        return AppSkillSnapshot()

    try:
        items = _parse_app_skill_items(text)
    except ValueError as exc:
        return AppSkillSnapshot(warnings=[{"path": "app_skills_yaml", "reason": str(exc)}])

    reserved = {str(name).strip().lower() for name in (reserved_names or set()) if str(name).strip()}
    skills: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        skill, warning = _normalize_app_skill(item, index=index, reserved_names=reserved | seen)
        if warning:
            warnings.append(warning)
            continue
        if skill is not None:
            skills.append(skill)
            seen.add(str(skill["name"]).lower())
    return AppSkillSnapshot(skills=skills, warnings=warnings)


def _parse_app_skill_items(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON app skills: {exc}") from exc
        if isinstance(parsed, dict):
            parsed = parsed.get("skills")
        if not isinstance(parsed, list):
            raise ValueError("app skills JSON must be a list or an object with a skills list")
        if not all(isinstance(item, dict) for item in parsed):
            raise ValueError("app skills JSON list items must be objects")
        return [dict(item) for item in parsed]
    return _parse_yaml_list(text)


def _parse_yaml_list(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_list_key: str | None = None
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0 and stripped.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            current_list_key = None
            rest = stripped[2:].strip()
            if rest:
                key, value, block = _parse_key_value(rest, lines, index, indent)
                if block is not None:
                    current[key] = block.value
                    index = block.next_index
                    continue
                current[key] = value
            index += 1
            continue
        if current is None:
            raise ValueError(f"expected '- name: ...' list item, got: {stripped}")
        if indent <= 0:
            raise ValueError(f"invalid app skill line: {stripped}")
        if stripped.startswith("- "):
            if current_list_key is None or not isinstance(current.get(current_list_key), list):
                raise ValueError(f"list item has no parent key: {stripped}")
            current[current_list_key].append(_parse_scalar(stripped[2:].strip()))
            index += 1
            continue
        key, value, block = _parse_key_value(stripped, lines, index, indent)
        if block is not None:
            current[key] = block.value
            current_list_key = None
            index = block.next_index
            continue
        current[key] = value
        current_list_key = key if isinstance(value, list) else None
        index += 1
    if current is not None:
        items.append(current)
    if not items:
        raise ValueError("app_skills_yaml must contain a YAML list")
    return items


@dataclass(slots=True)
class _BlockValue:
    value: str
    next_index: int


def _parse_key_value(
    stripped_line: str,
    lines: list[str],
    index: int,
    indent: int,
) -> tuple[str, Any, _BlockValue | None]:
    if ":" not in stripped_line:
        raise ValueError(f"invalid mapping line: {stripped_line}")
    key, raw_value = stripped_line.split(":", 1)
    key = _canonical_key(key.strip())
    if not key:
        raise ValueError("empty app skill key")
    value = raw_value.strip()
    if value == "|":
        block, next_index = _read_block(lines, index + 1, parent_indent=indent)
        return key, None, _BlockValue(block, next_index)
    if value == "":
        return key, [], None
    return key, _parse_scalar(value), None


def _read_block(lines: list[str], start: int, parent_indent: int) -> tuple[str, int]:
    collected: list[str] = []
    index = start
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip(" "))
        if stripped and indent <= parent_indent:
            break
        collected.append(raw)
        index += 1
    non_blank_indents = [len(line) - len(line.lstrip(" ")) for line in collected if line.strip()]
    trim = min(non_blank_indents) if non_blank_indents else 0
    return "\n".join(line[trim:] if len(line) >= trim else "" for line in collected).strip(), index


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
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    return value


def _normalize_app_skill(
    item: dict[str, Any],
    *,
    index: int,
    reserved_names: set[str],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    normalized = {_canonical_key(str(key)): value for key, value in item.items()}
    name = str(normalized.get("name") or "").strip()
    if not name:
        return None, _warning(index, "missing required name")
    if not _NAME_RE.match(name):
        return None, _warning(index, f"invalid name: {name}")
    if name.lower() in reserved_names:
        return None, _warning(index, f"skill name conflicts with existing skill or command: {name}")

    description = str(normalized.get("description") or "").strip()
    instructions = str(normalized.get("instructions") or "").strip()
    if not description:
        return None, _warning(index, f"{name}: missing required description")
    if not instructions:
        return None, _warning(index, f"{name}: missing required instructions")

    unknown = {key: value for key, value in normalized.items() if key not in _KNOWN_KEYS}
    skill = {
        "id": name,
        "name": name,
        "display_name": str(normalized.get("display_name") or name).strip() or name,
        "kind": "prompt",
        "description": description,
        "body": instructions,
        "path": "",
        "source": "app",
        "allowed_tools": _as_list(normalized.get("allowed_tools")),
        "argument_hint": _none_or_str(normalized.get("argument_hint")),
        "when_to_use": _none_or_str(normalized.get("when_to_use")),
        "version": None,
        "model": None,
        "shell": None,
        "effort": None,
        "context": [],
        "user_invocable": _bool(normalized.get("user_invocable"), True),
        "disable_model_invocation": _bool(normalized.get("disable_model_invocation"), False),
        "resources": {"references": [], "assets": [], "scripts": []},
        "ui": {},
        "metadata": {"app_skills_yaml": unknown} if unknown else {},
    }
    return skill, None


def _warning(index: int, reason: str) -> dict[str, str]:
    return {"path": f"app_skills_yaml[{index}]", "reason": reason}


def _canonical_key(key: str) -> str:
    return key.replace("-", "_")


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [item for item in value if str(item).strip()]
    return [value]


def _none_or_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return bool(value)
