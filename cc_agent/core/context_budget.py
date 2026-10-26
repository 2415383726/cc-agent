from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable

from .history import sanitize_history


@dataclass(slots=True)
class CompactionResult:
    messages: list[dict[str, Any]]
    summary: str
    metadata: dict[str, Any]


class ContextBudget:
    def __init__(
        self,
        max_history_messages: int = 40,
        max_observation_chars: int = 8000,
        max_total_context_chars: int = 131072,
        threshold_ratio: float = 0.7,
        keep_ratio: float = 0.3,
        max_total_context_tokens: int | None = None,
    ):
        self.max_history_messages = max_history_messages
        self.max_observation_chars = max_observation_chars
        self.max_total_context_tokens = max(1, int(max_total_context_tokens or max_total_context_chars))
        self.max_total_context_chars = self.max_total_context_tokens
        self.threshold_ratio = max(0.1, min(1.0, threshold_ratio))
        self.keep_ratio = max(0.05, min(0.95, keep_ratio))

    def prepare(
        self,
        messages: list[dict[str, Any]],
        summarizer: Callable[[list[dict[str, Any]]], str] | None = None,
        tools: list[Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        prepared = sanitize_history(copy.deepcopy(messages))
        metadata = {
            "compressed": False,
            "compressed_reason": [],
            "truncated_observations": 0,
            "summarized_messages": 0,
            "estimated_tokens_before": estimate_context_tokens(prepared),
            "estimated_tokens_after": 0,
            "tool_schema_estimated_tokens": estimate_context_tokens(tools or []),
            "input_budget_tokens": self.input_budget_tokens,
        }

        for message in prepared:
            if message.get("role") != "tool":
                continue
            content = str(message.get("content") or "")
            if len(content) > self.max_observation_chars:
                message["content"] = self._truncate(content)
                metadata["compressed"] = True
                metadata["compressed_reason"].append("observation_truncated")
                metadata["truncated_observations"] += 1

        metadata["estimated_tokens_after"] = estimate_context_tokens(prepared)
        metadata["request_estimated_tokens"] = (
            metadata["estimated_tokens_after"] + metadata["tool_schema_estimated_tokens"]
        )
        metadata["request_over_budget"] = (
            metadata["request_estimated_tokens"] > self.input_budget_tokens
        )
        metadata["compressed_reason"] = list(dict.fromkeys(metadata["compressed_reason"]))
        return prepared, metadata

    @property
    def input_budget_tokens(self) -> int:
        return max(1, int(self.max_total_context_tokens * self.threshold_ratio))

    def compact_history(
        self,
        messages: list[dict[str, Any]],
        existing_summary: str = "",
        summarizer: Callable[..., str] | None = None,
        force: bool = False,
        max_summary_tokens: int | None = None,
    ) -> CompactionResult:
        prepared = sanitize_history(copy.deepcopy(messages))
        before_tokens = estimate_context_tokens(prepared)
        threshold = self.input_budget_tokens
        metadata: dict[str, Any] = {
            "compressed": False,
            "compressed_reason": [],
            "snipped_tool_results": 0,
            "truncated_observations": 0,
            "summarized_messages": 0,
            "estimated_tokens_before": before_tokens,
            "estimated_tokens_after": 0,
            "context_limit": self.max_total_context_tokens,
            "context_threshold": threshold,
            "force": force,
        }

        should_compact = force or len(prepared) > self.max_history_messages or before_tokens > threshold
        if not should_compact:
            metadata["estimated_tokens_after"] = before_tokens
            return CompactionResult(messages=prepared, summary=existing_summary or "", metadata=metadata)

        snip_limit = min(self.max_observation_chars, 1000 if force else 2000)
        preserve_last_n = 3 if force else 6
        snipped = snip_old_tool_results(
            prepared,
            max_chars=snip_limit,
            preserve_last_n_messages=preserve_last_n,
        )
        if snipped:
            metadata["compressed"] = True
            metadata["compressed_reason"].append("observation_snipped")
            metadata["snipped_tool_results"] = snipped
            metadata["truncated_observations"] = snipped

        after_snip_tokens = estimate_context_tokens(prepared)
        should_summarize = force or len(prepared) > self.max_history_messages or after_snip_tokens > threshold
        if not should_summarize:
            metadata["estimated_tokens_after"] = after_snip_tokens
            metadata["compressed_reason"] = list(dict.fromkeys(metadata["compressed_reason"]))
            return CompactionResult(messages=prepared, summary=existing_summary or "", metadata=metadata)

        split = find_split_point(prepared, keep_ratio=self.keep_ratio)
        metadata["split_index"] = split
        if split <= 0:
            metadata["estimated_tokens_after"] = after_snip_tokens
            metadata["compressed_reason"] = list(dict.fromkeys(metadata["compressed_reason"]))
            return CompactionResult(messages=prepared, summary=existing_summary or "", metadata=metadata)

        old_messages = prepared[:split]
        recent_messages = sanitize_history(prepared[split:])
        summary = _call_summarizer(
            summarizer,
            old_messages,
            existing_summary or "",
            max_summary_tokens=max_summary_tokens,
        )
        metadata["compressed"] = True
        metadata["compressed_reason"].append("history_summarized")
        metadata["summarized_messages"] = len(old_messages)
        metadata["estimated_tokens_after"] = estimate_context_tokens(
            [{"role": "system", "content": summary}, *recent_messages]
        )
        metadata["compaction_failures"] = int(getattr(summarizer, "failure_count", 0) or 0)
        metadata["compaction_circuit_open"] = bool(getattr(summarizer, "circuit_open", False))
        metadata["compressed_reason"] = list(dict.fromkeys(metadata["compressed_reason"]))
        return CompactionResult(messages=recent_messages, summary=summary, metadata=metadata)

    def _keep_count(self, messages: list[dict[str, Any]]) -> int:
        keep_by_history = max(1, min(self.max_history_messages, len(messages)))
        keep_count = keep_by_history
        while keep_count > 1:
            recent = sanitize_history(messages[-keep_count:])
            candidate = [{"role": "system", "content": "Previous conversation summary:\n(summary)"}]
            candidate.extend(recent)
            if estimate_context_tokens(candidate) <= self.max_total_context_chars:
                return keep_count
            keep_count -= 1
        return keep_count

    def _truncate(self, content: str) -> str:
        if self.max_observation_chars <= 40:
            return content[: self.max_observation_chars]
        side = max(16, (self.max_observation_chars - 40) // 2)
        omitted = len(content) - side * 2
        return f"{content[:side]}\n...[truncated {omitted} chars]...\n{content[-side:]}"


def snip_old_tool_results(
    messages: list[dict[str, Any]],
    max_chars: int = 2000,
    preserve_last_n_messages: int = 6,
) -> int:
    cutoff = max(0, len(messages) - preserve_last_n_messages)
    snipped_count = 0
    for index in range(cutoff):
        message = messages[index]
        if message.get("role") != "tool":
            continue
        content = message.get("content", "")
        if not isinstance(content, str) or len(content) <= max_chars:
            continue
        first_half = content[: max_chars // 2]
        last_quarter = content[-(max_chars // 4):]
        omitted = len(content) - len(first_half) - len(last_quarter)
        message["content"] = f"{first_half}\n[... {omitted} chars snipped ...]\n{last_quarter}"
        snipped_count += 1
    return snipped_count


def find_split_point(messages: list[dict[str, Any]], keep_ratio: float = 0.3) -> int:
    if not messages:
        return 0
    keep_ratio = max(0.0, min(1.0, keep_ratio))
    total = estimate_context_tokens(messages)
    target = max(1, int(total * keep_ratio))
    running = 0
    raw_split = 0
    for index in range(len(messages) - 1, -1, -1):
        running += estimate_context_tokens([messages[index]])
        if running >= target:
            raw_split = index
            break
    adjusted = _respect_tool_pairs(messages, raw_split)
    if adjusted >= len(messages):
        return 0
    return adjusted


def _respect_tool_pairs(messages: list[dict[str, Any]], split: int) -> int:
    if split <= 0 or split >= len(messages):
        return split
    previous = messages[split - 1]
    if previous.get("role") == "assistant" and previous.get("tool_calls"):
        index = split
        while index < len(messages) and messages[index].get("role") == "tool":
            index += 1
        split = index
    while split < len(messages) and messages[split].get("role") == "tool":
        split += 1
    return split


def summarize_messages(messages: list[dict[str, Any]]) -> str:
    facts: list[str] = []
    for message in messages:
        role = message.get("role", "message")
        content = str(message.get("content") or "")
        if message.get("tool_calls"):
            content = f"{content} tool_calls={json.dumps(message['tool_calls'], ensure_ascii=False)}"
        if content:
            facts.append(f"- {role}: {content[:600]}")
    return "\n".join(facts) or "(no prior messages)"


def estimate_context_tokens(value: Any) -> int:
    text = _flatten_text(value)
    if not text:
        return 0
    chars_per_token = 1.0 if _is_cjk_heavy(text) else 2.8
    return int(len(text) / chars_per_token) + _message_overhead(value)


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    if hasattr(value, "model_dump"):
        try:
            return _flatten_text(value.model_dump(mode="json"))
        except TypeError:
            return _flatten_text(value.model_dump())
    return str(value)


def _is_cjk_heavy(text: str) -> bool:
    sample = text[:2000]
    if not sample:
        return False
    cjk_count = sum(1 for char in sample if "\u4e00" <= char <= "\u9fff" or "\u3040" <= char <= "\u30ff" or "\uac00" <= char <= "\ud7af")
    return cjk_count / len(sample) >= 0.2


def _message_overhead(value: Any) -> int:
    if isinstance(value, list):
        return len(value) * 4
    return 4


def _call_summarizer(
    summarizer: Callable[..., str] | None,
    messages: list[dict[str, Any]],
    existing_summary: str,
    max_summary_tokens: int | None = None,
) -> str:
    fallback = _merge_summaries(existing_summary, summarize_messages(messages))
    if summarizer is None:
        return limit_text_to_tokens(fallback, max_summary_tokens)
    try:
        summary = summarizer(messages, existing_summary=existing_summary)
    except TypeError:
        try:
            summary = summarizer(messages, existing_summary)
        except TypeError:
            summary = summarizer(messages)
    summary_text = str(summary or "").strip()
    if not summary_text:
        return limit_text_to_tokens(fallback, max_summary_tokens)
    return limit_text_to_tokens(_merge_summaries(existing_summary, summary_text), max_summary_tokens)


def limit_text_to_tokens(text: str, max_tokens: int | None) -> str:
    value = str(text or "").strip()
    if not value or not max_tokens or estimate_context_tokens(value) <= max_tokens:
        return value
    low, high = 1, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_context_tokens(value[:middle]) <= max_tokens:
            low = middle
        else:
            high = middle - 1
    limit = max(1, low)
    if limit < 80:
        return value[:limit]
    head = max(24, limit // 3)
    tail = max(24, limit - head - 35)
    omitted = max(0, len(value) - head - tail)
    return f"{value[:head]}\n...[summary trimmed {omitted} chars]...\n{value[-tail:]}"


def _merge_summaries(existing_summary: str, new_summary: str) -> str:
    existing_summary = str(existing_summary or "").strip()
    new_summary = str(new_summary or "").strip()
    if not existing_summary:
        return new_summary
    if not new_summary:
        return existing_summary
    if existing_summary in new_summary:
        return new_summary
    return f"{existing_summary}\n\n{new_summary}"
