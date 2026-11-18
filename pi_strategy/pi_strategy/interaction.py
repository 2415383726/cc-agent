"""Tool approvals: the one persistent pending interaction."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from uuid import uuid4

from .config import RuntimeConfig
from .errors import PendingError
from .native import clip_arguments


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


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


# -- native (built-in Dify UI) presentation and query-text resume ------------
#
# The built-in UI has no interaction cards: the pending approval is rendered as
# plain text, and the next query text is the decision. The validation machinery
# above (pending match, consumed records, expiry, fingerprints) is unchanged —
# only the entry point differs.


def render_approval_text(pending: dict[str, Any]) -> str:
    arguments = clip_arguments(pending.get("arguments") or {})
    source = str(pending.get("source") or "dify")
    lines = [
        f"**工具确认**：请求执行 `{pending.get('tool_name')}`（来源：{source}）",
        "",
        "```json",
        json.dumps(arguments, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "回复“**同意**”仅本次执行；回复“**当前会话始终允许**”后本会话内该工具不再重复确认；回复“**拒绝**”不执行。",
    ]
    return "\n".join(lines)


def _unwrap_quoted(text: str) -> str:
    """Strip one pair of literal wrapping quotes from a resolved query.

    Dify 1.5 workflow variable references wrap multiline values in a pair of
    literal quotes (string concatenation, not JSON encoding) when substituting
    ``{{#sys.query#}}`` — the same artifact pi_dify handles for its JSON
    interaction parameter. The quotes are transport noise: without this, the
    approval keyword cannot be recognized.
    """
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].strip()
    return text


def parse_approval_reply(pending: dict[str, Any], query: Any) -> dict[str, Any]:
    """Parse a plain-text approval decision via the cc_agent keyword table."""
    verdict = _permission_alias_value(_unwrap_quoted(str(query or "")))
    if verdict == "allow_once":
        decision, scope = "approve", "once"
    elif verdict == "allow_conversation":
        decision, scope = "approve", "session"
    elif verdict == "deny":
        decision, scope = "reject", "once"
    else:
        raise PendingError(
            "pending_invalid", "无法识别的审批回复；请回复“同意”、“当前会话始终允许”或“拒绝”。"
        )
    return {
        "type": "approval",
        "pending_id": pending.get("id"),
        "decision": decision,
        "scope": scope,
    }


def _normalize_choice(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _permission_alias_value(text: str) -> str:
    """Keyword table ported from cc_agent's native approval parser."""
    normalized = _normalize_choice(text)
    aliases = {
        "allow_conversation": {
            "allow_conversation",
            "always_allow",
            "always allow",
            "allow always",
            "allow in conversation",
            "always allow in this conversation",
            "当前会话始终允许",
            "始终允许",
            "本会话始终允许",
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
            "同意",
        },
        "deny": {"deny", "reject", "cancel", "stop", "no", "n", "false", "拒绝", "取消", "停止"},
    }
    for value, candidates in aliases.items():
        if normalized in candidates:
            return value
    return ""
