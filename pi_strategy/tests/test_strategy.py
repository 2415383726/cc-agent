from __future__ import annotations

import json
import unittest

from _support import ROOT

from pi_strategy.config import parse_request

STRATEGY = ROOT / "strategies" / "pi_strategy_native.py"


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
        from strategies.pi_strategy_native import PiStrategyNativeStrategy

        return PiStrategyNativeStrategy._dispatch(self, message)


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        from strategies.pi_strategy_native import PiStrategyNativeStrategy

        self.strategy = PiStrategyNativeStrategy.__new__(PiStrategyNativeStrategy)
        self.fake = FakeStrategy()
        self.dispatch = lambda message: PiStrategyNativeStrategy._dispatch(self.strategy, message)

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
            {"type": "log", "label": "Run finished", "data": {"raw": {"status": "completed"}}}
        )
        self.assertEqual(log[0], "log")
        self.assertEqual(log[1], "Run finished")

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
        self.assertEqual(manifest["name"], "pi_strategy")
        self.assertEqual(manifest["meta"]["runner"]["language"], "python")
        self.assertEqual(manifest["meta"]["runner"]["version"], "3.12")
        self.assertEqual(manifest["meta"]["minimum_dify_version"], "1.5.0")
        self.assertEqual(set(manifest["meta"]["arch"]), {"amd64", "arm64"})

        strategy = yaml.safe_load(
            (ROOT / "strategies" / "pi_strategy_native.yaml").read_text(encoding="utf-8")
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
            "agent_state",
            "conversation_id",
            "user_id",
            "app_id",
        ):
            self.assertIn(required, names)
        # Tools execute directly: there is no approval, no structured
        # interaction parameter and no query-text decision keyword.
        self.assertNotIn("interaction", names)
        self.assertNotIn("approval_mode", names)
        self.assertEqual(
            set(strategy["output_schema"]["properties"]), {"agent_state", "answer", "json"}
        )
        provider = yaml.safe_load(
            (ROOT / "provider" / "pi_strategy.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(provider["strategies"], ["strategies/pi_strategy_native.yaml"])

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
                "agent_state": "pistrategy-state:v1:gzip-base64:abc",
                "conversation_id": "conv",
                "user_id": "user",
            }
        )
        self.assertEqual(request.query, "hello")
        self.assertEqual(request.files[0]["id"], "f1")
        self.assertEqual(request.conversation_id, "conv")
        self.assertEqual(request.runtime.max_model_requests, 24)

    def test_mcp_tools_exclude_is_a_real_list(self) -> None:
        from pi_strategy.config import RuntimeConfig

        config = RuntimeConfig.from_value({"mcp_tools_exclude": ["write", "delete"]})
        self.assertEqual(config.mcp_tools_exclude, ("write", "delete"))


def tearDownModule() -> None:
    """Release SDK log handlers while gevent's greenlets are still alive.

    Importing the real strategy pulls in the plugin SDK, which monkey-patches
    ``threading`` at import. At interpreter shutdown the logging module's
    handler weakref callbacks run after greenlets are finalized and print a
    spurious "greenlet is being finalized" traceback. The handlers are dropped
    here and the logging lock is replaced at exit with a plain no-op so the
    callbacks cannot touch a dead gevent lock.
    """
    import atexit
    import gc
    import logging

    for logger in (
        logging.getLogger(),
        logging.getLogger("pi_strategy"),
        logging.getLogger("pi_strategy.runtime"),
    ):
        logger.handlers.clear()
    logging.shutdown()
    gc.collect()

    def _neutralize_lock() -> None:
        class _NoLock:
            def acquire(self, *args, **kwargs):
                return True

            def release(self) -> None:
                pass

        logging._lock = _NoLock()  # noqa: SLF001 - test-process exit hygiene

    # Registered after the SDK's monkey patch, so this runs before gevent's
    # own exit hook (atexit is LIFO).
    atexit.register(_neutralize_lock)


if __name__ == "__main__":
    unittest.main()
