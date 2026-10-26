import json
import unittest

from cc_agent.core.config import AgentRunConfig, StorageSettings
from cc_agent.core.messages import AgentRunResult
from cc_agent.core.protocol_renderer import AgentEvent, ProtocolRenderer
from cc_agent.core.skill_catalog import SKILL_MANAGEMENT_REQUIRES_MINIO, build_skill_catalog
from cc_agent.core.state_backend import DifyStateBackend
from cc_agent.core.state_variable import decode_agent_state
from cc_agent.core.tool_catalog import ToolCatalog


class ArchitecturePortTests(unittest.TestCase):
    def test_storage_settings_require_minio_scope_without_workspace_scope_id(self):
        settings = StorageSettings.from_value(
            json.dumps(
                {
                    "provider": "minio",
                    "endpoint": "minio:9000",
                    "bucket": "cc-agent",
                    "access_key": "access",
                    "secret_key": "secret",
                    "scope": {
                        "app_id": "app-1",
                        "user_id": "user-1",
                        "conversation_id": "conv-1",
                    },
                }
            )
        )

        self.assertEqual(settings.missing_required(), [])
        self.assertEqual(settings.scope.app_id, "app-1")
        self.assertEqual(settings.scope.user_id, "user-1")
        self.assertEqual(settings.scope.conversation_id, "conv-1")
        self.assertFalse(hasattr(settings.scope, "workspace_scope_id"))
        self.assertNotIn("secret_key\": \"secret", json.dumps(settings.redacted_summary()))

    def test_state_backend_commits_dify_agent_state(self):
        config = AgentRunConfig.from_parameters({"query": "hello"})
        result = AgentRunResult(
            answer="done",
            history=[{"role": "user", "content": "hello"}],
            memory=[],
            tasks=[{"id": "1", "subject": "ship task state", "status": "pending"}],
            execution_metadata={"finish_reason": "final"},
        )

        DifyStateBackend(config, state_id="conv-1").commit(result, expected_revision=0)
        loaded = decode_agent_state(result.encoded_agent_state)

        self.assertTrue(result.encoded_agent_state.startswith("ccagent-state:v1:gzip-base64:"))
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.bundle.tasks[0]["status"], "pending")
        self.assertEqual(result.state_ref["backend"], "conversation_variable")
        self.assertEqual(result.state_summary["last_finish_reason"], "final")

    def test_tool_catalog_filters_internal_tools_by_profile(self):
        dify_only = ToolCatalog.create(capability_mode="dify_only")
        minio = ToolCatalog.create(capability_mode="minio")
        dify_native = ToolCatalog.create(capability_mode="dify_only", output_protocol="dify_native")

        self.assertNotIn("run_python", dify_only.names())
        self.assertNotIn("SkillInstall", dify_only.names())
        self.assertIn("Skill", dify_only.names())
        self.assertIn("UserPrompt", dify_only.names())
        self.assertNotIn("AskUserQuestion", dify_only.names())
        self.assertIn("run_python", minio.names())
        self.assertIn("SkillInstall", minio.names())
        self.assertNotIn("UserPrompt", dify_native.names())
        self.assertNotIn("AskUserQuestion", dify_native.names())

    def test_dify_only_skill_catalog_rejects_user_management(self):
        catalog = build_skill_catalog(config=AgentRunConfig.from_parameters({"query": "hello"}))

        with self.assertRaisesRegex(NotImplementedError, SKILL_MANAGEMENT_REQUIRES_MINIO):
            catalog.install_user_skill(name="demo")
        with self.assertRaisesRegex(NotImplementedError, SKILL_MANAGEMENT_REQUIRES_MINIO):
            catalog.remove_user_skill(name="demo")

    def test_skill_catalog_excludes_denied_prompt_and_local_skills(self):
        config = AgentRunConfig.from_parameters(
            {"query": "hello", "skill_denylist": "ANSWERS-CHARTS;status"}
        )

        catalog = build_skill_catalog(config=config)

        self.assertNotIn("answers-charts", {skill["name"] for skill in catalog.prompt_skills})
        self.assertNotIn("status", {skill["name"] for skill in catalog.local_skills})
        self.assertIn("help", {skill["name"] for skill in catalog.local_skills})

    def test_protocol_renderer_uses_immutable_agent_event_data(self):
        event = AgentEvent("activity", {"activity_type": "cc_agent.workspace", "content": {"files": []}})
        renderer = ProtocolRenderer("agui", thread_id="conv-1", run_id="run-1")

        rendered = renderer.render(event)

        self.assertEqual(rendered[0]["type"], "ACTIVITY_SNAPSHOT")
        self.assertEqual(rendered[0]["activityType"], "cc_agent.workspace")
        self.assertEqual(event.payload["content"], {"files": []})


if __name__ == "__main__":
    unittest.main()
