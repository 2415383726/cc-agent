from __future__ import annotations

import asyncio
import threading
import unittest

from _support import ROOT  # noqa: F401

from pi_agent.budget import RunLedger
from pi_agent.config import RuntimeConfig
from pi_agent.errors import PiError
from pi_agent.mcp import McpRuntime, McpServer, McpTool, parse_servers
from pi_agent.skills import SkillCatalog
from pi_agent.tools import ToolRuntime


class FakeSession:
    def __init__(self, result=None, delay: float = 0):
        self.result = result
        self.delay = delay
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result


def runtime_with_tools(*tools: McpTool, session: FakeSession | None = None) -> McpRuntime:
    config = RuntimeConfig.from_value({"mcp_tool_timeout": 0.05})
    runtime = McpRuntime([McpServer(name="srv", url="http://example.test/mcp")], config)
    runtime._opened = True
    for tool in tools:
        runtime._tools[tool.exposed_name] = tool
    if session is not None:
        runtime._sessions["srv"] = session
    return runtime


class ParseTests(unittest.TestCase):
    def test_remote_only_and_resolved_headers(self) -> None:
        servers = parse_servers(
            {
                "mcpServers": {
                    "srv": {
                        "transport": "streamable_http",
                        "url": "https://example.test/mcp",
                        "headers": {"Authorization": "Bearer token"},
                    }
                }
            }
        )
        self.assertEqual(servers[0].transport, "streamable_http")
        with self.assertRaises(PiError):
            parse_servers({"srv": {"transport": "stdio", "command": "node"}})
        with self.assertRaises(PiError):
            parse_servers({"srv": {"url": "https://example.test/{{token}}"}})
        with self.assertRaises(PiError):
            parse_servers({"srv": {"url": "https://example.test", "headers": {"X": "a\nb"}}})

    def test_app_only_filter(self) -> None:
        from pi_agent.mcp import _is_app_only
        from types import SimpleNamespace

        self.assertTrue(_is_app_only(SimpleNamespace(name="app__internal")))
        self.assertTrue(_is_app_only(SimpleNamespace(name="x", meta={"appOnly": True})))
        self.assertFalse(_is_app_only(SimpleNamespace(name="search")))


class McpRuntimeTests(unittest.TestCase):
    def test_calls_the_current_run_session_and_cleans_up(self) -> None:
        tool = McpTool(
            server="srv",
            name="echo",
            exposed_name="echo",
            description="Echo",
            parameters={"type": "object", "properties": {}},
        )
        session = FakeSession({"content": [{"type": "text", "text": "ok"}]})
        runtime = runtime_with_tools(tool, session=session)
        result = asyncio.run(runtime.call("echo", {"x": 1}))
        self.assertEqual(result["content"][0]["text"], "ok")
        self.assertEqual(session.calls, [("echo", {"x": 1})])
        asyncio.run(runtime.close())
        self.assertEqual(runtime._sessions, {})
        self.assertEqual(runtime.tools(), [])

    def test_timeout_and_failure_become_unknown(self) -> None:
        tool = McpTool("srv", "slow", "slow", "Slow", {"type": "object", "properties": {}})
        runtime = runtime_with_tools(tool, session=FakeSession(delay=0.2))
        with self.assertRaises(PiError) as timeout:
            asyncio.run(runtime.call("slow", {}))
        self.assertEqual(timeout.exception.code, "unknown_outcome")

        class Broken(FakeSession):
            async def call_tool(self, name, arguments):
                raise RuntimeError("boom")

        runtime = runtime_with_tools(tool, session=Broken())
        with self.assertRaises(PiError) as failure:
            asyncio.run(runtime.call("slow", {}))
        self.assertEqual(failure.exception.code, "unknown_outcome")
        self.assertNotIn("boom", failure.exception.message)


class McpToolDeliveryTests(unittest.TestCase):
    def _runtime(self) -> tuple[ToolRuntime, list, McpRuntime]:
        tool = McpTool(
            "srv",
            "render",
            "render",
            "Render a file",
            {"type": "object", "properties": {}},
            {"readOnlyHint": True},
        )
        result = {
            "content": [
                {"type": "text", "text": "rendered"},
                {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
            ]
        }
        mcp = runtime_with_tools(tool, session=FakeSession(result))
        config = RuntimeConfig.from_value({"approval_mode": "off"})
        delivered = []

        def sink(artifact):
            delivered.append(artifact)
            return artifact.public()

        tools = ToolRuntime(
            session=None,
            config=config,
            ledger=RunLedger(config, "run"),
            run_id="run",
            skills=SkillCatalog.load(),
            mcp=mcp,
            artifact_sink=sink,
            dify_tools=[],
        )
        return tools, delivered, mcp

    def test_artifact_is_delivered_once(self) -> None:
        tools, delivered, _mcp = self._runtime()
        spec = tools.resolve("render")
        outcome = asyncio.run(tools.execute(spec, "call_1", {}))
        self.assertEqual(len(delivered), 1)
        self.assertEqual(len(outcome.details["artifacts"]), 1)
        self.assertEqual(outcome.details["artifacts"][0]["source"], "mcp")
        self.assertIn("rendered", outcome.text)

    def test_two_runs_do_not_share_sessions(self) -> None:
        tools_a, delivered_a, mcp_a = self._runtime()
        tools_b, delivered_b, mcp_b = self._runtime()
        asyncio.run(tools_a.execute(tools_a.resolve("render"), "call_a", {}))
        asyncio.run(tools_b.execute(tools_b.resolve("render"), "call_b", {}))
        self.assertIsNot(mcp_a, mcp_b)
        self.assertEqual(len(delivered_a), 1)
        self.assertEqual(len(delivered_b), 1)


if __name__ == "__main__":
    unittest.main()
