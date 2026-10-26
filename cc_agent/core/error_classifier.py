from __future__ import annotations

import re


class ContextOverflowError(RuntimeError):
    """Raised when CC Agent can prove a request cannot fit before model invocation."""


_CONTEXT_ERROR_PATTERNS = (
    "maximum context length",
    "maximum context window",
    "context length exceeded",
    "context window exceeded",
    "context_length_exceeded",
    "prompt is too long",
    "prompt too long",
    "input is too long",
    "too many input tokens",
    "input tokens exceed",
    "exceeds the model's context",
    "exceeds the model context",
)


def classify_error(exc: Exception) -> str:
    if isinstance(exc, ContextOverflowError):
        return "context_overflow"
    text = str(exc).lower()
    if any(pattern in text for pattern in _CONTEXT_ERROR_PATTERNS):
        return "context_overflow"
    if "tool" in text:
        return "tool_error"
    return "model_error"


def extract_context_numbers(exc: Exception) -> list[int]:
    return [int(match) for match in re.findall(r"\b\d{4,}\b", str(exc))]
