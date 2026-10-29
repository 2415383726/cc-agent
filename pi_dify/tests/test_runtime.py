from __future__ import annotations

import json
import unittest

from _support import (
    FakeSession,
    answer_text,
    base_parameters,
    display_events,
    event_types,
    last_state,
    last_terminal,
    prompt_texts,
    run_turn,
    text_chunks,
    tool_chunks,
)

from pi_agent.state import decode_state


class TextTurnTests(unittest.TestCase):
    def test_text_turn_outputs_state_before_terminal(self) -> None:
        session = FakeSession([text_chunks("Hello!")])
        outbox = run_turn(session, base_parameters(query="hi"))
        types = [item.get("type") for item in outbox]
        self.assertIn("state", types)
        self.assertLess(types.index("state"), types.index("text"))
        terminal = last_terminal(outbox)
        self.assertEqual(terminal["status"], "completed")
        self.assertEqual(terminal["answer"], "Hello!")
        self.assertEqual(terminal["state_summary"]["delivery_status"], "encoded")
        self.assertGreater(terminal["state_summary"]["encoded_bytes"], 0)
        self.assertEqual(answer_text(outbox), "Hello!")
        state = last_state(outbox)
        self.assertTrue(state.startswith("piagent-state:v1:gzip-base64:"))
        loaded = decode_state(state)
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.state.revision, 1)
        self.assertEqual(loaded.state.last_answer, "Hello!")
        self.assertIn("message.delta", event_types(outbox))
        self.assertIn("message.end", event_types(outbox))

    def test_second_turn_rebuilds_history_without_dify_history(self) -> None:
        session = FakeSession([text_chunks("Hello!"), text_chunks("Again")])
        first = run_turn(session, base_parameters(query="hi"))
        state = last_state(first)
        second = run_turn(session, base_parameters(query="again", state=state))
        self.assertEqual(last_terminal(second)["status"], "completed")
        prompts = prompt_texts(session.model.llm, index=1)
        self.assertTrue(any("hi" in text for text in prompts))
        self.assertTrue(any("Hello!" in text for text in prompts))
        loaded = decode_state(last_state(second))
        self.assertEqual(loaded.state.revision, 2)
        self.assertNotIn("history_prompt_messages", session.model.llm.calls[1])

    def test_usage_is_reported_separately(self) -> None:
        session = FakeSession([text_chunks("Hi")])
        outbox = run_turn(session, base_parameters())
        usage = last_terminal(outbox)["stats"]["usage"]
        self.assertEqual(usage["reported"]["total_tokens"], 15)
        self.assertEqual(usage["unknown_usage_requests"], 0)


