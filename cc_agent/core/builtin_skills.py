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
        {"name": "reset", "kind": "local", "description": "Reset history, memory, and tasks", "handler": _reset_handler},
        {"name": "a2ui-demo", "kind": "local", "description": "Render an A2UI report card demo", "handler": _a2ui_demo_handler},
        {"name": "weekly-report-card", "kind": "local", "description": "Render an A2UI weekly report card", "handler": _weekly_report_card_handler},
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
            f"- memory records: {len(state.memory)}",
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
    state.memory.clear()
    state.tasks.clear()
    lines = [
        "State reset",
        "- history: cleared",
        "- memory: cleared",
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


def _a2ui_demo_handler(state: AgentState, args: str, **_: Any) -> dict[str, Any]:
    return {
        "text": "A2UI report card demo rendered.",
        "events": [
            {"activity_type": "a2ui-surface", "activity": {"a2ui_operations": _report_demo_operations()}},
        ],
    }


def _weekly_report_card_handler(state: AgentState, args: str, **_: Any) -> dict[str, Any]:
    notes = args.strip() or (
        "Completed CopilotKit A2UI validation, fixed interrupt rendering, and split the Dify bridge. "
        "Next week, test the card with a real weekly report workflow."
    )
    return {
        "text": "A2UI weekly report card rendered.",
        "events": [
            {"activity_type": "a2ui-surface", "activity": {"a2ui_operations": _weekly_report_card_operations(notes)}},
        ],
    }


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


def _report_demo_operations() -> list[dict[str, Any]]:
    surface_id = "report-demo"
    catalog_id = "https://a2ui.org/specification/v0_9/basic_catalog.json"
    summary = "This week the CopilotKit integration PoC stabilized conversation, tool calling, and interrupt handling."
    highlights = (
        "1. Fixed interrupt rendering in the chat surface.\n"
        "2. Split the Dify bridge into transport, bridge, and run adapter.\n"
        "3. Added an A2UI demo path using the built-in catalog."
    )
    next_plan = "Pick one real reporting workflow and replace a markdown-heavy answer with a structured card surface."
    components = [
        {"id": "root", "component": "Card", "child": "content"},
        {
            "id": "content",
            "component": "Column",
            "children": ["title", "summary", "divider", "highlights_label", "highlights", "next_label", "next_plan", "cta"],
        },
        {"id": "title", "component": "Text", "variant": "h3", "text": "Weekly Report"},
        {"id": "summary", "component": "Text", "text": summary},
        {"id": "divider", "component": "Divider"},
        {"id": "highlights_label", "component": "Text", "variant": "h5", "text": "Highlights"},
        {"id": "highlights", "component": "Text", "text": highlights},
        {"id": "next_label", "component": "Text", "variant": "h5", "text": "Next Steps"},
        {"id": "next_plan", "component": "Text", "text": next_plan},
        {"id": "cta", "component": "Button", "child": "cta_text"},
        {"id": "cta_text", "component": "Text", "text": "Continue refining this report"},
    ]
    data = {
        "summary": summary,
        "highlights": highlights,
        "next_plan": next_plan,
    }
    return [
        {"version": "v0.9", "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id}},
        {"version": "v0.9", "updateComponents": {"surfaceId": surface_id, "components": components}},
        {"version": "v0.9", "updateDataModel": {"surfaceId": surface_id, "data": data}},
    ]


def _weekly_report_card_operations(notes: str) -> list[dict[str, Any]]:
    surface_id = "weekly-report-card"
    catalog_id = "https://a2ui.org/specification/v0_9/basic_catalog.json"
    components = [
        {"id": "root", "component": "Card", "child": "content"},
        {
            "id": "content",
            "component": "Column",
            "children": [
                "title",
                "intro",
                "divider_1",
                "done_label",
                "done_text",
                "issue_label",
                "issue_text",
                "next_label",
                "next_text",
                "cta",
            ],
        },
        {"id": "title", "component": "Text", "variant": "h3", "text": "Weekly Work Report"},
        {"id": "intro", "component": "Text", "text": "Structured report card generated from your notes."},
        {"id": "divider_1", "component": "Divider"},
        {"id": "done_label", "component": "Text", "variant": "h5", "text": "Completed This Week"},
        {"id": "done_text", "component": "Text", "text": notes},
        {"id": "issue_label", "component": "Text", "variant": "h5", "text": "Issues and Risks"},
        {
            "id": "issue_text",
            "component": "Text",
            "text": "No explicit blockers were detected. Add risks or open items after the command for a more precise report.",
        },
        {"id": "next_label", "component": "Text", "variant": "h5", "text": "Next Week Plan"},
        {
            "id": "next_text",
            "component": "Text",
            "text": "Use this A2UI card in a real weekly report flow and compare it with markdown output.",
        },
        {"id": "cta", "component": "Button", "child": "cta_text"},
        {"id": "cta_text", "component": "Text", "text": "Continue refining the report"},
    ]
    return [
        {"version": "v0.9", "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id}},
        {"version": "v0.9", "updateComponents": {"surfaceId": surface_id, "components": components}},
    ]
