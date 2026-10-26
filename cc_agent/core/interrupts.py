from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .messages import AgentState, ToolCall, ToolResult

logger = logging.getLogger(__name__)
PERMISSIONS_SCHEMA_VERSION = 1


@dataclass(slots=True)
class UserInterrupts:
    state: AgentState
    confirmation_tools: set[str] = field(default_factory=set)
    _approved_calls: set[tuple[str, str]] = field(default_factory=set, repr=False)

    def before_call(self, tool_call: ToolCall) -> ToolResult | None:
        approval = (tool_call.id, tool_call.name)
        if approval in self._approved_calls:
            self._approved_calls.remove(approval)
            return None
        permissions = normalize_permissions(self.state.permissions)
        self.state.permissions = permissions
        tool_name = str(tool_call.name or "")

        if _is_tool_allowed(permissions, tool_name):
            return None

        if tool_name in self.confirmation_tools:
            return self._permission_prompt(tool_call)

        return None

    def resume(
        self,
        config: Any,
        last_execution_metadata: dict[str, Any],
        execute: Callable[[ToolCall], ToolResult],
    ) -> ResumeResult:
        state = self.state
        if (
            not isinstance(last_execution_metadata, dict)
            or last_execution_metadata.get("finish_reason") != "awaiting_user"
        ):
            return ResumeResult(error="No awaiting user interrupt is available to resume")
        question = last_execution_metadata.get("question")
        if not isinstance(question, dict):
            return ResumeResult(error="Awaiting user interrupt is missing question metadata")
        expected_tool_call_id = str(
            question.get("tool_call_id") or question.get("id") or ""
        ).strip()
        if not expected_tool_call_id:
            return ResumeResult(error="Awaiting user interrupt is missing tool_call_id")

        response = (
            config.user_prompt_response if isinstance(config.user_prompt_response, dict) else {}
        )
        answer = str(response.get("answer") or "").strip()
        if not answer:
            return ResumeResult(error="User prompt response answer is empty")
        prompt_id = str(response.get("promptId") or response.get("prompt_id") or "").strip()
        if prompt_id and prompt_id != expected_tool_call_id:
            return ResumeResult(error="User prompt response does not match the pending interrupt")

        matches = [
            message
            for message in state.history
            if message.get("role") == "tool"
            and str(message.get("tool_call_id") or "").strip() == expected_tool_call_id
        ]
        if len(matches) != 1:
            return ResumeResult(
                error="Could not find exactly one pending tool result for the interrupt"
            )

        tool_message = matches[0]
        metadata = dict(tool_message.get("metadata") or {})
        pending_tool_execution = metadata.get("pending_tool_execution")
        safe_response = _safe_user_prompt_response(response)
        if isinstance(pending_tool_execution, dict):
            metadata["original_content_before_resume"] = str(tool_message.get("content") or "")
            metadata["resumed_user_prompt_response"] = safe_response
            metadata["requires_user_input"] = False
            permission_required = bool(metadata.get("permission_required"))
            if permission_required:
                decision = apply_permission_decision(state, response, metadata)
                metadata["permission_decision"] = decision
                approved = decision in {"allow_once", "allow_conversation"}
            else:
                approved = permission_decision(response) in {"allow_once", "allow_conversation"}
            metadata["confirmation_approved"] = approved
            executed = None
            if approved:
                approval = (
                    expected_tool_call_id,
                    str(pending_tool_execution.get("name") or tool_message.get("name") or ""),
                )
                self._approved_calls.add(approval)
                try:
                    executed = execute(
                        ToolCall(
                            id=expected_tool_call_id,
                            name=str(
                                pending_tool_execution.get("name") or tool_message.get("name") or ""
                            ),
                            arguments=dict(pending_tool_execution.get("arguments") or {}),
                            raw_arguments=str(pending_tool_execution.get("raw_arguments") or ""),
                        )
                    )
                finally:
                    self._approved_calls.discard(approval)
                tool_message.update(executed.to_history())
                tool_metadata = dict(tool_message.get("metadata") or {})
                tool_metadata.update(metadata)
                tool_metadata.update(executed.metadata or {})
                tool_metadata["confirmation_approved"] = True
                tool_metadata["requires_user_input"] = False
                tool_message["metadata"] = tool_metadata
            else:
                metadata["confirmation_denied"] = True
                tool_message["content"] = (
                    f"Tool execution cancelled by user: {tool_message.get('name') or pending_tool_execution.get('name') or 'unknown_tool'}"
                )
                tool_message["metadata"] = metadata
                tool_message["is_error"] = True
            config.user_prompt_response = None
            return ResumeResult(result=executed)

        metadata["original_content_before_resume"] = str(tool_message.get("content") or "")
        metadata["resumed_user_prompt_response"] = safe_response
        metadata["requires_user_input"] = False
        tool_message["metadata"] = metadata
        tool_message["content"] = f"User answered: {answer}"
        config.user_prompt_response = None
        return ResumeResult()

    @staticmethod
    def response_from_query(query: Any, metadata: dict[str, Any]) -> dict[str, Any] | None:
        return _implicit_user_prompt_response(query, metadata)

    @staticmethod
    def question_from_result(result: ToolResult) -> dict[str, Any]:
        raw = result.metadata.get("question") or result.llm_observation
        if isinstance(raw, dict):
            return {
                **raw,
                "id": raw.get("id") or result.tool_call_id,
                "question": raw.get("question") or raw.get("text") or result.llm_observation,
                "tool_call_id": raw.get("tool_call_id") or result.tool_call_id,
                "tool_name": raw.get("tool_name") or result.tool_name,
            }
        return {
            "id": result.tool_call_id,
            "question": str(raw),
            "text": str(raw),
            "purpose": "clarification",
            "options": [],
            "multiSelect": False,
            "allowCustomInput": True,
            "tool_call_id": result.tool_call_id,
            "tool_name": result.tool_name,
        }

    def decision_activities(self, writer: Any) -> list[dict[str, Any]]:
        return _permission_decision_activities(writer, self.state.history)

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
                "permission_request": {"tool_name": tool_call.name},
                "pending_tool_execution": {
                    "name": tool_call.name,
                    "arguments": dict(tool_call.arguments or {}),
                    "raw_arguments": tool_call.raw_arguments or "",
                },
            },
        )


