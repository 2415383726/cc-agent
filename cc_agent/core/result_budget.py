from __future__ import annotations

from .messages import ToolResult


class ResultBudget:
    def __init__(self, max_observation_chars: int = 8000):
        self.max_observation_chars = max_observation_chars

    def apply(self, result: ToolResult) -> ToolResult:
        observation = result.llm_observation or "(tool completed with no output)"
        if len(observation) <= self.max_observation_chars:
            result.llm_observation = observation
            return result
        result.llm_observation = self._truncate(observation)
        result.metadata = {
            **result.metadata,
            "truncated": True,
            "original_observation_chars": len(observation),
        }
        return result

    def apply_batch(
        self,
        results: list[ToolResult],
        max_batch_chars: int | None = None,
    ) -> list[ToolResult]:
        if not results:
            return results
        limit = max(1, int(max_batch_chars or self.max_observation_chars * 2))
        total = sum(len(result.llm_observation or "") for result in results)
        if total <= limit:
            return results

        excess = total - limit
        ordinary = [
            result
            for result in results
            if not result.is_error and not bool((result.metadata or {}).get("requires_user_input"))
        ]
        protected = [result for result in results if result not in ordinary]
        for candidates, minimum in ((ordinary, 512), (protected, 512)):
            for result in sorted(candidates, key=lambda item: len(item.llm_observation or ""), reverse=True):
                content = result.llm_observation or ""
                reducible = max(0, len(content) - minimum)
                if reducible <= 0:
                    continue
                reduction = min(excess, reducible)
                self._apply_batch_limit(result, len(content) - reduction)
                excess -= reduction
                if excess <= 0:
                    return results

        if excess > 0:
            per_result_limit = max(1, limit // len(results))
            for result in results:
                self._apply_batch_limit(result, per_result_limit)
        return results

    def _apply_batch_limit(self, result: ToolResult, limit: int) -> None:
        content = result.llm_observation or ""
        if len(content) <= limit:
            return
        result.llm_observation = self._truncate_to(content, limit)
        result.metadata = {
            **(result.metadata or {}),
            "batch_truncated": True,
            "batch_original_observation_chars": len(content),
        }

    def _truncate(self, content: str) -> str:
        return self._truncate_to(content, self.max_observation_chars)

    @staticmethod
    def _truncate_to(content: str, limit: int) -> str:
        limit = max(1, int(limit))
        if limit <= 40:
            return content[:limit]
        side = max(16, (limit - 40) // 2)
        omitted = len(content) - side * 2
        return f"{content[:side]}\n...[truncated {omitted} chars]...\n{content[-side:]}"
