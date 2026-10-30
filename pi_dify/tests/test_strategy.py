from __future__ import annotations

import json
import unittest

from _support import ROOT

from pi_agent.config import parse_request

STRATEGY = ROOT / "strategies" / "pi_agent_dify.py"


class FakeStrategy:
    def create_text_message(self, content):
        return ("text", content)

    def create_variable_message(self, name, value):
        return ("variable", name, value)

    def create_blob_message(self, blob, meta):
        return ("blob", blob, meta)

    def create_json_message(self, payload):
        return ("json", payload)

    def create_log_message(self, label, data, status):
        return ("log", label, data, status)

    def _log(self, label, data, *, is_error=False):
        return ("log", label, data, is_error)

    def _dispatch(self, message):
        from strategies.pi_agent_dify import PiAgentStrategy

        return PiAgentStrategy._dispatch(self, message)


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        from strategies.pi_agent_dify import PiAgentStrategy

        self.strategy = PiAgentStrategy.__new__(PiAgentStrategy)
        self.fake = FakeStrategy()
        self.dispatch = lambda message: PiAgentStrategy._dispatch(self.strategy, message)

    def test_maps_outbox_messages(self) -> None:
        # Bind the fake SDK methods onto the strategy instance for this contract test.
        for name in (
            "create_text_message",
            "create_variable_message",
            "create_blob_message",
            "create_json_message",
            "create_log_message",
            "_log",
        ):
            setattr(self.strategy, name, getattr(self.fake, name))
        self.assertEqual(self.dispatch({"type": "text", "content": "hi"}), ("text", "hi"))
        self.assertEqual(
            self.dispatch({"type": "state", "name": "agent_state", "value": "x"}),
            ("variable", "agent_state", "x"),
        )
        self.assertEqual(
            self.dispatch({"type": "blob", "blob": b"data", "meta": {"filename": "a"}}),
            (
                "blob",
                b"data",
                {"filename": "a", "output_filename": "a", "mime_type": "application/octet-stream"},
            ),
        )
        log = self.dispatch(
            {"type": "log", "label": "Pi event", "data": {"piagent": {"type": "run.start"}}}
        )
        self.assertEqual(log[0], "log")
        self.assertEqual(log[1], "Pi event")

    def test_unknown_or_bad_blob_is_safe(self) -> None:
        for name in ("create_log_message", "_log"):
            setattr(self.strategy, name, getattr(self.fake, name))
        result = self.dispatch({"type": "blob", "blob": "text", "meta": {}})
        self.assertEqual(result[0], "log")
        self.assertTrue(result[-1])
        result = self.dispatch({"type": "mystery"})
        self.assertEqual(result[0], "log")


class ConfigurationContractTests(unittest.TestCase):
    def test_manifest_and_strategy_schema(self) -> None:
        import yaml

        manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "pi_dify")
        self.assertEqual(manifest["meta"]["runner"]["language"], "python")
        self.assertEqual(manifest["meta"]["runner"]["version"], "3.12")
        self.assertEqual(manifest["meta"]["minimum_dify_version"], "1.7.0")
        self.assertEqual(set(manifest["meta"]["arch"]), {"amd64", "arm64"})

        strategy = yaml.safe_load(
            (ROOT / "strategies" / "pi_agent_dify.yaml").read_text(encoding="utf-8")
        )
        names = {parameter["name"] for parameter in strategy["parameters"]}
        for required in (
            "model",
            "query",
            "tools",
            "files",
            "instruction",
            "app_skills_yaml",
            "mcp_servers_config",
            "runtime_config",
            "interaction",
            "agent_state",
            "conversation_id",
            "user_id",
            "app_id",
        ):
            self.assertIn(required, names)
        provider = yaml.safe_load((ROOT / "provider" / "pi_agent.yaml").read_text(encoding="utf-8"))
        self.assertEqual(provider["strategies"], ["strategies/pi_agent_dify.yaml"])

    def test_parameters_are_explicitly_mapped(self) -> None:
        request = parse_request(
            {
                "model": {"model": "m", "provider": "p", "mode": "chat"},
                "query": "hello",
                "tools": [{"name": "echo"}],
                "files": json.dumps([{"id": "f1", "name": "a.txt"}]),
                "instruction": "be brief",
                "app_skills_yaml": "skills: []",
                "mcp_servers_config": "{}",
                "agent_state": "piagent-state:v1:gzip-base64:abc",
                "interaction": json.dumps({"type": "cancel", "pending_id": "p"}),
                "conversation_id": "conv",
                "user_id": "user",
            }
        )
        self.assertEqual(request.query, "hello")
        self.assertEqual(request.files[0]["id"], "f1")
        self.assertEqual(request.interaction["type"], "cancel")
        self.assertEqual(request.conversation_id, "conv")
        self.assertEqual(request.runtime.max_model_requests, 24)

    def test_mcp_tools_exclude_is_a_real_list(self) -> None:
        from pi_agent.config import RuntimeConfig

        config = RuntimeConfig.from_value({"mcp_tools_exclude": ["write", "delete"]})
        self.assertEqual(config.mcp_tools_exclude, ("write", "delete"))


if __name__ == "__main__":
    unittest.main()