def normalize_permissions(value: Any) -> dict[str, Any]:
    normalized = {"schema_version": PERMISSIONS_SCHEMA_VERSION, "allowed_tools": {}}
    if not isinstance(value, dict):
        return normalized
    raw = value.get("allowed_tools")
    if isinstance(raw, dict):
        normalized["allowed_tools"] = {
            str(name): str(scope) for name, scope in raw.items() if name and scope
        }
    return normalized


def apply_permission_decision(
    state: AgentState, response: dict[str, Any], metadata: dict[str, Any]
) -> str:
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
        "cc_agent permission decision applied: decision=%s tool=%s allowed_tools=%s",
        decision,
        str(request.get("tool_name") or "").strip(),
        sorted(permissions.get("allowed_tools", {}).keys()),
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
    if any(
        value
        in {
            "allow_once",
            "approve",
            "allow",
            "continue",
            "confirm",
            "yes",
            "y",
            "true",
            "继续执行",
            "允许",
        }
        for value in values
    ):
        return "allow_once"
    return "deny"


def _is_tool_allowed(permissions: dict[str, Any], tool_name: str) -> bool:
    return permissions.get("allowed_tools", {}).get(tool_name) == "conversation"


def _permission_question(tool_call: ToolCall) -> dict[str, Any]:
    detail = f"Tool: {tool_call.name}"
    if tool_call.arguments:
        detail += "\nArguments: " + json.dumps(
            tool_call.arguments, ensure_ascii=False, sort_keys=True
        )
    question = f"Allow this operation to run?\n{detail}"
    return {
        "id": tool_call.id,
        "question": question,
        "text": question,
        "purpose": "permission",
        "options": [
            {"label": "Allow once", "description": "Allow only this run", "value": "allow_once"},
            {
                "label": "Always allow",
                "description": "Allow this tool for the current conversation",
                "value": "allow_conversation",
            },
            {"label": "Deny", "description": "Do not run this operation", "value": "deny"},
        ],
        "multiSelect": False,
        "allowCustomInput": False,
        "tool_call_id": tool_call.id,
        "tool_name": tool_call.name,
    }


@dataclass(slots=True)
class ResumeResult:
    error: str | None = None
    result: ToolResult | None = None


