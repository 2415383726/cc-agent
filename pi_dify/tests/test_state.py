from __future__ import annotations

import json
import unittest

from _support import ROOT  # noqa: F401 - ensures the package root is on sys.path

from pi_agent.errors import StateError
from pi_agent.state import (
    STATE_PREFIX,
    PiState,
    decode_state,
    encode_state,
    sanitize_entries,
    validate_state,
)


def message_entry(entry_id: str, parent: str | None, message: dict) -> dict:
    return {
        "type": "message",
        "id": entry_id,
        "parentId": parent,
        "timestamp": "2026-10-29T00:00:00Z",
        "message": message,
    }


def user(entry_id: str, parent: str | None, text: str) -> dict:
    return message_entry(entry_id, parent, {"role": "user", "content": text, "timestamp": 1})


def assistant(
    entry_id: str, parent: str | None, text: str, calls: list[dict] | None = None
) -> dict:
    blocks = [{"type": "text", "text": text}]
    blocks.extend(calls or [])
    return message_entry(
        entry_id,
        parent,
        {
            "role": "assistant",
            "content": blocks,
            "api": "test",
            "provider": "test",
            "model": "test",
            "usage": {},
            "stopReason": "toolUse" if calls else "stop",
            "timestamp": 2,
        },
    )


def tool_result(entry_id: str, parent: str | None, call_id: str, text: str) -> dict:
    return message_entry(
        entry_id,
        parent,
        {
            "role": "toolResult",
            "toolCallId": call_id,
            "toolName": "echo",
            "content": [{"type": "text", "text": text}],
            "isError": False,
            "timestamp": 3,
        },
    )


class StateCodecTests(unittest.TestCase):
    def test_round_trip_preserves_leaf_and_revision(self) -> None:
        state = PiState.fresh("conv")
        state.entries = [user("u1", None, "hello"), assistant("a1", "u1", "hi")]
        state.leaf_id = "a1"
        result = encode_state(state, max_encoded_bytes=190_000)
        self.assertTrue(result.persisted)
        self.assertTrue(result.value.startswith(STATE_PREFIX))
        loaded = decode_state(result.value)
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.state.revision, 0)
        self.assertEqual(loaded.state.leaf_id, "a1")
        self.assertEqual(len(loaded.state.entries), 2)

    def test_unknown_prefix_and_corruption_are_rejected(self) -> None:
        self.assertIn("prefix", decode_state("ccagent-state:v1:gzip-base64:abc").error)
        self.assertIn("base64", decode_state(STATE_PREFIX + "!!").error)
        self.assertIn("gzip", decode_state(STATE_PREFIX + "aGVsbG8=").error)

    def test_unsupported_schema_is_rejected(self) -> None:
        import base64
        import gzip

        payload = json.dumps({"schema_version": 99, "entries": []}).encode()
        value = STATE_PREFIX + base64.b64encode(gzip.compress(payload)).decode()
        self.assertIn("schema", decode_state(value).error)

    def test_dangling_parent_and_unpaired_call_are_rejected(self) -> None:
        state = PiState.fresh("conv")
        state.entries = [user("u1", "missing", "hello")]
        state.leaf_id = "u1"
        result = encode_state(state)
        self.assertTrue(result.persisted)
        self.assertIsNone(decode_state(result.value).error)
        state.entries = [
            user("u1", None, "hello"),
            assistant(
                "a1", "u1", "", [{"type": "toolCall", "id": "c1", "name": "echo", "arguments": {}}]
            ),
        ]
        state.leaf_id = "a1"
        with self.assertRaises(StateError):
            validate_state(state)

    def test_missing_tool_result_is_synthesized_on_save(self) -> None:
        state = PiState.fresh("conv")
        state.entries = [
            user("u1", None, "hello"),
            assistant(
                "a1", "u1", "", [{"type": "toolCall", "id": "c1", "name": "echo", "arguments": {}}]
            ),
        ]
        state.leaf_id = "a1"
        result = encode_state(state)
        self.assertTrue(result.persisted)
        loaded = decode_state(result.value)
        self.assertIsNone(loaded.error)
        results = [
            entry
            for entry in loaded.state.entries
            if entry.get("type") == "message" and entry["message"].get("role") == "toolResult"
        ]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message"]["details"]["execution_outcome"], "unknown")

    def test_failed_assistant_is_not_persisted(self) -> None:
        state = PiState.fresh("conv")
        failed = {
            "role": "assistant",
            "content": [{"type": "text", "text": ""}],
            "stopReason": "error",
            "errorMessage": "pi_error:provider_failed",
            "timestamp": 2,
        }
        state.entries = [user("u1", None, "hello"), message_entry("a1", "u1", failed)]
        state.leaf_id = "a1"
        result = encode_state(state)
        loaded = decode_state(result.value)
        self.assertIsNone(loaded.error)
        self.assertEqual(len(loaded.state.entries), 1)
        self.assertEqual(loaded.state.entries[0]["id"], "u1")

    def test_storage_trimming_keeps_pending_group_and_valid_leaf(self) -> None:
        state = PiState.fresh("conv")
        entries = []
        parent = None
        import os

        for index in range(12):
            uid = f"u{index}"
            aid = f"a{index}"
            entries.append(user(uid, parent, os.urandom(400).hex()))
            entries.append(assistant(aid, uid, os.urandom(400).hex()))
            parent = aid
        state.entries = entries
        state.leaf_id = parent
        state.pending = {"kind": "ask_user", "id": "q", "tool_call_id": "last"}
        result = encode_state(state, max_encoded_bytes=7_000, target_encoded_bytes=5_000)
        self.assertTrue(result.persisted)
        self.assertTrue(result.compacted)
        self.assertLessEqual(result.encoded_bytes, 7_000)
        loaded = decode_state(result.value)
        self.assertIsNone(loaded.error)
        self.assertTrue(any(entry["type"] == "compaction" for entry in loaded.state.entries))
        self.assertEqual(loaded.state.leaf_id, parent)

    def test_save_failure_does_not_return_a_snapshot(self) -> None:
        import os

        state = PiState.fresh("conv")
        state.entries = [user("u1", None, os.urandom(40_000).hex())]
        state.leaf_id = "u1"
        result = encode_state(state, max_encoded_bytes=1_000)
        self.assertFalse(result.persisted)
        self.assertEqual(result.value, "")
        self.assertEqual(result.error, "state_too_large")

    def test_sanitize_rebuilds_parent_chain(self) -> None:
        entries = [user("u1", "ghost", "hello"), assistant("a1", "u1", "hi")]
        cleaned = sanitize_entries(entries, "a1", None)
        self.assertIsNone(cleaned[0]["parentId"])
        self.assertEqual(cleaned[1]["parentId"], "u1")


if __name__ == "__main__":
    unittest.main()
