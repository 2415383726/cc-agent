"""AskUser questionnaires and tool approvals: two distinct persistent interactions."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from uuid import uuid4

from .config import RuntimeConfig
from .errors import PendingError


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


def _clean(value: Any, limit: int = 2_000) -> str:
    text = str(value or "").strip()
    return text[:limit]


def build_questionnaire(arguments: dict[str, Any], config: RuntimeConfig) -> dict[str, Any]:
    raw_questions = arguments.get("questions")
    if raw_questions is None and arguments.get("question"):
        raw_questions = [
            {
                "question": arguments.get("question"),
                "header": arguments.get("header"),
                "type": arguments.get("type")
                or ("multi" if arguments.get("multiSelect") else "single"),
                "options": arguments.get("options") or [],
                "required": arguments.get("required", True),
            }
        ]
    if not isinstance(raw_questions, list) or not raw_questions:
        raise PendingError("pending_invalid", "ask_user requires at least one question.")
    if len(raw_questions) > config.max_questions:
        raise PendingError("pending_invalid", "ask_user received too many questions.")
    questions: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, raw in enumerate(raw_questions):
        if not isinstance(raw, dict):
            raise PendingError("pending_invalid", "Each question must be an object.")
        question_text = _clean(raw.get("question") or raw.get("text"), 4_000)
        if not question_text:
            raise PendingError("pending_invalid", "Each question needs text.")
        question_id = _slug(raw.get("id")) or f"q{index + 1}"
        if question_id in used_ids:
            question_id = f"{question_id}_{index + 1}"
        used_ids.add(question_id)
        kind = str(raw.get("type") or "single").strip().lower()
        if kind in {"single_select", "single-choice"}:
            kind = "single"
        if kind in {"multi_select", "multiple", "multi-choice"}:
            kind = "multi"
        if kind not in {"single", "multi", "text"}:
            raise PendingError("pending_invalid", "Question type must be single, multi or text.")
        options: list[dict[str, Any]] = []
        raw_options = raw.get("options") or []
        if kind in {"single", "multi"}:
            if not isinstance(raw_options, list) or not raw_options:
                raise PendingError("pending_invalid", "Choice questions need options.")
            if len(raw_options) > config.max_options:
                raise PendingError("pending_invalid", "Too many options in one question.")
            used_options: set[str] = set()
            for position, option in enumerate(raw_options):
                if isinstance(option, dict):
                    label = _clean(option.get("label") or option.get("value"), 500)
                    option_id = _slug(option.get("id")) or f"o{position + 1}"
                    description = _clean(option.get("description"), 1_000)
                else:
                    label = _clean(option, 500)
                    option_id = f"o{position + 1}"
                    description = ""
                if not label:
                    raise PendingError("pending_invalid", "Each option needs a label.")
                if option_id in used_options:
                    option_id = f"{option_id}_{position + 1}"
                used_options.add(option_id)
                options.append({"id": option_id, "label": label, "description": description})
        question: dict[str, Any] = {
            "id": question_id,
            "question": question_text,
            "type": kind,
            "required": bool(raw.get("required", True)),
            "options": options,
        }
        header = _clean(raw.get("header"), 200)
        if header:
            question["header"] = header
        if kind == "text":
            placeholder = _clean(raw.get("placeholder"), 300)
            if placeholder:
                question["placeholder"] = placeholder
            question["max_length"] = max(1, min(int(raw.get("max_length") or 4_000), 20_000))
        if kind == "multi":
            minimum = raw.get("min_selections")
            maximum = raw.get("max_selections")
            if minimum is not None:
                question["min_selections"] = max(0, min(int(minimum), len(options)))
            if maximum is not None:
                question["max_selections"] = max(1, min(int(maximum), len(options)))
        questions.append(question)
    return {
        "id": _new_id("qst"),
        "title": _clean(arguments.get("title"), 300),
        "description": _clean(arguments.get("description"), 2_000),
        "questions": questions,
    }


def create_question_pending(
    questionnaire: dict[str, Any], *, tool_call_id: str, run_id: str, timeout_seconds: float
) -> dict[str, Any]:
    created = time.time()
    pending: dict[str, Any] = {
        "kind": "ask_user",
        "id": str(questionnaire["id"]),
        "questionnaire": questionnaire,
        "tool_call_id": tool_call_id,
        "run_id": run_id,
        "created_at": created,
        "expires_at": created + timeout_seconds if timeout_seconds else None,
    }
    return pending


def validate_question_answer(
    pending: dict[str, Any], interaction: dict[str, Any]
) -> dict[str, Any]:
    if str(interaction.get("pending_id") or "") != str(pending.get("id") or ""):
        raise PendingError(
            "pending_invalid", "The answer does not match the waiting questionnaire."
        )
    if _expired(pending):
        raise PendingError("pending_expired", "The waiting questionnaire has expired.")
    questionnaire = pending.get("questionnaire") or {}
    questions = questionnaire.get("questions") or []
    answers = interaction.get("answers")
    if not isinstance(answers, dict):
        raise PendingError("pending_invalid", "Answers must be an object keyed by question id.")
    known = {str(question.get("id")): question for question in questions}
    unknown = set(answers) - set(known)
    if unknown:
        raise PendingError("pending_invalid", "The answer references an unknown question.")
    normalized: dict[str, Any] = {}
    for question_id, question in known.items():
        value = answers.get(question_id)
        kind = question.get("type")
        required = bool(question.get("required", True))
        if kind == "text":
            text = _clean(value, int(question.get("max_length") or 4_000))
            if not text and required:
                raise PendingError("pending_invalid", "A required text answer is missing.")
            if text:
                normalized[question_id] = text
            continue
        options = question.get("options") or []
        option_ids = {str(option.get("id")) for option in options}
        labels = {str(option.get("label")): str(option.get("id")) for option in options}
        if kind == "single":
            if value in (None, ""):
                if required:
                    raise PendingError("pending_invalid", "A required choice is missing.")
                continue
            selected = str(value)
            if selected not in option_ids:
                selected = labels.get(selected, "")
            if not selected:
                raise PendingError("pending_invalid", "The selected option is not valid.")
            normalized[question_id] = selected
            continue
        if value in (None, "", []):
            if required:
                raise PendingError("pending_invalid", "A required multi-select answer is missing.")
            continue
        if not isinstance(value, list):
            raise PendingError("pending_invalid", "A multi-select answer must be a list.")
        selected_ids: list[str] = []
        for item in value:
            candidate = str(item)
            if candidate not in option_ids:
                candidate = labels.get(candidate, "")
            if not candidate:
                raise PendingError("pending_invalid", "A selected option is not valid.")
            if candidate not in selected_ids:
                selected_ids.append(candidate)
        minimum = question.get("min_selections")
        maximum = question.get("max_selections")
        if minimum is not None and len(selected_ids) < int(minimum):
            raise PendingError("pending_invalid", "Too few options were selected.")
        if maximum is not None and len(selected_ids) > int(maximum):
            raise PendingError("pending_invalid", "Too many options were selected.")
        if selected_ids:
            normalized[question_id] = selected_ids
    missing = [
        question_id
        for question_id, question in known.items()
        if question.get("required", True) and question_id not in normalized
    ]
    if missing:
        raise PendingError("pending_invalid", "A required answer is missing.")
    return {"pending_id": pending["id"], "answers": normalized, "questionnaire": questionnaire}


def format_answer_message(result: dict[str, Any]) -> str:
    questionnaire = result.get("questionnaire") or {}
    answers = result.get("answers") or {}
    lines = ["Answers to the questionnaire:"]
    for question in questionnaire.get("questions") or []:
        question_id = str(question.get("id"))
        value = answers.get(question_id)
        if value is None:
            continue
        if isinstance(value, list):
            labels = []
            options = {
                str(option.get("id")): option.get("label")
                for option in question.get("options") or []
            }
            for item in value:
                labels.append(str(options.get(item) or item))
            display = ", ".join(labels)
        else:
            options = {
                str(option.get("id")): option.get("label")
                for option in question.get("options") or []
            }
            display = str(options.get(value) or value)
        lines.append(f"- {question.get('question')}: {display}")
    return "\n".join(lines)


def public_questionnaire(pending: dict[str, Any]) -> dict[str, Any]:
    questionnaire = dict(pending.get("questionnaire") or {})
    questionnaire["pending_id"] = pending.get("id")
    questionnaire["created_at"] = pending.get("created_at")
    questionnaire["expires_at"] = pending.get("expires_at")
    return questionnaire


def approval_required(
    tool_name: str,
    source: str,
    annotations: dict[str, Any] | None,
    config: RuntimeConfig,
    grants: list[dict[str, Any]],
    *,
    tool_identity: str = "",
) -> bool:
    if config.approval_mode == "off":
        return False
    for grant in grants:
        if (
            grant.get("tool") == tool_name
            and grant.get("scope") == "session"
            and (not grant.get("source") or grant.get("source") == source)
            and (not tool_identity or grant.get("tool_identity") == tool_identity)
        ):
            return False
    if tool_name in config.approval_tools:
        return True
    if config.approval_mode == "mcp" and source == "mcp":
        hints = annotations or {}
        return hints.get("readOnlyHint") is not True or hints.get("destructiveHint") is True
    return False


def create_approval_pending(
    *,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    source: str,
    annotations: dict[str, Any] | None,
    run_id: str,
    timeout_seconds: float = 0.0,
    tool_identity: str = "",
) -> dict[str, Any]:
    created = time.time()
    pending = {
        "kind": "approval",
        "tool_identity": tool_identity,
        "id": _new_id("apv"),
        "action_id": _new_id("act"),
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "source": source,
        "annotations": annotations or {},
        "run_id": run_id,
        "created_at": created,
        "expires_at": created + timeout_seconds if timeout_seconds else None,
        "scope_options": ["once", "session"],
    }
    pending["call_fingerprint"] = _approval_fingerprint(pending)
    return pending


def validate_approval_decision(
    pending: dict[str, Any], interaction: dict[str, Any]
) -> dict[str, Any]:
    if str(interaction.get("type") or "") != "approval":
        raise PendingError("pending_invalid", "The interaction is not an approval decision.")
    if pending.get("call_fingerprint") != _approval_fingerprint(pending):
        raise PendingError(
            "pending_invalid", "The pending approval no longer matches its original operation."
        )
    if str(interaction.get("pending_id") or "") != str(pending.get("id") or ""):
        raise PendingError("pending_invalid", "The decision does not match the waiting action.")
    if _expired(pending):
        raise PendingError("pending_expired", "The waiting approval has expired.")
    decision = str(interaction.get("decision") or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise PendingError("pending_invalid", "The approval decision must be approve or reject.")
    scope = str(interaction.get("scope") or "once").strip().lower()
    if scope not in {"once", "session"}:
        raise PendingError("pending_invalid", "The approval scope must be once or session.")
    return {
        "pending_id": pending["id"],
        "decision": decision,
        "scope": scope,
        "tool_name": pending.get("tool_name"),
        "tool_call_id": pending.get("tool_call_id"),
        "arguments": pending.get("arguments") or {},
        "source": pending.get("source") or "dify",
    }


def public_approval(pending: dict[str, Any]) -> dict[str, Any]:
    return {
        "pending_id": pending.get("id"),
        "action_id": pending.get("action_id"),
        "tool_call_id": pending.get("tool_call_id"),
        "tool": pending.get("tool_name"),
        "arguments": pending.get("arguments") or {},
        "source": pending.get("source"),
        "annotations": pending.get("annotations") or {},
        "created_at": pending.get("created_at"),
        "expires_at": pending.get("expires_at"),
        "scope_options": pending.get("scope_options") or ["once", "session"],
    }


def consumed_record(pending: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "id": pending.get("id"),
        "kind": pending.get("kind"),
        "tool_call_id": pending.get("tool_call_id"),
        "action": action,
        "consumed_at": time.time(),
    }


def is_consumed(consumed: list[dict[str, Any]], pending_id: str) -> bool:
    return any(str(item.get("id")) == pending_id for item in consumed)


def _approval_fingerprint(pending: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "tool_call_id": pending.get("tool_call_id"),
            "tool_name": pending.get("tool_name"),
            "source": pending.get("source"),
            "tool_identity": pending.get("tool_identity"),
            "arguments": pending.get("arguments"),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expired(pending: dict[str, Any]) -> bool:
    expires_at = pending.get("expires_at")
    return bool(expires_at and time.time() > float(expires_at))


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-")
    return text[:64]
