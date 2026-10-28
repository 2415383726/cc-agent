from __future__ import annotations

import json
from typing import Any

from .model_adapter import strip_dify_history_from_model_config, to_dify_prompt_messages
from .run_budget import RunBudget, RunBudgetExceeded

try:  # pragma: no cover - exercised inside Dify runtime
    from dify_plugin.entities.model.llm import LLMModelConfig
except Exception:  # pragma: no cover
    LLMModelConfig = None


class DifyHistorySummarizer:
    def __init__(
        self,
        session: Any,
        model_config: Any,
        max_consecutive_failures: int = 3,
        run_budget: RunBudget | None = None,
    ):
        self.session = session
        self.run_budget = run_budget
        self.model_config = model_config
        self.max_consecutive_failures = max(1, int(max_consecutive_failures))
        self.consecutive_failures = 0
        self.failure_count = 0
        self.circuit_open = False

    def __call__(self, messages: list[dict[str, Any]], existing_summary: str = "") -> str:
        if self.circuit_open:
            return _fallback_summary(messages, existing_summary)
        prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize prior assistant conversation state for continuation. "
                    "Preserve user goals, current task state, key decisions, tool result conclusions, "
                    "task changes, open tasks, and important conversation facts. "
                    "Return one complete replacement summary, updating or removing superseded "
                    "decisions and constraints according to the newest messages. "
                    "Do not invent details."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"existing_summary": existing_summary or "", "messages_to_compact": messages},
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            if self.run_budget is not None:
                self.run_budget.before_model()
            response = self.session.model.llm.invoke(
                model_config=self._model_config(),
                prompt_messages=to_dify_prompt_messages(prompt),
                tools=None,
                stop=None,
                stream=False,
            )
            if self.run_budget is not None:
                self.run_budget.record_usage(getattr(response, "usage", None))
            message = getattr(response, "message", response)
            content = str(getattr(message, "content", "") or "").strip()
            if not content:
                self._record_failure()
                return _fallback_summary(messages, existing_summary)
            self.consecutive_failures = 0
            return content
        except RunBudgetExceeded:
            raise
        except Exception:
            self._record_failure()
            return _fallback_summary(messages, existing_summary)

    def _record_failure(self) -> None:
        self.failure_count += 1
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.circuit_open = True

    def _model_config(self) -> Any:
        config = strip_dify_history_from_model_config(self.model_config)
        if LLMModelConfig is None:
            return config
        if hasattr(config, "model_dump"):
            return LLMModelConfig(**config.model_dump(mode="json"))
        if isinstance(config, dict):
            return LLMModelConfig(**config)
        return config


def _fallback_summary(messages: list[dict[str, Any]], existing_summary: str = "") -> str:
    lines = []
    if existing_summary:
        lines.append(str(existing_summary).strip())
    for message in messages:
        content = str(message.get("content") or "")
        if message.get("tool_calls"):
            content += " tool_calls=" + json.dumps(message["tool_calls"], ensure_ascii=False)
        if content:
            lines.append(f"- {message.get('role', 'message')}: {content[:500]}")
    return "\n".join(lines) or "(no prior messages)"


def compression_activity(
    status: str, trigger: str, compression_id: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload.update(
        {
            "status": status,
            "trigger": trigger,
            "compressionId": compression_id,
            "messageId": compression_id,
        }
    )
    return payload
