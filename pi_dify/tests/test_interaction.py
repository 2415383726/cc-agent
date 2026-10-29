from __future__ import annotations

import time
import unittest

from _support import ROOT  # noqa: F401

from pi_agent.config import RuntimeConfig
from pi_agent.errors import PendingError
from pi_agent.interaction import (
    approval_required,
    build_questionnaire,
    create_approval_pending,
    create_question_pending,
    validate_approval_decision,
    validate_question_answer,
)


class QuestionnaireTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = RuntimeConfig()
        self.questionnaire = build_questionnaire(
            {
                "title": "Details",
                "questions": [
                    {
                        "id": "color",
                        "question": "Pick one",
                        "type": "single",
                        "options": [{"id": "red", "label": "Red"}, {"id": "blue", "label": "Blue"}],
                    },
                    {
                        "id": "tags",
                        "question": "Pick many",
                        "type": "multi",
                        "options": ["A", "B", "C"],
                        "min_selections": 1,
                        "max_selections": 2,
                    },
                    {"id": "notes", "question": "Notes", "type": "text", "max_length": 20},
                ],
            },
            self.config,
        )
        self.pending = create_question_pending(
            self.questionnaire, tool_call_id="call", run_id="run", timeout_seconds=0
        )

    def test_answer_normalizes_ids_and_labels(self) -> None:
        result = validate_question_answer(
            self.pending,
            {
                "type": "ask_user",
                "pending_id": self.questionnaire["id"],
                "answers": {"color": "Blue", "tags": ["A", "B"], "notes": "hello"},
            },
        )
        self.assertEqual(result["answers"]["color"], "blue")
        self.assertEqual(result["answers"]["tags"], ["o1", "o2"])

    def test_missing_required_and_invalid_options_are_rejected(self) -> None:
        base = {"type": "ask_user", "pending_id": self.questionnaire["id"]}
        with self.assertRaises(PendingError):
            validate_question_answer(self.pending, {**base, "answers": {"tags": ["A"]}})
        with self.assertRaises(PendingError):
            validate_question_answer(
                self.pending, {**base, "answers": {"color": "green", "tags": ["A"]}}
            )
        with self.assertRaises(PendingError):
            validate_question_answer(
                self.pending, {**base, "answers": {"color": "red", "tags": ["A", "B", "C"]}}
            )

    def test_invalid_and_expired_pending_are_rejected(self) -> None:
        with self.assertRaises(PendingError):
            validate_question_answer(
                self.pending, {"type": "ask_user", "pending_id": "other", "answers": {}}
            )
        expired = {**self.pending, "expires_at": time.time() - 1}
        with self.assertRaises(PendingError):
            validate_question_answer(
                expired,
                {
                    "type": "ask_user",
                    "pending_id": self.questionnaire["id"],
                    "answers": {"color": "red", "tags": ["A"]},
                },
            )

    def test_oversized_questionnaire_is_rejected(self) -> None:
        with self.assertRaises(PendingError):
            build_questionnaire(
                {"questions": [{"question": "x", "type": "text"}] * 20}, self.config
            )


class ApprovalPolicyTests(unittest.TestCase):
    def test_configured_and_session_grants(self) -> None:
        config = RuntimeConfig.from_value(
            {"approval_mode": "configured", "approval_tools": ["write"]}
        )
        self.assertTrue(approval_required("write", "dify", {}, config, []))
        self.assertFalse(approval_required("read", "dify", {}, config, []))
        grant = [{"tool": "write", "scope": "session"}]
        self.assertFalse(approval_required("write", "dify", {}, config, grant))

    def test_mcp_destructive_policy(self) -> None:
        config = RuntimeConfig.from_value({"approval_mode": "mcp"})
        self.assertTrue(approval_required("delete", "mcp", {}, config, []))
        self.assertFalse(
            approval_required(
                "search", "mcp", {"readOnlyHint": True, "destructiveHint": False}, config, []
            )
        )
        self.assertFalse(approval_required("delete", "dify", {}, config, []))

    def test_decision_validation(self) -> None:
        pending = create_approval_pending(
            tool_call_id="c1",
            tool_name="write",
            arguments={"value": 1},
            source="dify",
            annotations={},
            run_id="run",
        )
        decision = validate_approval_decision(
            pending,
            {
                "type": "approval",
                "pending_id": pending["id"],
                "decision": "approve",
                "scope": "session",
            },
        )
        self.assertEqual(decision["scope"], "session")
        with self.assertRaises(PendingError):
            validate_approval_decision(
                pending, {"type": "approval", "pending_id": pending["id"], "decision": "maybe"}
            )
        with self.assertRaises(PendingError):
            validate_approval_decision(pending, {"type": "ask_user", "pending_id": pending["id"]})


if __name__ == "__main__":
    unittest.main()
