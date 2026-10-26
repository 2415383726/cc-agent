from __future__ import annotations

from typing import Any

from .config import AgentRunConfig
from .context_budget import ContextBudget, estimate_context_tokens
from .messages import AgentState


def register_all() -> list[dict[str, Any]]:
    return [
        {"name": "help", "kind": "local", "description": "Show commands and skills", "handler": _help_handler},
        {"name": "status", "kind": "local", "description": "Show current session status", "handler": _status_handler},
        {"name": "context", "kind": "local", "description": "Show context usage", "handler": _context_handler},
        {"name": "cost", "kind": "local", "description": "Show token usage", "handler": _cost_handler},
        {"name": "compact", "kind": "local", "description": "Force compact conversation history", "handler": _compact_handler},
        {"name": "reset", "kind": "local", "description": "Reset history and tasks", "handler": _reset_handler},
    ]


def _help_handler(state: AgentState, args: str, *, all_skills: list[dict[str, Any]] | None = None, **_: Any) -> str:
    lines = ["Available commands:"]
    for skill in all_skills or []:
        if skill.get("kind") == "local":
            lines.append(f"  /{skill['name']:<18}{skill.get('description', '')}")
    lines.append("")
    lines.append("Available skills:")
    for skill in all_skills or []:
        if skill.get("kind") == "prompt":
            lines.append(f"  {skill['name']:<28}  {skill.get('description', '')}")
    return "\n".join(lines)


def _status_handler(state: AgentState, args: str, **_: Any) -> str:
    return "\n".join(
        [
            "Status",
            f"- history messages: {len(state.history)}",
            f"- summary: {'yes' if state.summary else 'no'}",
            f"- tasks: {len(state.tasks)}",
            f"- skills: {len(state.skills)}",
        ]
    )


def _context_handler(state: AgentState, args: str, *, config: AgentRunConfig | None = None, **_: Any) -> str:
    estimated_tokens = estimate_context_tokens(state.history)
    return "\n".join(
        [
            "Context",
            f"- history messages: {len(state.history)}",
            f"- estimated tokens: {estimated_tokens}",
            f"- max history messages: {config.max_history_messages if config else 'N/A'}",
            f"- context limit (tokens): {(config.resolved_context_limit or config.max_total_context_tokens) if config else 'N/A'}",
            f"- summary: {state.summary or '(empty)'}",
        ]
    )


def _reset_handler(state: AgentState, args: str, **_: Any) -> str:
    state.history.clear()
    state.summary = ""
    state.tasks.clear()
    lines = [
        "State reset",
        "- history: cleared",
        "- tasks: cleared",
    ]
    return "\n".join(lines)


def _cost_handler(state: AgentState, args: str, **_: Any) -> str:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for message in state.history:
        usage = message.get("usage") or {}
        if not isinstance(usage, dict):
            continue
        for key in totals:
            try:
                totals[key] += int(usage.get(key) or 0)
            except (TypeError, ValueError):
                continue
    return "\n".join(
        [
            "Token usage",
            f"- total_tokens: {totals['total_tokens']}",
            f"- prompt_tokens: {totals['prompt_tokens']}",
            f"- completion_tokens: {totals['completion_tokens']}",
        ]
    )






def _compact_handler(
    state: AgentState,
    args: str,
    *,
    config: AgentRunConfig | None = None,
    summarizer: Any = None,
    compression_id: str = "",
    **_: Any,
) -> dict[str, Any]:
    if config is None:
        config = AgentRunConfig()
    budget = ContextBudget(
        max_history_messages=config.max_history_messages,
        max_observation_chars=config.max_observation_chars,
        max_total_context_tokens=config.resolved_context_limit or config.max_total_context_tokens,
    )
    compacted = budget.compact_history(
        list(state.history),
        existing_summary=state.summary,
        summarizer=summarizer,
        force=True,
    )
    state.history = compacted.messages
    state.summary = compacted.summary
    metadata = dict(compacted.metadata)
    compression_id = compression_id or "manual-compression"
    completed = {
        **metadata,
        "status": "completed",
        "trigger": "manual",
        "compressionId": compression_id,
        "messageId": compression_id,
        "history_messages": len(state.history),
    }
    return {
        "text": "Context compacted.",
        "events": [
            {
                "activity_type": "cc_agent.compression",
                "activity": completed,
            }
        ],
    }