def _implicit_user_prompt_response(
    query: Any, last_execution_metadata: dict[str, Any]
) -> dict[str, Any] | None:
    if (
        not isinstance(last_execution_metadata, dict)
        or last_execution_metadata.get("finish_reason") != "awaiting_user"
    ):
        return None
    question = last_execution_metadata.get("question")
    if not isinstance(question, dict):
        return None
    tool_call_id = str(question.get("tool_call_id") or question.get("id") or "").strip()
    answer = str(query or "").strip()
    if not tool_call_id or not answer:
        return None

    purpose = str(question.get("purpose") or "").strip()
    raw_options = question.get("options")
    options = raw_options if isinstance(raw_options, list) else []
    selected_value = _matching_option_value(answer, options)
    selected_label = _matching_option_label(selected_value, options)
    if not selected_value and purpose == "permission":
        selected_value = _permission_alias_value(answer)
        selected_label = selected_value

    response: dict[str, Any] = {"promptId": tool_call_id, "answer": answer}
    if purpose:
        response["purpose"] = purpose
    if question.get("question") or question.get("text"):
        response["question"] = question.get("question") or question.get("text")
    if selected_value:
        response["selectedValues"] = [selected_value]
        response["selectedLabels"] = [selected_label or selected_value]
    else:
        response["customInput"] = answer
    return response


def _matching_option_value(answer: str, options: list[Any]) -> str:
    normalized_answer = _normalize_choice(answer)
    for option in options:
        if not isinstance(option, dict):
            continue
        value = str(option.get("value") or "").strip()
        label = str(option.get("label") or option.get("text") or "").strip()
        description = str(option.get("description") or "").strip()
        candidates = [value, label, description]
        if any(
            _normalize_choice(candidate) == normalized_answer
            for candidate in candidates
            if candidate
        ):
            return value or label
    return ""


def _matching_option_label(value: str, options: list[Any]) -> str:
    if not value:
        return ""
    for option in options:
        if not isinstance(option, dict):
            continue
        if str(option.get("value") or "").strip() == value:
            return str(option.get("label") or value)
    return value


def _permission_alias_value(answer: str) -> str:
    normalized = _normalize_choice(answer)
    aliases = {
        "allow_conversation": {
            "allow_conversation",
            "always_allow",
            "always allow",
            "allow always",
            "allow in conversation",
            "always allow in this conversation",
            "当前会话始终允许",
        },
        "allow_once": {
            "allow_once",
            "approve",
            "allow",
            "continue",
            "confirm",
            "yes",
            "y",
            "true",
            "允许一次",
            "继续执行",
            "允许",
        },
        "deny": {"deny", "reject", "cancel", "stop", "no", "n", "false", "拒绝", "取消", "停止"},
    }
    for value, candidates in aliases.items():
        if normalized in {_normalize_choice(candidate) for candidate in candidates}:
            return value
    return ""


def _normalize_choice(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_user_prompt_response(response: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "promptId",
        "prompt_id",
        "purpose",
        "question",
        "selectedLabels",
        "selectedValues",
        "customInput",
        "answer",
        "values",
    }
    return {key: value for key, value in response.items() if key in allowed and value is not None}


def _permission_decision_activities(
    writer: Any, history: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for message in history:
        if message.get("role") != "tool":
            continue
        metadata = message.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("permission_decision_activity_emitted"):
            continue
        decision = metadata.get("permission_decision")
        if decision not in {"allow_once", "allow_conversation", "deny"}:
            continue
        raw_request = metadata.get("permission_request")
        request = raw_request if isinstance(raw_request, dict) else {}
        events.extend(
            writer.write_activity(
                "cc_agent.permission_decision",
                _drop_none(
                    {
                        "toolName": request.get("tool_name") or message.get("name"),
                        "decision": decision,
                        "scope": "conversation" if decision == "allow_conversation" else "once",
                    }
                ),
            )
        )
        metadata["permission_decision_activity_emitted"] = True
        message["metadata"] = metadata
    return events


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def pending_tool_call_id(metadata: Any) -> str:
    if not isinstance(metadata, dict) or metadata.get("finish_reason") != "awaiting_user":
        return ""
    question = metadata.get("question")
    if not isinstance(question, dict):
        return ""
    return str(question.get("tool_call_id") or question.get("id") or "").strip()
