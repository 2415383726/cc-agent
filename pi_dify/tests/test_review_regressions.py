"""Regression cases at the SDK, runtime and saved-state boundaries."""

from __future__ import annotations

import asyncio
import random
import threading
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

from _support import (
    FakeSession,
    base_parameters,
    display_events,
    last_state,
    last_terminal,
    run_turn,
    text_chunks,
    tool_chunks,
)
from pi_agent_harness.session.session import Session
from test_state import assistant, user
from test_stream import build_stream, consume

from pi_agent.config import RuntimeConfig
from pi_agent.mcp import McpRuntime, McpServer, McpTool
from pi_agent.runtime import PiAgentRuntime
from pi_agent.state import MAX_PAYLOAD_BYTES, PiState, build_storage, decode_state, encode_state


class ReviewRegressionTests(unittest.TestCase):
    def test_sdk_loads_provider_and_strategy_manifests(self):
        import yaml
        from _support import ROOT
        from dify_plugin.entities.agent import AgentStrategyProviderConfiguration

        def load(path):
            return yaml.safe_load((ROOT / path).read_text())

        with patch("dify_plugin.entities.agent.load_yaml_file", load):
            provider = AgentStrategyProviderConfiguration(**load("provider/pi_agent.yaml"))
        self.assertEqual(provider.strategies[0].identity.name, "pi_agent_dify")

    def test_real_sdk_registration_loads_source_and_assets(self):
        import subprocess
        import sys

        from _support import ROOT

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "from dify_plugin import DifyPluginEnv; "
                "from dify_plugin.core.plugin_registration import PluginRegistration; "
                "PluginRegistration(DifyPluginEnv())",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_strategy_uses_its_sdk_session(self):
        from strategies.pi_agent_dify import PiAgentStrategy

        session = FakeSession([text_chunks("real entry")])
        strategy = PiAgentStrategy(runtime=None, session=session)
        output = list(strategy._invoke(base_parameters()))
        self.assertEqual(len(session.model.llm.calls), 1)
        self.assertTrue(
            any(item.type.value == "text" and item.message.text == "real entry" for item in output)
        )

    def test_http_mcp_uses_pinned_client_signature_and_closes_http_client(self):
        clients = []

        @asynccontextmanager
        async def transport(url, *, http_client=None, terminate_on_close=True):
            clients.append(http_client)
            self.assertEqual(http_client.headers["x-user"], "test-user")
            yield object(), object(), lambda: None

        class SessionStub:
            def __init__(self, *_args):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            async def initialize(self):
                pass

            async def list_tools(self):
                return SimpleNamespace(tools=[])

        async def run():
            runtime = McpRuntime(
                [
                    McpServer(
                        "srv", "http://local.test/mcp", "streamable_http", {"X-User": "test-user"}
                    )
                ],
                RuntimeConfig(),
            )
            with (
                patch("pi_agent.mcp.streamable_http_client", transport),
                patch("pi_agent.mcp.ClientSession", SessionStub),
            ):
                try:
                    await runtime.open()
                finally:
                    await runtime.close()
            self.assertTrue(clients[0].is_closed)

        asyncio.run(run())

    def test_encoder_never_accepts_state_its_decoder_rejects(self):
        state = PiState.fresh("conv")
        state.entries = [user("u", None, "A" * (MAX_PAYLOAD_BYTES + 100))]
        state.leaf_id = "u"
        saved = encode_state(state)
        if saved.persisted:
            self.assertIsNone(decode_state(saved.value).error)
        else:
            self.assertFalse(saved.value)
            self.assertEqual(saved.error, "state_too_large")

    def test_storage_trim_keeps_summary_on_active_branch(self):
        state = PiState.fresh("conv")
        rng = random.Random(42)  # noqa: S311 - deterministic non-security fixture
        parent = None
        for index in range(12):
            state.entries.extend(
                [
                    user(f"u{index}", parent, rng.randbytes(400).hex()),
                    assistant(f"a{index}", f"u{index}", rng.randbytes(400).hex()),
                ]
            )
            parent = f"a{index}"
        state.leaf_id = parent
        saved = encode_state(state, max_encoded_bytes=7000, target_encoded_bytes=5000)
        self.assertTrue(saved.persisted)
        loaded = decode_state(saved.value).state
        branch = asyncio.run(Session(build_storage(loaded)).get_branch())
        self.assertTrue(any(entry.type == "compaction" for entry in branch))

    def test_reasoning_does_not_replace_answer_body(self):
        out = run_turn(
            FakeSession(
                [[{"delta": {"message": {"reasoning_content": "reasoning", "content": "answer"}}}]]
            ),
            base_parameters(),
        )
        ends = [e for e in display_events(out) if e["type"] == "message.end"]
        self.assertEqual(ends[-1]["text"], "answer")

    def test_nonstream_usage_is_reported(self):
        session = FakeSession(
            [
                {
                    "message": {"content": "answer"},
                    "usage": {"prompt_tokens": 123, "completion_tokens": 4, "total_tokens": 127},
                }
            ]
        )
        out = run_turn(session, base_parameters(runtime={"stream_mode": "nonstream"}))
        usage = last_terminal(out)["stats"]["usage"]
        self.assertEqual(usage["reported"]["total_tokens"], 127)
        self.assertEqual(usage["unknown_usage_requests"], 0)

    def test_fallback_checks_budget_before_second_request(self):
        session = FakeSession(
            [RuntimeError("stream unavailable"), {"message": {"content": "fallback"}}]
        )
        _, final = consume(build_stream(session, max_model_requests=1))
        self.assertEqual(len(session.model.llm.calls), 1)
        self.assertIn("budget_exhausted", final.errorMessage)

    def test_approval_cannot_target_a_replacement_provider(self):
        original = {
            "name": "write",
            "provider": "alpha",
            "parameters": {"type": "object", "properties": {}},
        }
        session = FakeSession([tool_chunks([{"name": "write"}]), text_chunks("done")])
        runtime = {"approval_tools": ["write"]}
        first = run_turn(session, base_parameters(tools=[original], runtime=runtime))
        pending = decode_state(last_state(first)).state.pending
        run_turn(
            session,
            base_parameters(
                tools=[{**original, "provider": "beta"}],
                runtime=runtime,
                state=last_state(first),
                interaction={
                    "type": "approval",
                    "pending_id": pending["id"],
                    "decision": "approve",
                },
            ),
        )
        self.assertEqual(session.tool.calls, [])

    def test_mcp_business_error_is_an_error(self):
        from pi_agent.budget import RunLedger
        from pi_agent.skills import SkillCatalog
        from pi_agent.tools import ToolRuntime

        class McpStub:
            def tools(self):
                return [McpTool("srv", "write", "write", "", {"type": "object", "properties": {}})]

            async def call(self, *_args):
                return {"isError": True, "content": [{"type": "text", "text": "denied"}]}

        config = RuntimeConfig.from_value({"approval_mode": "off"})
        ledger = RunLedger(config, "run")
        tools = ToolRuntime(
            session=None,
            config=config,
            ledger=ledger,
            run_id="run",
            skills=SkillCatalog.load(),
            mcp=McpStub(),
        )
        outcome = asyncio.run(tools.execute(tools.resolve("write"), "c1", {}))
        self.assertTrue(outcome.is_error)
        self.assertEqual(outcome.details["status"], "error")
        self.assertEqual(ledger.consecutive_errors, 1)

    def test_model_deltas_are_delivered_before_provider_finishes(self):
        out = []
        seen = []

        class Llm:
            def invoke(self, **_kwargs):
                yield from text_chunks("first")
                seen.append(any(e["type"] == "message.delta" for e in display_events(out)))
                yield from text_chunks("second")

        session = FakeSession([])
        session.model.llm = Llm()
        asyncio.run(
            PiAgentRuntime(session).execute_async(base_parameters(), out.append, threading.Event())
        )
        self.assertEqual(seen, [True])

    def test_stop_blocks_new_model_and_tool_calls(self):
        stop = threading.Event()

        class Llm:
            def __init__(self):
                self.calls = 0

            def invoke(self, **_kwargs):
                self.calls += 1
                yield from tool_chunks([{"name": "write"}])
                stop.set()

        session = FakeSession([])
        session.model.llm = Llm()
        out = run_turn(
            session,
            base_parameters(
                tools=[{"name": "write", "parameters": {"type": "object", "properties": {}}}],
                runtime={"max_model_requests": 2},
            ),
            stop=stop,
        )
        self.assertEqual(session.tool.calls, [])
        self.assertEqual(session.model.llm.calls, 1)
        self.assertEqual(last_terminal(out)["status"], "stopped")
