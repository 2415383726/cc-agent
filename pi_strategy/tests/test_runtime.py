from __future__ import annotations

import json
import unittest

from _support import (
    FakeSession,
    base_parameters,
    json_payloads,
    last_state,
    last_terminal,
    log_labels,
    prompt_texts,
    run_turn,
    streamed_text,
    text_chunks,
    text_items,
    tool_cards,
    tool_chunks,
)

from pi_strategy.state import decode_state


class TextTurnTests(unittest.TestCase):
    def test_text_turn_outputs_state_before_terminal(self) -> None:
        session = FakeSession([text_chunks("Hello!")])
        outbox = run_turn(session, base_parameters(query="hi"))
        types = [item.get("type") for item in outbox]
        self.assertIn("state", types)
        self.assertIn("json", types)
        # State precedes the terminal JSON payload; the streamed answer
        # (deltas) necessarily precedes both because it happens during the run.
        self.assertLess(types.index("state"), types.index("json"))
        terminal = last_terminal(outbox)
        self.assertEqual(terminal["status"], "completed")
        self.assertEqual(terminal["answer"], "Hello!")
        self.assertEqual(terminal["state_summary"]["delivery_status"], "encoded")
        self.assertGreater(terminal["state_summary"]["encoded_bytes"], 0)
        self.assertEqual(text_items(outbox)[-1], "Hello!")
        state = last_state(outbox)
        self.assertTrue(state.startswith("pistrategy-state:v1:gzip-base64:"))
        loaded = decode_state(state)
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.state.revision, 1)
        self.assertEqual(loaded.state.last_answer, "Hello!")
        self.assertIn("Run started", log_labels(outbox))
        self.assertIn("Run finished", log_labels(outbox))
        # Completed answers are not re-emitted as a final text; the variable
        # carries the answer for downstream workflow nodes instead.
        self.assertNotIn(("state", "answer"), [(i.get("type"), i.get("name")) for i in outbox[:1]])
        answer_vars = [i for i in outbox if i.get("type") == "state" and i.get("name") == "answer"]
        self.assertEqual(answer_vars[-1]["value"], "Hello!")

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
        cards = tool_cards(outbox)
        self.assertEqual(len(cards), 1)
        self.assertIn("echo", cards[0])
        self.assertIn("已运行", cards[0])
        self.assertIn("echoed x", cards[0])
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
        self.assertIn(
            "Invalid arguments", streamed_text(outbox) + json.dumps(json_payloads(outbox))
        )

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
        cards = tool_cards(outbox)
        self.assertIn("结果未知", cards[0])
        self.assertEqual(len(session.tool.calls), 1)
        self.assertNotIn("connection reset", json.dumps(outbox))


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
        # The approval request is rendered as text with reply keywords.
        self.assertTrue(any("工具确认" in text for text in text_items(first)))
        self.assertTrue(any("write" in text for text in text_items(first)))

        second = run_turn(
            session,
            base_parameters(query="当前会话始终允许", tools=[tool], runtime=config, state=state),
        )
        self.assertEqual(last_terminal(second)["status"], "completed")
        self.assertEqual(len(session.tool.calls), 1)
        loaded = decode_state(last_state(second))
        self.assertIsNone(loaded.state.pending)
        self.assertEqual([grant["tool"] for grant in loaded.state.grants], ["write"])
        # The approval-resumed execution renders its own native tool card.
        approve_cards = [card for card in tool_cards(second) if "write" in card]
        self.assertTrue(approve_cards)
        self.assertIn("已运行", approve_cards[-1])
        self.assertIn("written", approve_cards[-1])
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
        second = run_turn(
            session,
            base_parameters(query="拒绝", tools=[tool], runtime=config, state=last_state(first)),
        )
        self.assertEqual(last_terminal(second)["status"], "completed")
        self.assertEqual(len(session.tool.calls), 0)
        self.assertIsNone(decode_state(last_state(second)).state.pending)
        # The rejection renders a not-executed card instead of a run card.
        reject_cards = [card for card in tool_cards(second) if "write" in card]
        self.assertTrue(reject_cards)
        self.assertIn("未执行", reject_cards[-1])


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
        cards = tool_cards(outbox)
        self.assertIn("未执行", cards[0])


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
        labels = log_labels(second)
        self.assertIn("Compaction started", labels)
        self.assertIn("Compaction finished", labels)
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
        time.sleep(0.01)
        second = run_turn(
            session,
            base_parameters(query="同意", tools=[tool], runtime=config, state=last_state(first)),
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
        publish = {
            "name": "publish",
            "description": "Publish",
            "parameters": {"type": "object", "properties": {}},
        }
        # The approval resume continues the batch; the model then calls a second
        # approval-required tool, which opens a new pending approval.
        session = FakeSession(
            [tool_chunks([{"name": "write"}]), tool_chunks([{"name": "publish"}])],
            tool_responses=[[{"type": "text", "message": "written"}]],
        )
        config = {"approval_mode": "configured", "approval_tools": ["write", "publish"]}
        first = run_turn(
            session, base_parameters(query="write", tools=[write, publish], runtime=config)
        )
        self.assertEqual(decode_state(last_state(first)).state.pending["kind"], "approval")
        second = run_turn(
            session,
            base_parameters(
                query="同意", tools=[write, publish], runtime=config, state=last_state(first)
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "awaiting_approval")
        loaded = decode_state(last_state(second))
        self.assertEqual(loaded.state.pending["kind"], "approval")
        self.assertEqual(loaded.state.pending["tool_name"], "publish")
        # The approved write ran exactly once; the second call awaits approval.
        self.assertEqual([call["tool_name"] for call in session.tool.calls], ["write"])

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
        from pi_strategy.state import decode_state as decode

        state = decode(state_text).state
        state.pending["tool_name"] = "other"
        from pi_strategy.state import encode_state

        tampered = encode_state(state)
        second = run_turn(
            session,
            base_parameters(
                query="同意", tools=[write, other], runtime=config, state=tampered.value
            ),
        )
        self.assertEqual(last_terminal(second)["status"], "awaiting_approval")
        self.assertEqual(last_terminal(second)["error"]["code"], "pending_invalid")
        self.assertEqual(len(session.tool.calls), 0)


class FinalizeTests(unittest.TestCase):
    def test_failed_run_emits_feedback_text_and_error_log(self) -> None:
        session = FakeSession([RuntimeError("provider down")])
        outbox = run_turn(session, base_parameters(query="hi"))
        self.assertEqual(last_terminal(outbox)["status"], "failed")
        labels = log_labels(outbox)
        self.assertIn("Run error", labels)
        self.assertTrue(any(item.get("is_error") for item in outbox if item.get("type") == "log"))
        self.assertTrue(any("failed" in text.lower() for text in text_items(outbox)))

    def test_reasoning_streams_inside_think_tags(self) -> None:

        # A thinking chunk followed by a text chunk, both streamed as deltas.
        thinking_chunks = [
            {"delta": {"reasoning_content": "Let me think..."}},
            {"delta": {"message": {"content": "Answer!", "usage": {}}}},
        ]
        session = FakeSession([thinking_chunks])
        outbox = run_turn(session, base_parameters(query="hi"))
        texts = text_items(outbox)
        joined = "\n".join(texts)
        self.assertIn("<think>", joined)
        self.assertIn("Let me think...", joined)
        self.assertIn("</think>", joined)
        self.assertIn("Answer!", joined)
        # The think tag opens before the reasoning and closes before the answer.
        open_at = joined.index("<think>")
        close_at = joined.index("</think>")
        answer_at = joined.index("Answer!")
        self.assertLess(open_at, close_at)
        self.assertLess(close_at, answer_at)


if __name__ == "__main__":
    unittest.main()
