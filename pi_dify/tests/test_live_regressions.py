"""Regressions found during live Dify 1.5.0 integration."""

from __future__ import annotations

import json
import unittest

from pi_agent.config import RuntimeConfig, parse_request
from pi_agent.stream import ThinkingTagSplitter


class DoubleEncodedInputsTests(unittest.TestCase):
    """Dify template references deliver user inputs JSON-quoted."""

    def test_interaction_unwraps_json_quoted_string(self) -> None:
        payload = {"type": "ask_user", "pending_id": "qst_1", "answers": {"drink": "coffee"}}
        request = parse_request(
            {
                "model": {"model": "m", "provider": "p", "mode": "chat"},
                "query": "提交交互",
                "interaction": json.dumps(json.dumps(payload)),
            }
        )
        self.assertEqual(request.interaction["type"], "ask_user")
        self.assertEqual(request.interaction["answers"]["drink"], "coffee")

    def test_interaction_unwraps_quote_wrapped_string(self) -> None:
        """Dify 1.5 workflow references wrap paragraph values in literal quotes.

        The wrap is string concatenation, not JSON encoding: the inner quotes
        are unescaped, so the whole value is not valid JSON and must be
        unwrapped by stripping the outer pair (observed live 2026-11-07).
        """
        payload = {"type": "ask_user", "pending_id": "qst_1", "answers": {"drink": "coffee"}}
        wrapped = '"' + json.dumps(payload) + '"'
        request = parse_request(
            {
                "model": {"model": "m", "provider": "p", "mode": "chat"},
                "query": "提交交互",
                "interaction": wrapped,
            }
        )
        self.assertEqual(request.interaction["type"], "ask_user")
        self.assertEqual(request.interaction["answers"]["drink"], "coffee")

    def test_runtime_config_unwraps_json_quoted_string(self) -> None:
        config = RuntimeConfig.from_value(json.dumps(json.dumps({"thinking_tags": True})))
        self.assertIs(config.thinking_tags, True)

    def test_non_object_interaction_still_rejected(self) -> None:
        from pi_agent.errors import PiError

        with self.assertRaises(PiError):
            parse_request(
                {
                    "model": {"model": "m", "provider": "p", "mode": "chat"},
                    "query": "q",
                    "interaction": json.dumps(json.dumps(["not", "an", "object"])),
                }
            )


class ThinkingMarkerTests(unittest.TestCase):
    def test_complete_marker_is_stripped(self) -> None:
        splitter = ThinkingTagSplitter()
        events: list[tuple[str, str]] = []
        events += splitter.feed("<think><!--dify-deepseek-reasoning-->User wants coffee.")
        events += splitter.feed("</think>Answer!")
        events += splitter.flush()
        thinking = "".join(text for kind, text in events if kind == "thinking")
        text = "".join(text for kind, text in events if kind == "text")
        self.assertEqual(thinking, "User wants coffee.")
        self.assertEqual(text, "Answer!")

    def test_marker_split_across_chunks_is_stripped(self) -> None:
        splitter = ThinkingTagSplitter()
        events: list[tuple[str, str]] = []
        for chunk in ("<think><!--dify-de", "epseek-reasoning--", ">User waits.", "</think>ok"):
            events += splitter.feed(chunk)
        events += splitter.flush()
        thinking = "".join(text for kind, text in events if kind == "thinking")
        text = "".join(text for kind, text in events if kind == "text")
        self.assertEqual(thinking, "User waits.")
        self.assertEqual(text, "ok")

    def test_plain_thinking_untouched(self) -> None:
        splitter = ThinkingTagSplitter()
        events = splitter.feed("<think>plain reasoning</think>out")
        events += splitter.flush()
        thinking = "".join(text for kind, text in events if kind == "thinking")
        self.assertEqual(thinking, "plain reasoning")


class StrategyStateFallbackTests(unittest.TestCase):
    def _strategy(self) -> tuple[object, object]:
        import strategies.pi_agent_dify as module
        from strategies.pi_agent_dify import PiAgentStrategy

        strategy = PiAgentStrategy.__new__(PiAgentStrategy)
        strategy.session = None

        class Fake:
            def create_text_message(self, content):
                return ("text", content)

            def create_variable_message(self, name, value):
                return ("variable", name, value)

            def create_log_message(self, label, data, status):
                return ("log", label, data, status)

            def _log(self, label, data, *, is_error=False):
                return ("log", label, data, is_error)

        fake = Fake()
        for name in (
            "create_text_message",
            "create_variable_message",
            "create_log_message",
            "_log",
        ):
            setattr(strategy, name, getattr(fake, name))
        return strategy, module

    def test_early_failure_reemits_agent_state(self) -> None:
        strategy, module = self._strategy()
        original = module.PiAgentRuntime

        class ExplodingRuntime:
            def __init__(self, session) -> None:
                pass

            def run(self, parameters):
                raise RuntimeError("boom before request build")
                yield  # pragma: no cover - generator marker

        module.PiAgentRuntime = ExplodingRuntime
        try:
            messages = list(
                strategy._invoke({"agent_state": "piagent-state:v1:gzip-base64:old", "query": "q"})
            )
        finally:
            module.PiAgentRuntime = original
        self.assertEqual(
            messages[-1], ("variable", "agent_state", "piagent-state:v1:gzip-base64:old")
        )
        self.assertTrue(any(m == ("text", "The Pi agent run failed.") for m in messages))

    def test_state_emitting_run_has_no_fallback(self) -> None:
        strategy, module = self._strategy()
        original = module.PiAgentRuntime

        class StateRuntime:
            def __init__(self, session) -> None:
                pass

            def run(self, parameters):
                yield {"type": "state", "name": "agent_state", "value": "new-encoded"}
                yield {"type": "text", "content": "done"}

        module.PiAgentRuntime = StateRuntime
        try:
            messages = list(strategy._invoke({"agent_state": "old", "query": "q"}))
        finally:
            module.PiAgentRuntime = original
        self.assertIn(("variable", "agent_state", "new-encoded"), messages)
        self.assertNotIn(("variable", "agent_state", "old"), messages)


if __name__ == "__main__":
    unittest.main()
