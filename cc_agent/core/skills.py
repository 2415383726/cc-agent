from __future__ import annotations

import json
import re
from typing import Any

from .skill_registry import load_bundled_skill_snapshot


def load_bundled_skills(groups: tuple[str, ...] | list[str] | None = None) -> list[dict[str, Any]]:
    return list(load_bundled_skill_snapshot(groups).skills)


def load_skill_warnings(groups: tuple[str, ...] | list[str] | None = None) -> list[dict[str, str]]:
    return list(load_bundled_skill_snapshot(groups).warnings)


def list_skills(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for skill in skills:
        if not isinstance(skill, dict) or not skill.get("name"):
            continue
        desc = str(skill.get("description") or "")
        when_to_use = str(skill.get("when_to_use") or "").strip()
        if when_to_use:
            desc = f"{desc} — {when_to_use}"
        compact.append(
            {
                "name": skill.get("name"),
                "id": skill.get("id") or skill.get("name"),
                "display_name": skill.get("display_name") or skill.get("name"),
                "description": desc,
                "allowed_tools": skill.get("allowed_tools") or [],
                "argument_hint": skill.get("argument_hint"),
                "when_to_use": skill.get("when_to_use"),
                "version": skill.get("version"),
                "model": skill.get("model"),
                "shell": skill.get("shell"),
                "context": skill.get("context") if skill.get("context") is not None else [],
                "source": skill.get("source") or "inline",
                "layer": skill.get("layer") or skill.get("source") or "inline",
                "status": skill.get("status") or "active",
                "user_invocable": bool(skill.get("user_invocable", True)),
                "disable_model_invocation": bool(skill.get("disable_model_invocation", False)),
                "resources": skill.get("resources") or [],
                "ui": skill.get("ui") or {},
                "metadata": skill.get("metadata") or {},
            }
        )
    return compact


def skill_prompt_index(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for skill in skills:
        if not isinstance(skill, dict) or not skill.get("name"):
            continue
        name = str(skill.get("name"))
        item: dict[str, Any] = {"name": name, "description": str(skill.get("description") or "")}
        skill_id = str(skill.get("id") or name)
        if skill_id != name:
            item["id"] = skill_id
        when_to_use = str(skill.get("when_to_use") or "").strip()
        if when_to_use:
            item["when_to_use"] = when_to_use
        argument_hint = skill.get("argument_hint")
        if argument_hint not in (None, ""):
            item["argument_hint"] = argument_hint
        compact.append(item)
    return compact


def render_skill(
    skills: list[dict[str, Any]], name: str, args: dict[str, Any] | None = None
) -> str:
    skill = next((item for item in skills if item.get("name") == name), None)
    if not skill:
        raise KeyError(f"skill not found: {name}")
    args = args or {}
    body = str(skill.get("body") or "")
    if not body:
        body = f"Apply skill {name} with arguments: {json.dumps(args, ensure_ascii=False)}"
    rendered = _replace_standard_arguments(body, args)
    for key, value in args.items():
        if str(key).startswith("_"):
            continue
        rendered = rendered.replace("{{" + str(key) + "}}", str(value))
    rendered = re.sub(r"\{\{[^{}]+\}\}", "", rendered).strip()
    if args and not _body_references_arguments(body):
        rendered += "\n\nARGUMENTS:\n" + _raw_arguments(args)
    resources = skill.get("resources") or {}
    if resources:
        resource_text = _render_resource_index(resources)
        if resource_text:
            rendered += f"\n\n{resource_text}"
    return rendered


def _replace_standard_arguments(body: str, args: dict[str, Any]) -> str:
    raw = _raw_arguments(args)
    argv = args.get("_argv")
    if not isinstance(argv, list):
        argv = shlex_split(raw)

    def indexed(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if index <= 0:
            return ""
        return str(argv[index - 1]) if index - 1 < len(argv) else ""

    def arguments_indexed(match: re.Match[str]) -> str:
        index = int(match.group(1))
        return str(argv[index]) if 0 <= index < len(argv) else ""

    rendered = re.sub(r"\$ARGUMENTS\[(\d+)\]", arguments_indexed, body)
    rendered = re.sub(r"\$(\d+)", indexed, rendered)
    return rendered.replace("$ARGUMENTS", raw)


def _body_references_arguments(body: str) -> bool:
    return bool(re.search(r"\$ARGUMENTS(?:\[\d+\])?|\$\d+|\{\{[^{}]+\}\}", body or ""))


def _raw_arguments(args: dict[str, Any]) -> str:
    raw = args.get("_raw")
    if raw is not None:
        return str(raw)
    visible = {key: value for key, value in args.items() if not str(key).startswith("_")}
    return json.dumps(visible, ensure_ascii=False)


def shlex_split(value: str) -> list[str]:
    try:
        import shlex

        return shlex.split(value)
    except Exception:
        return [part for part in str(value or "").split() if part]


def _render_resource_index(resources: Any) -> str:
    if isinstance(resources, list):
        resources = {"files": resources}
    if not isinstance(resources, dict):
        return ""
    lines = ["Resource index:"]
    found = False
    for group in ("references", "assets", "scripts", "files"):
        values = resources.get(group) or []
        if not isinstance(values, list) or not values:
            continue
        found = True
        lines.append(f"- {group}:")
        for value in values:
            lines.append(f"  - {value}")
    if not found:
        return ""
    lines.append("Scripts are not executed automatically.")
    return "\n".join(lines)
