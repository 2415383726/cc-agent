import unittest

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.messages import AgentRunResult
from cc_agent.core.protocol_renderer import AgentEvent, ProtocolRenderer
from cc_agent.core.state_backend import DifyStateBackend
from cc_agent.core.state_variable import decode_agent_state
from cc_agent.core.tool_catalog import ToolCatalog


class ArchitecturePortTests(unittest.TestCase):

    def test_state_backend_commits_dify_agent_state(self):
        config = AgentRunConfig.from_parameters({"query": "hello"})
        result = AgentRunResult(
            answer="done",
            history=[{"role": "user", "content": "hello"}],
            tasks=[{"id": "1", "subject": "ship task state", "status": "pending"}],
            execution_metadata={"finish_reason": "final"},
        )

        DifyStateBackend(config, state_id="conv-1").commit(result, previous_revision=0)
        loaded = decode_agent_state(result.encoded_agent_state)

        self.assertTrue(result.encoded_agent_state.startswith("ccagent-state:v1:gzip-base64:"))
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.bundle.tasks[0]["status"], "pending")
        self.assertEqual(result.state_ref["backend"], "conversation_variable")
        self.assertEqual(result.state_summary["last_finish_reason"], "final")

    def test_tool_catalog_exposes_dify_tools_and_protocol_specific_interrupt(self):
        dify_only = ToolCatalog.create()
        dify_native = ToolCatalog.create(output_protocol="dify_native")

        self.assertNotIn("run_python", dify_only.names())
        self.assertNotIn("SkillInstall", dify_only.names())
        self.assertIn("Skill", dify_only.names())
        self.assertIn("UserPrompt", dify_only.names())
        self.assertNotIn("AskUserQuestion", dify_only.names())
        self.assertNotIn("UserPrompt", dify_native.names())
        self.assertNotIn("AskUserQuestion", dify_native.names())

    def test_removed_internal_tools_can_only_be_provided_externally(self):
        from cc_agent.core.internal_tools import InternalToolExecutor
        from cc_agent.core.messages import AgentState, ToolCall
        from cc_agent.core.tool_adapter import ToolAdapter

        retired = {
            "list_files",
            "inspect_file",
            "read_file",
            "write_file",
            "delete_file",
            "run_python",
            "SkillRunScript",
            "SkillInstall",
            "SkillRemove",
        }
        state = AgentState()
        catalog = ToolCatalog.create()
        self.assertTrue(retired.isdisjoint(catalog.names()))
        for name in retired:
            with self.subTest(name=name):
                result = InternalToolExecutor(state).execute(name, {}, "removed-call")
                self.assertTrue(result.is_error)
                self.assertEqual(result.tool_call_id, "removed-call")
                missing = ToolAdapter(catalog, state).execute(ToolCall("missing-call", name, {}))
                self.assertTrue(missing.is_error)
                self.assertEqual(missing.tool_call_id, "missing-call")

        calls = []
        from types import SimpleNamespace

        session = SimpleNamespace(
            tool=SimpleNamespace(invoke=lambda **kwargs: calls.append(kwargs) or [])
        )
        catalog = ToolCatalog.create(
            external_tools=[{"name": "read_file", "provider": "files"}],
            external_prompt_tools=[{"name": "read_file", "parameters": {}}],
        )
        result = ToolAdapter(catalog, state, session=session).execute(
            ToolCall("external-call", "read_file", {"id": "1"})
        )
        self.assertFalse(result.is_error)
        self.assertEqual(catalog.resolve("read_file").kind, "external")
        self.assertEqual(calls[0]["tool_name"], "read_file")

    def test_protocol_renderer_uses_immutable_agent_event_data(self):
        event = AgentEvent(
            "activity", {"activity_type": "cc_agent.uploaded_files", "content": {"files": []}}
        )
        renderer = ProtocolRenderer("agui", thread_id="conv-1", run_id="run-1")

        rendered = renderer.render(event)

        self.assertEqual(rendered[0]["type"], "ACTIVITY_SNAPSHOT")
        self.assertEqual(rendered[0]["activityType"], "cc_agent.uploaded_files")
        self.assertEqual(event.payload["content"], {"files": []})


if __name__ == "__main__":
    unittest.main()
