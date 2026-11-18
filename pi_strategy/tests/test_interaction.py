from __future__ import annotations

import unittest

from _support import ROOT  # noqa: F401

from pi_strategy.config import RuntimeConfig
from pi_strategy.errors import PendingError
from pi_strategy.interaction import (
    approval_required,
    create_approval_pending,
    parse_approval_reply,
    render_approval_text,
    validate_approval_decision,
)


class ApprovalKeywordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pending = create_approval_pending(
            tool_call_id="c1",
            tool_name="write",
            arguments={"value": 1},
            source="dify",
            annotations={},
            run_id="run",
        )

    def test_approval_text_shows_keywords(self) -> None:
        text = render_approval_text(self.pending)
        self.assertIn("write", text)
        self.assertIn("同意", text)
        self.assertIn("当前会话始终允许", text)
        self.assertIn("拒绝", text)

    def test_keyword_table_matches_cc_agent_native(self) -> None:
        cases = {
            "同意": ("approve", "once"),
            "允许一次": ("approve", "once"),
            "允许": ("approve", "once"),
            "yes": ("approve", "once"),
            "当前会话始终允许": ("approve", "session"),
            "始终允许": ("approve", "session"),
            "always allow": ("approve", "session"),
            "拒绝": ("reject", "once"),
            "取消": ("reject", "once"),
            "no": ("reject", "once"),
        }
        for reply, (decision, scope) in cases.items():
            parsed = parse_approval_reply(self.pending, reply)
            self.assertEqual(parsed["decision"], decision, reply)
            self.assertEqual(parsed["scope"], scope, reply)

    def test_unrecognized_reply_is_rejected(self) -> None:
        with self.assertRaises(PendingError):
            parse_approval_reply(self.pending, "随便说说")
        with self.assertRaises(PendingError):
            parse_approval_reply(self.pending, "")

    def test_quote_wrapped_reply_is_unwrapped(self) -> None:
        """Dify 1.5 wraps template-resolved queries in literal quotes."""
        parsed = parse_approval_reply(self.pending, '"同意"')
        self.assertEqual(parsed["decision"], "approve")
        self.assertEqual(parsed["scope"], "once")

    def test_parsed_reply_feeds_validation(self) -> None:
        decision = validate_approval_decision(
            self.pending, parse_approval_reply(self.pending, "同意")
        )
        self.assertEqual(decision["decision"], "approve")
        self.assertEqual(decision["scope"], "once")


class ApprovalPolicyTests(unittest.TestCase):
    def test_configured_and_session_grants(self) -> None:
        config = RuntimeConfig.from_value(
            {"approval_mode": "configured", "approval_tools": ["write"]}
        )
        self.assertTrue(approval_required("write", "dify", {}, config, []))
        self.assertFalse(approval_required("read", "dify", {}, config, []))
        grant = [{"tool": "write", "scope": "session", "source": "dify"}]
        self.assertFalse(approval_required("write", "dify", {}, config, grant))
        self.assertTrue(approval_required("write", "mcp", {}, config, grant))

    def test_mcp_destructive_policy(self) -> None:
        config = RuntimeConfig.from_value({"approval_mode": "mcp"})
        self.assertTrue(approval_required("delete", "mcp", {}, config, []))
        self.assertFalse(
            approval_required(
                "search", "mcp", {"readOnlyHint": True, "destructiveHint": False}, config, []
            )
        )
        self.assertFalse(approval_required("delete", "dify", {}, config, []))

    def test_expired_approval_is_rejected(self) -> None:
        pending = create_approval_pending(
            tool_call_id="c1",
            tool_name="write",
            arguments={},
            source="dify",
            annotations={},
            run_id="run",
            timeout_seconds=0.001,
        )
        import time

        time.sleep(0.01)
        with self.assertRaises(PendingError):
            validate_approval_decision(
                pending, {"type": "approval", "pending_id": pending["id"], "decision": "approve"}
            )

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
        with self.assertRaises(PendingError):
            validate_approval_decision(
                pending, {"type": "approval", "pending_id": "other", "decision": "approve"}
            )


if __name__ == "__main__":
    unittest.main()
