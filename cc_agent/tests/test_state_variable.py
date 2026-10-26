import unittest

from cc_agent.core.state_variable import (
    AGENT_STATE_PREFIX,
    AgentStateBundle,
    decode_agent_state,
    encode_agent_state,
    state_summary,
)


class AgentStateCodecTests(unittest.TestCase):
    def test_empty_agent_state_loads_empty_bundle(self):
        loaded = decode_agent_state("")

        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.bundle.revision, 0)
        self.assertEqual(loaded.bundle.history, {"messages": [], "summary": "", "version": 1})
        self.assertEqual(loaded.bundle.memory, [])
        self.assertEqual(loaded.bundle.tasks, [])
        self.assertEqual(loaded.bundle.permissions, {})

    def test_encoded_agent_state_round_trips_bundle(self):
        encoded = encode_agent_state(
            AgentStateBundle(
                revision=2,
                history={
                    "messages": [{"role": "user", "content": "from agent_state"}],
                    "summary": "prior summary",
                    "version": 1,
                },
                memory=[{"key": "project", "content": "cc-agent"}],
                tasks=[{"id": "task-1", "subject": "ship"}],
                permissions={"schema_version": 1, "allowed_tools": {"current_time": "conversation"}},
                last_execution_metadata={"finish_reason": "final"},
                active_skills=[{"name": "slides", "summary": "Created a deck"}],
            )
        )

        self.assertIsNone(encoded.error)
        self.assertTrue(encoded.value.startswith(AGENT_STATE_PREFIX))
        loaded = decode_agent_state(encoded.value)

        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.bundle.revision, 3)
        self.assertEqual(loaded.bundle.history["messages"][0]["content"], "from agent_state")
        self.assertEqual(loaded.bundle.history["summary"], "prior summary")
        self.assertEqual(loaded.bundle.memory[0]["key"], "project")
        self.assertEqual(loaded.bundle.tasks[0]["id"], "task-1")
        self.assertEqual(loaded.bundle.permissions["allowed_tools"]["current_time"], "conversation")
        self.assertEqual(loaded.bundle.active_skills[0]["name"], "slides")
        self.assertEqual(loaded.bundle.last_execution_metadata["finish_reason"], "final")

    def test_state_summary_is_read_only_subset(self):
        summary = state_summary(
            AgentStateBundle(
                revision=7,
                history={
                    "messages": [{"role": "user", "content": "hello"}],
                    "summary": "summary",
                    "version": 1,
                },
                memory=[{"key": "m1"}, {"key": "m2"}],
                tasks=[{"id": "t1"}],
                permissions={"allowed_tools": {"run_python": "conversation", "x": "once"}},
                active_skills=[{"name": "slides"}, {"id": "tables"}],
                last_execution_metadata={"finish_reason": "awaiting_user"},
            )
        )

        self.assertEqual(summary["revision"], 7)
        self.assertEqual(summary["history_message_count"], 1)
        self.assertEqual(summary["memory_count"], 2)
        self.assertEqual(summary["task_count"], 1)
        self.assertEqual(summary["permission_tool_count"], 2)
        self.assertEqual(summary["active_skill_names"], ["slides", "tables"])
        self.assertTrue(summary["awaiting_user"])

    def test_old_history_variable_prefix_is_rejected(self):
        loaded = decode_agent_state("ccagent:v3:gzip-base64:abc")

        self.assertIsNotNone(loaded.error)
        self.assertIn("unsupported prefix", loaded.error)

    def test_damaged_agent_state_reports_error(self):
        loaded = decode_agent_state("ccagent-state:v1:gzip-base64:not-base64")

        self.assertIsNone(loaded.record)
        self.assertIsNotNone(loaded.error)
        self.assertIn("Invalid agent_state", loaded.error)

    def test_oversized_agent_state_compacts_old_messages(self):
        messages = [
            {"role": "user", "content": f"old-{index}-" + ("x" * 2000)}
            for index in range(20)
        ]

        encoded = encode_agent_state(
            AgentStateBundle(
                revision=0,
                history={"messages": messages, "summary": "", "version": 1},
            ),
            max_encoded_bytes=2500,
        )
        loaded = decode_agent_state(encoded.value)

        self.assertIsNone(encoded.error)
        self.assertTrue(encoded.compacted)
        self.assertLessEqual(encoded.encoded_bytes, 2500)
        self.assertLess(len(loaded.bundle.history["messages"]), len(messages))
        self.assertTrue(loaded.bundle.history["summary"])

    def test_encode_supports_explicit_revision_increment_fields(self):
        encoded = encode_agent_state(
            previous_revision=2,
            history={
                "messages": [{"role": "user", "content": "from history variable"}],
                "summary": "prior summary",
                "version": 1,
            },
            memory=[{"key": "project", "content": "cc-agent"}],
            tasks=[{"id": "task-1", "subject": "ship"}],
            permissions={"schema_version": 1, "allowed_tools": {"current_time": "conversation"}},
            last_execution_metadata={"finish_reason": "final"},
            active_skills=[{"name": "slides", "summary": "Created a deck"}],
        )

        self.assertIsNone(encoded.error)
        loaded = decode_agent_state(encoded.value)

        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.bundle.revision, 3)
        self.assertEqual(loaded.bundle.history["messages"][0]["content"], "from history variable")


if __name__ == "__main__":
    unittest.main()
