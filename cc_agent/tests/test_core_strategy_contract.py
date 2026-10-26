import unittest
import json
from pathlib import Path

import yaml

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.messages import AgentState
from cc_agent.core.profiles import AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE
from cc_agent.core.prompt_builder import PromptBuilder
from cc_agent.core.skill_catalog import build_skill_catalog
from cc_agent.strategies.base import _parameter_summary


ROOT = Path(__file__).resolve().parents[1]


class StrategyContractTests(unittest.TestCase):
    def test_strategy_yamls_expose_split_contract(self):
        expected = {
            "cc_agent_agui.yaml": ("cc_agent_agui", "CC Agent (AG-UI)"),
            "cc_agent_dify.yaml": ("cc_agent_dify", "CC Agent (Dify)"),
        }
        forbidden_public_parameters = {
            "capability_mode",
            "storage",
            "output_protocol",
            "skill_denylist",
            "user_skill_scripts_enabled",
            "skills",
            "memory",
            "tasks",
            "state_id",
            "history",
            "think_model",
            "flash_model",
            "multimodal_model",
            "state_reset",
            "emit_inline_state",
            "maximum_iterations",
            "max_observation_chars",
            "max_history_messages",
            "max_total_context_chars",
            "max_repeated_tool_calls",
            "max_consecutive_tool_errors",
            "tool_allowlist",
            "tool_denylist",
            "tool_confirmation_list",
            "workspace_enabled",
            "skills_enabled",
            "workspace_scope_id",
            "app_id",
            "user_id",
            "conversation_id",
            "skill_package_max_bytes",
            "minio_endpoint",
            "minio_bucket",
            "minio_access_key",
            "minio_secret_key",
        }

        for filename, (identity, label) in expected.items():
            text = (ROOT / "strategies" / filename).read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            by_name = {parameter["name"]: parameter for parameter in data["parameters"]}

            self.assertIn("history-messages", data.get("features") or [])
            self.assertEqual(data["identity"]["name"], identity)
            self.assertEqual(data["identity"]["label"]["en_US"], label)
            self.assertNotIn("Claws", text)
            self.assertTrue(forbidden_public_parameters.isdisjoint(by_name))
            for required in (
                "model",
                "max_total_context_tokens",
                "tools",
                "mcp_servers_config",
                "agent_state",
                "runtime_config",
                "deepseek_thinking_compat",
                "app_skills_yaml",
                "files",
            ):
                self.assertIn(required, by_name)
            self.assertEqual(by_name["deepseek_thinking_compat"]["default"], False)
            self.assertEqual(by_name["mcp_servers_config"]["type"], "string")
            self.assertFalse(by_name["mcp_servers_config"]["required"])
            self.assertTrue(by_name["mcp_servers_config"]["template"]["enabled"])
            self.assertEqual(by_name["max_total_context_tokens"]["type"], "number")
            self.assertEqual(by_name["max_total_context_tokens"]["default"], 131072)
            self.assertEqual(by_name["max_total_context_tokens"]["min"], 4096)

        provider = yaml.safe_load((ROOT / "provider" / "agent.yaml").read_text(encoding="utf-8"))
        self.assertEqual(
            provider["strategies"],
            ["strategies/cc_agent_agui.yaml", "strategies/cc_agent_dify.yaml"],
        )

    def test_strategy_profiles_fix_protocol_prompt_and_skill_surface(self):
        agui = AgentRunConfig.from_parameters(
            {"query": "hello", "output_protocol": False},
            strategy_profile=AGUI_STRATEGY_PROFILE,
        )
        dify = AgentRunConfig.from_parameters(
            {"query": "hello", "output_protocol": True},
            strategy_profile=DIFY_STRATEGY_PROFILE,
        )

        self.assertEqual(agui.output_protocol, "agui")
        self.assertTrue(agui.strategy_profile.structured_answers)
        self.assertEqual(dify.output_protocol, "dify_native")
        self.assertFalse(dify.strategy_profile.structured_answers)
        self.assertIn("# Structured answers", PromptBuilder(agui, AgentState()).system_prompt())
        self.assertNotIn("# Structured answers", PromptBuilder(dify, AgentState()).system_prompt())

        agui_names = {skill["name"] for skill in build_skill_catalog(config=agui).prompt_skills}
        dify_names = {skill["name"] for skill in build_skill_catalog(config=dify).prompt_skills}
        self.assertTrue({"answers-charts", "answers-ui"}.issubset(agui_names))
        self.assertTrue({"answers-charts", "answers-ui"}.isdisjoint(dify_names))
        self.assertNotIn("create-skill", agui_names)
        self.assertNotIn("create-skill", dify_names)
    def test_strategy_entry_modules_export_one_strategy_subclass(self):
        from cc_agent.strategies import base, cc_agent_agui, cc_agent_dify

        for module in (cc_agent_agui, cc_agent_dify):
            subclasses = [
                value
                for value in vars(module).values()
                if isinstance(value, type)
                and value is not base.BaseCCAgentStrategy
                and issubclass(value, base.BaseCCAgentStrategy)
            ]
            self.assertEqual(len(subclasses), 1, module.__name__)
    def test_agent_run_config_defaults_to_dify_state(self):
        config = AgentRunConfig.from_parameters({"query": "hello"})

        self.assertFalse(hasattr(config, "capability_mode"))
        self.assertFalse(hasattr(config, "storage"))
        self.assertEqual(config.agent_state_variable, "")
        self.assertEqual(config.max_total_context_tokens, 131072)


    def test_removed_storage_parameters_are_ignored_without_parsing(self):
        config = AgentRunConfig.from_parameters({
            "query": "hello",
            "capability_mode": "minio",
            "storage": "invalid JSON that must not be parsed",
            "agent_state": "previous-state",
        })
        self.assertEqual(config.agent_state_variable, "previous-state")
        self.assertFalse(hasattr(config, "capability_mode"))
        self.assertFalse(hasattr(config, "storage"))

    def test_agent_run_config_reads_runtime_config_json(self):
        config = AgentRunConfig.from_parameters(
            {
                "query": "hello",
                "runtime_config": json.dumps(
                    {
                        "maximum_iterations": 5,
                        "max_observation_chars": 1234,
                        "max_history_messages": 9,
                        "max_total_context_chars": 4567,
                        "max_repeated_tool_calls": 2,
                        "max_consecutive_tool_errors": 4,
                        "state_reset": True,
                        "unknown": "ignored",
                    }
                ),
            }
        )

        self.assertEqual(config.maximum_iterations, 5)
        self.assertEqual(config.max_observation_chars, 1234)
        self.assertEqual(config.max_history_messages, 9)
        self.assertEqual(config.max_total_context_chars, 4567)
        self.assertEqual(config.max_total_context_tokens, 4567)
        self.assertEqual(config.resolved_context_limit, 4567)
        self.assertEqual(config.max_repeated_tool_calls, 2)
        self.assertEqual(config.max_consecutive_tool_errors, 4)
        self.assertTrue(config.state_reset)
        self.assertEqual(config.runtime_config["state_reset"], True)
        self.assertNotIn("unknown", config.runtime_config)

    def test_agent_run_config_rejects_invalid_runtime_config_json(self):
        with self.assertRaises(ValueError):
            AgentRunConfig.from_parameters({"query": "hello", "runtime_config": "{bad"})

    def test_agent_run_config_ignores_removed_flat_runtime_params(self):
        config = AgentRunConfig.from_parameters(
            {
                "query": "hello",
                "maximum_iterations": 99,
                "max_observation_chars": 111,
                "max_history_messages": 222,
                "max_total_context_chars": 333,
                "max_repeated_tool_calls": 44,
                "max_consecutive_tool_errors": 55,
                "state_reset": True,
                "emit_inline_state": False,
                "tool_allowlist": "A",
                "tool_denylist": "B",
                "tool_confirmation_list": "C",
                "skill_package_max_bytes": 1,
            }
        )

        self.assertEqual(config.maximum_iterations, 8)
        self.assertEqual(config.max_observation_chars, 8000)
        self.assertEqual(config.max_history_messages, 40)
        self.assertEqual(config.max_total_context_chars, 131072)
        self.assertEqual(config.max_total_context_tokens, 131072)
        self.assertEqual(config.max_repeated_tool_calls, 3)
        self.assertEqual(config.max_consecutive_tool_errors, 3)
        self.assertFalse(config.state_reset)
        self.assertTrue(config.emit_inline_state)
        self.assertIsNone(config.tool_allowlist)
        self.assertIsNone(config.tool_denylist)
        self.assertIsNone(config.tool_confirmation_list)
        self.assertFalse(hasattr(config, "skill_package_max_bytes"))

    def test_node_context_limit_overrides_runtime_and_model_metadata(self):
        model = type("Model", (), {"entity": type("Entity", (), {"context_size": 32000})()})()
        config = AgentRunConfig.from_parameters(
            {
                "query": "hello",
                "model": model,
                "max_total_context_tokens": 200000,
                "runtime_config": json.dumps(
                    {"max_total_context_tokens": 64000, "max_total_context_chars": 48000}
                ),
            }
        )

        self.assertEqual(config.max_total_context_tokens, 200000)
        self.assertEqual(config.resolved_context_limit, 200000)

    def test_input_context_limit_is_used_when_top_level_is_missing(self):
        config = AgentRunConfig.from_parameters(
            {"query": "hello", "inputs": {"max_total_context_tokens": 96000}}
        )

        self.assertEqual(config.max_total_context_tokens, 96000)

    def test_agent_run_config_ignores_inline_state_fields(self):
        config = AgentRunConfig.from_parameters(
            {
                "query": "hello",
                "skills": [{"name": "ignored"}],
                "memory": [{"key": "ignored"}],
                "tasks": [{"id": "ignored"}],
            }
        )

        self.assertFalse(hasattr(config, "skills"))
        self.assertFalse(hasattr(config, "memory"))
        self.assertFalse(hasattr(config, "tasks"))
        self.assertEqual(config.query, "hello")

    def test_parameter_summary_redacts_storage_secrets(self):
        storage = {
            "provider": "minio",
            "endpoint": "http://localhost:19000",
            "bucket": "cc-agent",
            "access_key": "AKIA_TEST_VALUE",
            "secret_key": "MINIO_SECRET_VALUE",
            "scope": {"app_id": "app-1", "user_id": "user-1", "conversation_id": "conv-1"},
        }
        summary = _parameter_summary(
            {
                "query": "hello",
                "capability_mode": "minio",
                "agent_state": "ccagent-state:v1:gzip-base64:SECRET",
                "files": [{"name": "a.txt"}],
                "storage": json.dumps(storage),
            }
        )

        rendered = str(summary)
        self.assertEqual(summary["files_count"], 1)
        self.assertNotIn("capability_mode", summary)
        self.assertTrue(summary["agent_state_present"])
        self.assertNotIn("storage_summary", summary)
        self.assertNotIn("storage_present", summary)
        self.assertNotIn("AKIA_TEST_VALUE", rendered)
        self.assertNotIn("MINIO_SECRET_VALUE", rendered)
        self.assertNotIn("SECRET", rendered)
        self.assertNotIn("localhost:19000", rendered)


if __name__ == "__main__":
    unittest.main()
