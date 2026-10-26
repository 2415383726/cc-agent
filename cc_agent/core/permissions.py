from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .internal_tools import SAFE_INTERNAL_TOOL_NAMES, SESSION_MUTATION_TOOL_NAMES
from .messages import AgentState, ToolCall, ToolResult


logger = logging.getLogger(__name__)
PERMISSIONS_SCHEMA_VERSION = 1

@dataclass(slots=True)
class PermissionManager:
    state: AgentState
    external_tool_names: set[str] = field(default_factory=set)
    always_ask_tools: set[str] = field(default_factory=set)

    def before_call(self, tool_call: ToolCall) -> ToolResult | None:
        permissions = normalize_permissions(self.state.permissions)
        self.state.permissions = permissions
        tool_name = str(tool_call.name or "")

        if _is_tool_allowed(permissions, tool_name):
            return None

        if tool_name in self.always_ask_tools:
            return self._permission_prompt(tool_call)

        if tool_name in SAFE_INTERNAL_TOOL_NAMES or tool_name in SESSION_MUTATION_TOOL_NAMES:
            return None
        return None

    def _permission_prompt(self, tool_call: ToolCall) -> ToolResult:
        question = _permission_question(tool_call)
        logger.info(
            "cc_agent permission prompt created: tool=%s tool_call_id=%s",
            tool_call.name,
            tool_call.id,
        )
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            llm_observation=f"Executing {tool_call.name} requires user permission.",
            synthetic=True,
            metadata={
                "requires_user_input": True,
                "permission_required": True,
                "question": question,
                "permission_request": {
                    "tool_name": tool_call.name,
                },
                "pending_tool_execution": {
                    "name": tool_call.name,
                    "arguments": dict(tool_call.arguments or {}),
                    "raw_arguments": tool_call.raw_arguments or "",
                },
            },
        )


def normalize_permissions(value: Any) -> dict[str, Any]:
    normalized = {
        "schema_version": PERMISSIONS_SCHEMA_VERSION,
        "allowed_tools": {},
        "allowed_skills": {},
        "allowed_skill_scripts": {},
    }
    if not isinstance(value, dict):
        return normalized
    for key in ("allowed_tools", "allowed_skills", "allowed_skill_scripts"):
        raw = value.get(key)
        if isinstance(raw, dict):
            normalized[key] = {str(name): str(scope) for name, scope in raw.items() if name and scope}
    return normalized


def apply_permission_decision(state: AgentState, response: dict[str, Any], metadata: dict[str, Any]) -> str:
    decision = permission_decision(response)
    permissions = normalize_permissions(state.permissions)
    request = metadata.get("permission_request") if isinstance(metadata, dict) else {}
    request = request if isinstance(request, dict) else {}
    if decision == "allow_conversation":
        tool_name = str(request.get("tool_name") or "").strip()
        if tool_name:
            permissions["allowed_tools"][tool_name] = "conversation"
    state.permissions = permissions
    logger.info(
        "cc_agent permission decision applied: decision=%s tool=%s allowed_tools=%s allowed_skill_scripts=%s",
        decision,
        str(request.get("tool_name") or "").strip(),
        sorted(permissions.get("allowed_tools", {}).keys()),
        sorted(permissions.get("allowed_skill_scripts", {}).keys()),
    )
    return decision


def permission_decision(response: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("selectedValues", "selected_values", "selectedLabels", "selected_labels"):
        raw = response.get(key)
        if isinstance(raw, list):
            values.extend(str(item).strip().lower() for item in raw if str(item).strip())
    for key in ("answer", "customInput"):
        raw = response.get(key)
        if raw:
            values.append(str(raw).strip().lower())
    if any(value in {"allow_conversation", "always_allow", "当前会话始终允许"} for value in values):
        return "allow_conversation"
    if any(value in {"allow_once", "approve", "allow", "continue", "confirm", "yes", "y", "true", "继续执行", "允许"} for value in values):
        return "allow_once"
    return "deny"


def _is_tool_allowed(permissions: dict[str, Any], tool_name: str) -> bool:
    return permissions.get("allowed_tools", {}).get(tool_name) == "conversation"


def _permission_question(tool_call: ToolCall) -> dict[str, Any]:
    detail = f"Tool: {tool_call.name}"
    if tool_call.arguments:
        detail += "\nArguments: " + json.dumps(tool_call.arguments, ensure_ascii=False, sort_keys=True)
    question = f"Allow this operation to run?\n{detail}"
    return {
        "id": tool_call.id,
        "question": question,
        "text": question,
        "purpose": "permission",
        "options": [
            {"label": "Allow once", "description": "Allow only this run", "value": "allow_once"},
            {"label": "Always allow", "description": "Allow this tool for the current conversation", "value": "allow_conversation"},
            {"label": "Deny", "description": "Do not run this operation", "value": "deny"},
        ],
        "multiSelect": False,
        "allowCustomInput": False,
        "tool_call_id": tool_call.id,
        "tool_name": tool_call.name,
    }
