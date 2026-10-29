from __future__ import annotations

import json
import os
import unittest

from _support import (
    FakeSession,
    base_parameters,
    display_events,
    last_state,
    last_terminal,
    prompt_texts,
    run_turn,
    text_chunks,
    tool_chunks,
)

from pi_agent.state import decode_state

SKILLS = """
skills:
  - name: refund-policy
    description: Refund guidance
    content: |
      Refunds require an unused item and an order inside 30 days.
    resources:
      guide.md: "Step one: verify the order date."
  - name: needs-tool
    description: Requires an unavailable tool
    content: Should stay hidden.
    requires_tools: [missing_tool]
"""


class SkillRuntimeTests(unittest.TestCase):
    def test_user_activation_injects_skill_content(self) -> None:
        session = FakeSession([text_chunks("Using the policy")])
        outbox = run_turn(
            session,
            base_parameters(
                query="/skill:refund-policy please check order A-1042",
                app_skills_yaml=SKILLS,
            ),
        )
        self.assertEqual(last_terminal(outbox)["status"], "completed")
        prompts = prompt_texts(session.model.llm)
        self.assertTrue(any("Refunds require an unused item" in text for text in prompts))
        events = display_events(outbox)
        activations = [event for event in events if event.get("type") == "skill.activate"]
        self.assertEqual(len(activations), 1)
        self.assertEqual(activations[0]["activated_by"], "user")
        loaded = decode_state(last_state(outbox))
        self.assertEqual([skill["name"] for skill in loaded.state.active_skills], ["refund-policy"])

    def test_ineligible_skill_is_not_injected(self) -> None:
        session = FakeSession([text_chunks("ok")])
        outbox = run_turn(
            session,
            base_parameters(query="/skill:needs-tool do it", app_skills_yaml=SKILLS),
        )
        prompts = prompt_texts(session.model.llm)
        self.assertFalse(any("Should stay hidden" in text for text in prompts))
        events = display_events(outbox)
        self.assertTrue(any(event.get("type") == "skill.rejected" for event in events))

    def test_model_activation_and_bounded_read(self) -> None:
        session = FakeSession(
            [
                tool_chunks([{"name": "activate_skill", "arguments": '{"name":"refund-policy"}'}]),
                tool_chunks(
                    [
                        {
                            "name": "read_skill_resource",
                            "arguments": '{"name":"refund-policy","path":"guide.md","limit":9}',
                        }
                    ]
                ),
                text_chunks("The guide says to verify the date."),
            ]
        )
        outbox = run_turn(session, base_parameters(query="use the skill", app_skills_yaml=SKILLS))
        self.assertEqual(last_terminal(outbox)["status"], "completed")
        events = display_events(outbox)
        reads = [event for event in events if event.get("type") == "skill.read"]
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]["path"], "guide.md")
        prompts = prompt_texts(session.model.llm, index=1)
        self.assertTrue(any("Refunds require an unused item" in text for text in prompts))
        prompts = prompt_texts(session.model.llm, index=2)
        self.assertTrue(any("Step one:" in text for text in prompts))

    def test_traversal_is_rejected_and_visible(self) -> None:
        session = FakeSession(
            [
                tool_chunks(
                    [
                        {
                            "name": "read_skill_resource",
                            "arguments": '{"name":"refund-policy","path":"../secret"}',
                        }
                    ]
                ),
                text_chunks("I could not read that resource."),
            ]
        )
        outbox = run_turn(session, base_parameters(query="read it", app_skills_yaml=SKILLS))
        events = display_events(outbox)
        reads = [event for event in events if event.get("type") == "skill.read"]
        self.assertEqual(reads, [])
        notes = [event for event in events if event.get("type") == "activity"]
        self.assertTrue(any("Invalid skill resource path" in str(event.get("text") or "") for event in notes))
        self.assertEqual(last_terminal(outbox)["status"], "completed")


class RecoveryTests(unittest.TestCase):
    def test_cancel_clears_pending_without_model_call(self) -> None:
        ask = tool_chunks(
            [
                {
                    "name": "ask_user",
                    "arguments": json.dumps(
                        {"questions": [{"id": "q", "question": "Continue?", "type": "text"}]}
                    ),
                }
            ]
        )
        session = FakeSession([ask])
        first = run_turn(session, base_parameters(query="ask"))
        pending = decode_state(last_state(first)).state.pending
        second = run_turn(
            session,
            base_parameters(
                state=last_state(first),
                interaction={"type": "cancel", "pending_id": pending["id"]},
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "cancelled")
        self.assertIsNone(decode_state(last_state(second)).state.pending)
        self.assertEqual(len(session.model.llm.calls), 1)
        events = display_events(second)
        self.assertTrue(any(event.get("type") == "question.cancelled" for event in events))

    def test_state_from_another_conversation_is_rejected(self) -> None:
        session = FakeSession([text_chunks("first")])
        first = run_turn(session, base_parameters(query="one", conversation_id="conv-1"))
        second = run_turn(
            session,
            base_parameters(query="two", state=last_state(first), conversation_id="conv-2"),
        )
        self.assertEqual(last_terminal(second)["status"], "failed")
        self.assertEqual(last_terminal(second)["error"]["code"], "invalid_state")
        self.assertEqual(len(session.model.llm.calls), 1)

    def test_state_save_failure_is_not_reported_as_completed(self) -> None:
        long_text = os.urandom(30_000).hex()
        session = FakeSession([text_chunks(long_text)])
        outbox = run_turn(
            session,
            base_parameters(runtime={"state_max_encoded_bytes": 600}),
        )
        terminal = last_terminal(outbox)
        self.assertEqual(terminal["status"], "state_save_failed")
        self.assertEqual(terminal["error"]["code"], "state_save_failed")
        self.assertIn("not reported as completed", terminal["answer"])
        statuses = {event.get("status") for event in _terminal_entry(outbox)}
        self.assertEqual(statuses, {"state_save_failed"})

    def test_unknown_remote_outcome_asks_for_verification(self) -> None:
        tool = {"name": "write", "description": "Write", "parameters": {"type": "object", "properties": {}}}
        session = FakeSession(
            [tool_chunks([{"name": "write"}]), text_chunks("Please verify the record.")],
            tool_responses=[RuntimeError("socket reset")],
        )
        outbox = run_turn(session, base_parameters(query="write", tools=[tool]))
        events = display_events(outbox)
        ends = [event for event in events if event.get("type") == "tool.end"]
        self.assertEqual(ends[0]["status"], "unknown")
        self.assertEqual(ends[0]["execution_outcome"], "unknown")
        self.assertNotIn("socket reset", json.dumps(outbox))


def _terminal_entry(outbox):
    return [
        event
        for event in display_events(outbox)
        if event.get("type") in {"run.state", "run.done"}
    ]


if __name__ == "__main__":
    unittest.main()