class ToolTests(unittest.TestCase):
    def test_tool_call_executes_and_pairs(self) -> None:
        tool = {
            "name": "echo",
            "description": "Echo a value",
            "parameters": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        }
        session = FakeSession(
            [tool_chunks([{"name": "echo", "arguments": '{"value":"x"}'}]), text_chunks("Done")],
            tool_responses=[[{"type": "text", "message": "echoed x"}]],
        )
        outbox = run_turn(session, base_parameters(query="echo", tools=[tool]))
        self.assertEqual(len(session.tool.calls), 1)
        self.assertEqual(session.tool.calls[0]["tool_name"], "echo")
        self.assertEqual(session.tool.calls[0]["parameters"]["value"], "x")
        terminal = last_terminal(outbox)
        self.assertEqual(terminal["status"], "completed")
        self.assertEqual(terminal["answer"], "Done")
        ends = [event for event in display_events(outbox) if event.get("type") == "tool.end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]["status"], "ok")
        loaded = decode_state(last_state(outbox))
        self.assertIsNone(loaded.error)
        self.assertIn("echoed x", json.dumps(loaded.state.entries))

    def test_invalid_tool_json_is_not_executed(self) -> None:
        tool = {
            "name": "echo",
            "description": "Echo",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession(
            [tool_chunks([{"name": "echo", "arguments": '{"value":'}]), text_chunks("Recovered")],
            tool_responses=[],
        )
        outbox = run_turn(session, base_parameters(query="echo", tools=[tool]))
        self.assertEqual(len(session.tool.calls), 0)
        self.assertEqual(last_terminal(outbox)["status"], "completed")
        self.assertIn("Invalid arguments", json.dumps(display_events(outbox)))

    def test_tool_failure_is_unknown_not_retried(self) -> None:
        tool = {
            "name": "write",
            "description": "Write",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession(
            [tool_chunks([{"name": "write"}]), text_chunks("Check it")],
            tool_responses=[RuntimeError("connection reset")],
        )
        outbox = run_turn(session, base_parameters(query="write", tools=[tool]))
        ends = [event for event in display_events(outbox) if event.get("type") == "tool.end"]
        self.assertEqual(ends[0]["status"], "unknown")
        self.assertEqual(ends[0]["execution_outcome"], "unknown")
        self.assertEqual(len(session.tool.calls), 1)
        self.assertNotIn("connection reset", json.dumps(outbox))


class AskUserTests(unittest.TestCase):
    def _question_call(self) -> list[dict]:
        return tool_chunks(
            [
                {
                    "name": "ask_user",
                    "arguments": json.dumps(
                        {
                            "title": "Details",
                            "questions": [
                                {
                                    "id": "color",
                                    "question": "Which color?",
                                    "type": "single",
                                    "options": [
                                        {"id": "red", "label": "Red"},
                                        {"id": "blue", "label": "Blue"},
                                    ],
                                },
                                {
                                    "id": "notes",
                                    "question": "Notes",
                                    "type": "text",
                                    "required": False,
                                },
                            ],
                        }
                    ),
                },
                {"name": "echo"},
            ]
        )

    def test_question_pauses_batch_and_resumes_next_turn(self) -> None:
        tool = {
            "name": "echo",
            "description": "Echo",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession(
            [self._question_call(), text_chunks("Thanks")],
            tool_responses=[[{"type": "text", "message": "should not run"}]],
        )
        first = run_turn(session, base_parameters(query="ask me", tools=[tool]))
        self.assertEqual(last_terminal(first)["status"], "awaiting_user")
        state = last_state(first)
        loaded = decode_state(state)
        self.assertEqual(loaded.state.pending["kind"], "ask_user")
        self.assertEqual(len(session.model.llm.calls), 1)
        self.assertEqual(len(session.tool.calls), 0)
        ends = [event for event in display_events(first) if event.get("type") == "tool.end"]
        statuses = sorted(event["status"] for event in ends)
        self.assertIn("awaiting_user", statuses)
        self.assertIn("not_executed", statuses)

        question_id = loaded.state.pending["questionnaire"]["id"]
        second = run_turn(
            session,
            base_parameters(
                query="",
                state=state,
                tools=[tool],
                interaction={
                    "type": "ask_user",
                    "pending_id": question_id,
                    "answers": {"color": "blue", "notes": "any"},
                },
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "completed")
        self.assertEqual(len(session.model.llm.calls), 2)
        prompts = prompt_texts(session.model.llm, index=1)
        self.assertTrue(any("Answers to the questionnaire" in text for text in prompts))
        self.assertTrue(any("Blue" in text for text in prompts))
        self.assertIsNone(decode_state(last_state(second)).state.pending)

    def test_bad_answer_keeps_pending_and_skips_model(self) -> None:
        session = FakeSession([self._question_call(), text_chunks("never")])
        first = run_turn(session, base_parameters(query="ask me"))
        state = last_state(first)
        question_id = decode_state(state).state.pending["questionnaire"]["id"]
        second = run_turn(
            session,
            base_parameters(
                state=state,
                interaction={
                    "type": "ask_user",
                    "pending_id": question_id,
                    "answers": {"color": "purple"},
                },
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "awaiting_user")
        self.assertEqual(last_terminal(second)["error"]["code"], "pending_invalid")
        self.assertEqual(len(session.model.llm.calls), 1)
        self.assertIsNotNone(decode_state(last_state(second)).state.pending)

    def test_duplicate_answer_is_rejected_without_model_call(self) -> None:
        session = FakeSession([self._question_call(), text_chunks("Thanks"), text_chunks("never")])
        first = run_turn(session, base_parameters(query="ask me"))
        state = last_state(first)
        question_id = decode_state(state).state.pending["questionnaire"]["id"]
        interaction = {"type": "ask_user", "pending_id": question_id, "answers": {"color": "red"}}
        second = run_turn(session, base_parameters(state=state, interaction=interaction))
        third = run_turn(
            session, base_parameters(state=last_state(second), interaction=interaction)
        )
        self.assertEqual(last_terminal(third)["status"], "failed")
        self.assertEqual(last_terminal(third)["error"]["code"], "pending_consumed")
        self.assertEqual(len(session.model.llm.calls), 2)


class ApprovalTests(unittest.TestCase):
    def test_approval_executes_once_after_current_policy_check(self) -> None:
        tool = {
            "name": "write",
            "description": "Write a record",
            "parameters": {"type": "object", "properties": {"value": {"type": "string"}}},
        }
        session = FakeSession(
            [
                tool_chunks([{"name": "write", "arguments": '{"value":"x"}'}]),
                text_chunks("Written"),
                text_chunks("never"),
            ],
            tool_responses=[[{"type": "text", "message": "written"}]],
        )
        config = {"approval_mode": "configured", "approval_tools": ["write"]}
        first = run_turn(session, base_parameters(query="write it", tools=[tool], runtime=config))
        self.assertEqual(last_terminal(first)["status"], "awaiting_approval")
        self.assertEqual(len(session.tool.calls), 0)
        state = last_state(first)
        pending = decode_state(state).state.pending
        self.assertEqual(pending["kind"], "approval")

        second = run_turn(
            session,
            base_parameters(
                query="",
                tools=[tool],
                runtime=config,
                state=state,
                interaction={
                    "type": "approval",
                    "pending_id": pending["id"],
                    "decision": "approve",
                    "scope": "session",
                },
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "completed")
        self.assertEqual(len(session.tool.calls), 1)
        loaded = decode_state(last_state(second))
        self.assertIsNone(loaded.state.pending)
        self.assertEqual([grant["tool"] for grant in loaded.state.grants], ["write"])
        self.assertEqual(
            sum(
                1
                for entry in loaded.state.entries
                if entry.get("type") == "message"
                and entry.get("message", {}).get("role") == "toolResult"
            ),
            1,
        )
        self.assertIn("Written", last_terminal(second)["answer"])

    def test_rejection_is_not_executed_and_not_replayed(self) -> None:
        tool = {
            "name": "write",
            "description": "Write",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession(
            [tool_chunks([{"name": "write"}]), text_chunks("Understood")], tool_responses=[]
        )
        config = {"approval_mode": "configured", "approval_tools": ["write"]}
        first = run_turn(session, base_parameters(query="write", tools=[tool], runtime=config))
        pending = decode_state(last_state(first)).state.pending
        second = run_turn(
            session,
            base_parameters(
                query="",
                tools=[tool],
                runtime=config,
                state=last_state(first),
                interaction={"type": "approval", "pending_id": pending["id"], "decision": "reject"},
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "completed")
        self.assertEqual(len(session.tool.calls), 0)
        self.assertIsNone(decode_state(last_state(second)).state.pending)


class BudgetTests(unittest.TestCase):
    def test_tool_budget_blocks_execution_and_stops(self) -> None:
        tool = {
            "name": "echo",
            "description": "Echo",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession(
            [tool_chunks([{"name": "echo"}]), text_chunks("never")], tool_responses=[]
        )
        outbox = run_turn(
            session, base_parameters(query="echo", tools=[tool], runtime={"max_tool_calls": 0})
        )
        self.assertEqual(len(session.tool.calls), 0)
        self.assertEqual(last_terminal(outbox)["status"], "budget_exhausted")
        self.assertEqual(len(session.model.llm.calls), 1)
        ends = [event for event in display_events(outbox) if event.get("type") == "tool.end"]
        self.assertEqual(ends[0]["status"], "not_executed")


class OverflowTests(unittest.TestCase):
    def test_single_overflow_recovery_compacts_and_retries(self) -> None:
        session = FakeSession(
            [
                text_chunks("First answer"),
                text_chunks("Second answer"),
                Exception("maximum context length exceeded"),
                text_chunks("Summary of the conversation"),
                text_chunks("Recovered answer"),
            ]
        )
        first = run_turn(session, base_parameters(query="first"))
        second_turn = run_turn(session, base_parameters(query="second", state=last_state(first)))
        second = run_turn(
            session,
            base_parameters(
                query="third question",
                state=last_state(second_turn),
                runtime={"auto_compact": False, "compaction_enabled": True},
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "completed")
        self.assertEqual(last_terminal(second)["answer"], "Recovered answer")
        types = event_types(second)
        self.assertIn("compaction.start", types)
        self.assertIn("compaction.end", types)
        self.assertEqual(len(session.model.llm.calls), 5)
        prompts = prompt_texts(session.model.llm, index=4)
        self.assertTrue(any("third question" in text for text in prompts))


class NoReplayOverflowTests(unittest.TestCase):
    def test_overflow_after_a_tool_does_not_replay_the_tool(self) -> None:
        tool = {
            "name": "write",
            "description": "Write once",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession(
            [
                tool_chunks([{"name": "write"}]),
                Exception("maximum context length exceeded"),
                text_chunks("Summary after the tool"),
                text_chunks("Continued with the preserved tool result"),
            ],
            tool_responses=[[{"type": "text", "message": "written once"}]],
        )
        outbox = run_turn(
            session,
            base_parameters(
                query="write it",
                tools=[tool],
                runtime={"auto_compact": False, "compaction_enabled": True},
            ),
        )
        self.assertEqual(last_terminal(outbox)["status"], "completed")
        self.assertEqual(len(session.tool.calls), 1)
        self.assertEqual(len(session.model.llm.calls), 4)
        prompts = prompt_texts(session.model.llm, index=3)
        self.assertTrue(any("write it" in text for text in prompts))
        self.assertTrue(any("written once" in text for text in prompts))
        self.assertTrue(any("context was compacted" in text for text in prompts))


class ApprovalExpiryRuntimeTests(unittest.TestCase):
    def test_configured_expiry_rejects_the_decision(self) -> None:
        import time

        tool = {
            "name": "write",
            "description": "Write",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession([tool_chunks([{"name": "write"}])])
        config = {
            "approval_mode": "configured",
            "approval_tools": ["write"],
            "approval_timeout_seconds": 0.001,
        }
        first = run_turn(session, base_parameters(query="write", tools=[tool], runtime=config))
        pending = decode_state(last_state(first)).state.pending
        time.sleep(0.01)
        second = run_turn(
            session,
            base_parameters(
                query="",
                tools=[tool],
                runtime=config,
                state=last_state(first),
                interaction={
                    "type": "approval",
                    "pending_id": pending["id"],
                    "decision": "approve",
                },
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "awaiting_approval")
        self.assertEqual(last_terminal(second)["error"]["code"], "pending_expired")
        self.assertEqual(len(session.tool.calls), 0)


class NestedPendingTests(unittest.TestCase):
    def test_new_pending_created_during_approval_resume_is_persisted(self) -> None:
        write = {
            "name": "write",
            "description": "Write",
            "parameters": {"type": "object", "properties": {}},
        }
        ask = tool_chunks(
            [
                {
                    "name": "ask_user",
                    "arguments": json.dumps(
                        {"questions": [{"id": "next", "question": "Continue?", "type": "text"}]}
                    ),
                }
            ]
        )
        session = FakeSession(
            [tool_chunks([{"name": "write"}]), ask],
            tool_responses=[[{"type": "text", "message": "written"}]],
        )
        config = {"approval_mode": "configured", "approval_tools": ["write"]}
        first = run_turn(session, base_parameters(query="write", tools=[write], runtime=config))
        pending = decode_state(last_state(first)).state.pending
        second = run_turn(
            session,
            base_parameters(
                query="",
                tools=[write],
                runtime=config,
                state=last_state(first),
                interaction={
                    "type": "approval",
                    "pending_id": pending["id"],
                    "decision": "approve",
                    "scope": "once",
                },
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "awaiting_user")
        loaded = decode_state(last_state(second))
        self.assertEqual(loaded.state.pending["kind"], "ask_user")

    def test_approval_cannot_target_a_different_tool(self) -> None:
        write = {
            "name": "write",
            "description": "Write",
            "parameters": {"type": "object", "properties": {}},
        }
        other = {
            "name": "other",
            "description": "Other",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession(
            [tool_chunks([{"name": "write"}]), text_chunks("should not run")], tool_responses=[]
        )
        config = {"approval_mode": "configured", "approval_tools": ["write", "other"]}
        first = run_turn(
            session, base_parameters(query="write", tools=[write, other], runtime=config)
        )
        state_text = last_state(first)
        from pi_agent.state import decode_state as decode

        state = decode(state_text).state
        state.pending["tool_name"] = "other"
        from pi_agent.state import encode_state

        tampered = encode_state(state)
        second = run_turn(
            session,
            base_parameters(
                query="",
                tools=[write, other],
                runtime=config,
                state=tampered.value,
                interaction={
                    "type": "approval",
                    "pending_id": state.pending["id"],
                    "decision": "approve",
                },
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "awaiting_approval")
        self.assertEqual(last_terminal(second)["error"]["code"], "pending_invalid")
        self.assertEqual(len(session.tool.calls), 0)


if __name__ == "__main__":
    unittest.main()
