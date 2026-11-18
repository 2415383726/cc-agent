from __future__ import annotations

import asyncio
import unittest

from _support import ROOT  # noqa: F401

from pi_strategy.budget import RunLedger
from pi_strategy.config import RuntimeConfig
from pi_strategy.errors import PiError
from pi_strategy.mcp import McpRuntime, McpServer, McpTool, parse_servers
from pi_strategy.skills import SkillCatalog
from pi_strategy.tools import ToolRuntime


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
        from types import SimpleNamespace

        from pi_strategy.mcp import _is_app_only

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
        config = RuntimeConfig()
        delivered = []

        def sink(artifact):
            delivered.append(artifact)
            return artifact.public()

        tools = ToolRuntime(
            session=None,
            config=config,
            ledger=RunLedger(config, "run"),
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


class FailSoftTests(unittest.TestCase):
    def test_one_failing_server_does_not_drop_the_others(self) -> None:
        async def scenario():
            runtime = McpRuntime(
                [McpServer("a", "http://a.test/mcp"), McpServer("b", "http://b.test/sse")],
                RuntimeConfig(),
            )
            attempted = []

            async def connect(server):
                attempted.append(server.name)
                if server.name == "a":
                    raise RuntimeError("dial failed")

            runtime._connect = connect
            await runtime.open()
            return attempted, runtime.errors

        attempted, errors = asyncio.run(scenario())
        self.assertEqual(attempted, ["a", "b"])
        self.assertEqual([item["server"] for item in errors], ["a"])
        self.assertEqual(errors[0]["error"], "RuntimeError")


class InvalidParamsTests(unittest.TestCase):
    def test_invalid_params_is_not_executed(self) -> None:
        from types import SimpleNamespace

        class McpError(Exception):
            def __init__(self, code: int):
                self.error = SimpleNamespace(code=code)

        class InvalidSession(FakeSession):
            async def call_tool(self, name, arguments):
                raise McpError(-32602)

        tool = McpTool("srv", "write", "write", "", {"type": "object", "properties": {}})
        mcp = runtime_with_tools(tool, session=InvalidSession())
        with self.assertRaises(PiError) as failure:
            asyncio.run(mcp.call("write", {}))
        self.assertEqual(failure.exception.details["execution_outcome"], "not_executed")

        config = RuntimeConfig()
        tools = ToolRuntime(
            session=None,
            config=config,
            ledger=RunLedger(config, "run"),
            skills=SkillCatalog.load(),
            mcp=mcp,
        )
        outcome = asyncio.run(tools.execute(tools.resolve("write"), "c1", {}))
        self.assertEqual(outcome.details["status"], "not_executed")
        self.assertEqual(outcome.details["execution_outcome"], "not_executed")
        self.assertTrue(outcome.is_error)


if __name__ == "__main__":
    unittest.main()
