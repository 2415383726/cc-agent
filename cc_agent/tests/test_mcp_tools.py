import base64
import json
import unittest
from contextlib import contextmanager

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.messages import AgentState, ToolCall
from cc_agent.core.tool_adapter import ToolAdapter
from cc_agent.core.tool_catalog import ToolCatalog


class McpConfigurationTests(unittest.TestCase):
    def test_optional_wrapped_configuration_and_invalid_inputs(self):
        self.assertEqual(AgentRunConfig.from_parameters({}).mcp_servers, [])
        wrapped = AgentRunConfig.from_parameters(
            {
                "inputs": {
                    "mcp_servers_config": {
                        "mcpServers": {
                            "one": {"url": "https://example/mcp", "transport": "streamable_http"}
                        }
                    }
                }
            }
        )
        self.assertEqual(wrapped.mcp_servers[0].name, "one")
        for invalid in (
            "{SECRET",
            [],
            {"mcpServers": []},
            {"one": {"url": "file:///SECRET"}},
            {"one": {"url": "http://example", "transport": "stdio"}},
            {
                "one": {
                    "url": "http://example",
                    "headers": {"Authorization": "{{#missing.SECRET#}}"},
                }
            },
            {"one": {"url": "http://example", "timeout": -1}},
            {"one": {"url": "http://example", "timeout": float("nan")}},
        ):
            with self.subTest(value=type(invalid).__name__), self.assertRaises(
                (TypeError, ValueError)
            ) as raised:
                AgentRunConfig.from_parameters({"mcp_servers_config": invalid})
            self.assertNotIn("SECRET", str(raised.exception))

    def test_runtime_reads_resolved_headers_without_exposing_them_in_repr(self):
        config = AgentRunConfig.from_parameters(
            {
                "query": "hello",
                "mcp_servers_config": json.dumps(
                    {
                        "business": {
                            "transport": "sse",
                            "url": "http://mcp.example/sse",
                            "headers": {"X-User-Id": "user-42", "Authorization": "Bearer SECRET"},
                            "timeout": 2,
                        }
                    }
                ),
            }
        )

        server = config.mcp_servers[0]
        self.assertEqual(server.name, "business")
        self.assertEqual(server.headers["X-User-Id"], "user-42")
        self.assertEqual(server.timeout, 2)
        self.assertNotIn("SECRET", repr(config))
        self.assertNotIn("SECRET", repr(server))


class McpToolIntegrationTests(unittest.TestCase):
    def test_ct_mcp_contract_keeps_twelve_plain_business_tools(self):
        from pathlib import Path

        from cc_agent.core.mcp_tools import McpToolProvider

        snapshot = json.loads(
            Path(__file__).with_name("fixtures").joinpath("ct_mcp_tool_metadata.json").read_text()
        )

        @contextmanager
        def factory(_server):
            class Session:
                def list_tools(self, cursor=None):
                    # The first page contains only excluded tools, discovery must continue.
                    tools = snapshot["tools"]
                    if cursor is None:
                        return {"tools": tools[12:], "nextCursor": "business"}
                    return {"tools": tools[:12]}

            yield Session()

        config = AgentRunConfig.from_parameters(
            {"mcp_servers_config": {"ct": {"url": "http://ct/mcp"}}}
        )
        expected = {
            "search_people",
            "get_people_records",
            "find_organizations",
            "get_job_options",
            "list_job_structures",
            "find_tags",
            "get_staffing_overview",
            "list_staffing_positions",
            "query_relationships",
            "export_people_excel",
            "export_appointment_forms",
            "get_export_job",
        }
        with McpToolProvider(config.mcp_servers, session_factory=factory) as provider:
            catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
            self.assertEqual(
                set(catalog.names_by_kind("mcp")), {"mcp__ct__" + name for name in expected}
            )

    def test_first_connection_debug_logs_redact_echoed_response_credentials(self):
        import subprocess
        import sys
        import textwrap

        script = textwrap.dedent("""
            import io
            import logging
            from cc_agent.core.config import AgentRunConfig
            from cc_agent.core.mcp_tools import McpToolProvider
            from cc_agent.tests.mcp_test_server import mcp_server

            logs = io.StringIO()
            handler = logging.StreamHandler(logs)
            logging.getLogger('httpcore').addHandler(handler)
            logging.getLogger('httpcore').setLevel(logging.DEBUG)
            assert 'httpcore.http11' not in logging.Logger.manager.loggerDict
            with mcp_server(echo_authorization=True) as (url, requests):
                config = AgentRunConfig.from_parameters({'mcp_servers_config': {
                    'one': {'url': url + '/mcp', 'transport': 'streamable_http',
                            'headers': {'Authorization': 'Bearer FIRST_CONNECT_SECRET'}}}})
                with McpToolProvider(config.mcp_servers) as provider:
                    assert len(provider.tool_specs()) == 1
            assert 'receive_response_headers.complete' in logs.getvalue()
            assert 'FIRST_CONNECT_SECRET' not in logs.getvalue(), 'Credential leaked in HTTP logs'
            """)
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_mcp_apps_and_tools_hidden_from_model_never_enter_catalog_or_dispatch(self):
        from cc_agent.core.mcp_tools import McpToolProvider
        from cc_agent.tests.mcp_test_server import mcp_server

        tools = [
            {"name": "search_people", "_meta": {"ui": {"visibility": ["model", "app"]}}},
            {"name": "no_metadata"},
            {"name": "open_named_plain_tool"},
            {"name": "default_visibility", "_meta": {"ui": {}}},
            {"name": "model_only", "_meta": {"ui": {"visibility": ["model"]}}},
            {
                "name": "open_people_search",
                "_meta": {
                    "ui": {
                        "resourceUri": "ui://ct/people_search.html",
                        "visibility": ["model", "app"],
                    }
                },
            },
            {"name": "app_get_view", "_meta": {"ui": {"visibility": ["app"]}}},
            {"name": "hidden", "_meta": {"ui": {"visibility": []}}},
            {"name": "invalid_visibility", "_meta": {"ui": {"visibility": "model"}}},
            {"name": "legacy_app", "_meta": {"ui/resourceUri": "ui://ct/old.html"}},
            {"name": "legacy_template", "_meta": {"openai/outputTemplate": "ui://ct/old.html"}},
        ]
        for tool in tools:
            tool["inputSchema"] = {"type": "object"}
        allowed = {tool["name"] for tool in tools[:5]}
        with mcp_server(tools=tools) as (url, requests):
            config = AgentRunConfig.from_parameters(
                {
                    "mcp_servers_config": {
                        "ct": {
                            "url": url + "/mcp",
                            "transport": "streamable_http",
                            "headers": {"X-Employee-Id": "employee001"},
                        }
                    }
                }
            )
            with McpToolProvider(config.mcp_servers) as provider:
                catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
                self.assertEqual(
                    set(catalog.names_by_kind("mcp")), {"mcp__ct__" + name for name in allowed}
                )
                adapter = ToolAdapter(catalog, AgentState(), mcp_provider=provider)
                for tool in tools[5:]:
                    name = "mcp__ct__" + tool["name"]
                    self.assertNotIn(name, json.dumps(catalog.prompt_tools()))
                    self.assertTrue(adapter.execute(ToolCall("hidden", name, {})).is_error)
                result = adapter.execute(
                    ToolCall("plain", "mcp__ct__search_people", {"text": "employee001"})
                )
                self.assertEqual(result.llm_observation, "employee001")
            calls = [
                data["params"]["name"]
                for data, _headers in requests
                if data["method"] == "tools/call"
            ]
            self.assertEqual(calls, ["search_people"])

    def test_request_timeout_produces_a_paired_safe_tool_error(self):
        from cc_agent.core.mcp_tools import McpToolProvider
        from cc_agent.tests.mcp_test_server import mcp_server

        with mcp_server() as (url, _requests):
            config = AgentRunConfig.from_parameters(
                {
                    "mcp_servers_config": {
                        "one": {
                            "url": url + "/mcp",
                            "transport": "streamable_http",
                            "timeout": 0.5,
                            "headers": {"Authorization": "Bearer TIMEOUT_SECRET"},
                        }
                    }
                }
            )
            with McpToolProvider(config.mcp_servers) as provider:
                catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
                result = ToolAdapter(catalog, AgentState(), mcp_provider=provider).execute(
                    ToolCall("timeout-call", "mcp__one__echo", {"text": "timeout"})
                )
                self.assertTrue(result.is_error)
                self.assertTrue(result.synthetic)
                self.assertEqual(result.to_history()["tool_call_id"], "timeout-call")
                self.assertNotIn("TIMEOUT_SECRET", str(result))

    def test_simultaneous_users_keep_credentials_separate_and_logs_redacted(self):
        from concurrent.futures import ThreadPoolExecutor

        from cc_agent.core.mcp_tools import McpToolProvider
        from cc_agent.tests.mcp_test_server import mcp_server

        with mcp_server() as (url, requests), self.assertLogs("httpx", level="INFO") as logs:

            def invoke(user):
                config = AgentRunConfig.from_parameters(
                    {
                        "mcp_servers_config": {
                            "one": {
                                "url": url + "/mcp?key=SECRET_QUERY",
                                "transport": "streamable_http",
                                "headers": {
                                    "X-User-Id": user,
                                    "Authorization": "Bearer SECRET_" + user,
                                },
                                "timeout": 2,
                            }
                        }
                    }
                )
                with McpToolProvider(config.mcp_servers) as provider:
                    catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
                    return (
                        ToolAdapter(catalog, AgentState(), mcp_provider=provider)
                        .execute(ToolCall(user, "mcp__one__echo", {"text": user}))
                        .llm_observation
                    )

            with ThreadPoolExecutor(max_workers=3) as pool:
                self.assertEqual(
                    list(pool.map(invoke, ("alice", "bob", "carol"))), ["alice", "bob", "carol"]
                )
            for data, headers in requests:
                if data["method"] == "tools/call":
                    user = data["params"]["arguments"]["text"]
                    self.assertEqual(headers["X-User-Id"], user)
                    self.assertEqual(headers["Authorization"], "Bearer SECRET_" + user)
            self.assertNotIn("SECRET_", "\n".join(logs.output))

    def test_multiple_sdk_connections_can_stay_open_in_one_run(self):
        from cc_agent.core.mcp_tools import McpToolProvider
        from cc_agent.tests.mcp_test_server import mcp_server

        with mcp_server() as (url, _requests):
            config = AgentRunConfig.from_parameters(
                {
                    "mcp_servers_config": {
                        name: {
                            "url": url + "/mcp",
                            "transport": "streamable_http",
                            "headers": {"X-User-Id": name},
                            "timeout": 2,
                        }
                        for name in ("one", "two")
                    }
                }
            )
            with McpToolProvider(config.mcp_servers) as provider:
                catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
                adapter = ToolAdapter(catalog, AgentState(), mcp_provider=provider)
                for name in ("one", "two"):
                    result = adapter.execute(ToolCall(name, f"mcp__{name}__echo", {"text": name}))
                    self.assertEqual(result.llm_observation, name)

    def test_initialization_failure_releases_previously_opened_connections(self):
        from cc_agent.core.mcp_tools import McpToolProvider

        closed = []

        @contextmanager
        def factory(server):
            class Session:
                def list_tools(self, cursor=None):
                    if server.name == "two":
                        raise RuntimeError("a transport failure with HIDDEN_TOKEN")
                    return {"tools": []}

            try:
                yield Session()
            finally:
                closed.append(server.name)

        config = AgentRunConfig.from_parameters(
            {"mcp_servers_config": {"one": {"url": "http://one"}, "two": {"url": "http://two"}}}
        )
        with self.assertRaises(ValueError) as raised, McpToolProvider(
            config.mcp_servers, session_factory=factory
        ):
            pass
        self.assertNotIn("HIDDEN_TOKEN", str(raised.exception))
        self.assertEqual(closed, ["two", "one"])

    def test_discovery_paginates_and_redacts_credentials_from_remote_content(self):
        from cc_agent.core.mcp_tools import McpToolProvider

        @contextmanager
        def factory(_server):
            class Session:
                def list_tools(self, cursor=None):
                    if cursor is None:
                        return {
                            "tools": [
                                {
                                    "name": "first",
                                    "description": "Secret is HIDDEN_TOKEN",
                                    "inputSchema": {"type": "object"},
                                }
                            ],
                            "nextCursor": "next",
                        }
                    return {"tools": [{"name": "second", "inputSchema": {"type": "object"}}]}

                def call_tool(self, name, arguments):
                    return {
                        "content": [{"type": "text", "text": "Server echoed Bearer HIDDEN_TOKEN"}],
                        "structuredContent": {"echo": "HIDDEN_TOKEN"},
                    }

            yield Session()

        config = AgentRunConfig.from_parameters(
            {
                "mcp_servers_config": {
                    "one": {
                        "url": "http://one/sse",
                        "headers": {"Authorization": "Bearer HIDDEN_TOKEN"},
                    }
                }
            }
        )
        with McpToolProvider(config.mcp_servers, session_factory=factory) as provider:
            catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
            self.assertEqual(catalog.names_by_kind("mcp"), ["mcp__one__first", "mcp__one__second"])
            self.assertNotIn("HIDDEN_TOKEN", json.dumps(catalog.prompt_tools()))
            result = ToolAdapter(catalog, AgentState(), mcp_provider=provider).execute(
                ToolCall("call", "mcp__one__second", {})
            )
            self.assertNotIn("HIDDEN_TOKEN", str(result))
            self.assertIn("[redacted]", result.llm_observation)

    def test_binary_resources_are_displayed_without_base64_in_model_history(self):
        from cc_agent.core.mcp_tools import McpToolProvider

        payload = base64.b64encode(b"test image bytes").decode()

        @contextmanager
        def factory(_server):
            class Session:
                def list_tools(self, cursor=None):
                    return {"tools": [{"name": "image", "inputSchema": {"type": "object"}}]}

                def call_tool(self, name, arguments):
                    return {
                        "content": [{"type": "image", "mimeType": "image/png", "data": payload}],
                        "structuredContent": {"count": 1},
                        "isError": True,
                    }

            yield Session()

        config = AgentRunConfig.from_parameters(
            {"mcp_servers_config": {"one": {"url": "http://one/sse"}}}
        )
        with McpToolProvider(config.mcp_servers, session_factory=factory) as provider:
            catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
            result = ToolAdapter(catalog, AgentState(), mcp_provider=provider).execute(
                ToolCall("image-1", "mcp__one__image", {})
            )
            self.assertTrue(result.is_error)
            self.assertEqual(result.metadata["output"], {"count": 1})
            self.assertEqual(result.display_messages[0]["blob"], b"test image bytes")
            self.assertEqual(result.display_messages[0]["meta"]["mime_type"], "image/png")
            self.assertNotIn(payload, json.dumps(result.to_history()))

    def test_redaction_preserves_binary_content_that_contains_a_header_value(self):
        from cc_agent.core.mcp_tools import McpToolProvider

        image = b"\x89PNG\r\n\x1a\n"
        payload = base64.b64encode(image).decode()

        @contextmanager
        def factory(_server):
            class Session:
                def list_tools(self, cursor=None):
                    return {"tools": [{"name": "image", "inputSchema": {"type": "object"}}]}

                def call_tool(self, name, arguments):
                    return {
                        "content": [
                            {"type": "text", "text": "Echoed iVBOR"},
                            {"type": "image", "mimeType": "image/png", "data": payload},
                            {
                                "type": "resource",
                                "resource": {"uri": "test://image", "blob": payload},
                            },
                        ],
                        "structuredContent": {"echo": "iVBOR"},
                    }

            yield Session()

        config = AgentRunConfig.from_parameters(
            {
                "mcp_servers_config": {
                    "one": {"url": "http://one/sse", "headers": {"X-API-Key": "iVBOR"}}
                }
            }
        )
        with McpToolProvider(config.mcp_servers, session_factory=factory) as provider:
            catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
            result = ToolAdapter(catalog, AgentState(), mcp_provider=provider).execute(
                ToolCall("image-1", "mcp__one__image", {})
            )
            self.assertFalse(result.is_error)
            self.assertEqual(
                [message["blob"] for message in result.display_messages], [image, image]
            )
            self.assertEqual(result.metadata["output"], {"echo": "[redacted]"})
            self.assertIn("Echoed [redacted]", result.llm_observation)
            self.assertNotIn("iVBOR", json.dumps(result.to_history()))

    def test_sse_and_later_runs_use_their_own_user_headers(self):
        from cc_agent.core.mcp_tools import McpToolProvider
        from cc_agent.tests.mcp_test_server import mcp_server

        with mcp_server() as (url, requests):
            for user in ("alice", "bob"):
                config = AgentRunConfig.from_parameters(
                    {
                        "mcp_servers_config": {
                            "business": {
                                "url": url + "/sse",
                                "headers": {"X-User-Id": user},
                                "timeout": 2,
                                "sse_read_timeout": 2,
                            }
                        }
                    }
                )
                with McpToolProvider(config.mcp_servers) as provider:
                    catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
                    result = ToolAdapter(catalog, AgentState(), mcp_provider=provider).execute(
                        ToolCall("call-1", "mcp__business__echo", {"text": user})
                    )
                    self.assertEqual(result.llm_observation, user)
            remote_calls = [
                (data, headers) for data, headers in requests if data["method"] == "tools/call"
            ]
            self.assertEqual(
                [headers["X-User-Id"] for _, headers in remote_calls], ["alice", "bob"]
            )

    def test_streamable_http_sends_this_runs_headers_and_calls_the_remote_tool(self):
        from cc_agent.core.mcp_tools import McpToolProvider
        from cc_agent.tests.mcp_test_server import mcp_server

        with mcp_server() as (url, requests):
            config = AgentRunConfig.from_parameters(
                {
                    "mcp_servers_config": {
                        "business": {
                            "transport": "streamable_http",
                            "url": url + "/mcp",
                            "headers": {"X-User-Id": "user-42"},
                            "timeout": 2,
                            "sse_read_timeout": 2,
                        }
                    }
                }
            )
            with McpToolProvider(config.mcp_servers) as provider:
                catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
                result = ToolAdapter(catalog, AgentState(), mcp_provider=provider).execute(
                    ToolCall("call-1", "mcp__business__echo", {"text": "hello MCP"})
                )
                self.assertEqual(result.llm_observation, "hello MCP")
                self.assertFalse(result.is_error)
            self.assertTrue(requests)
            self.assertTrue(all(headers.get("X-User-Id") == "user-42" for _, headers in requests))

    def test_services_with_the_same_tool_keep_schemas_and_route_original_names(self):
        from cc_agent.core.mcp_tools import McpToolProvider

        calls = []
        closed = []
        schema = {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"id": {"type": "integer"}}},
                }
            },
            "required": ["filters"],
        }

        @contextmanager
        def session_factory(server):
            class Session:
                def list_tools(self, cursor=None):
                    return {
                        "tools": [
                            {"name": "search", "description": "Find records", "inputSchema": schema}
                        ]
                    }

                def call_tool(self, name, arguments):
                    calls.append((server.name, name, arguments))
                    return {"content": [{"type": "text", "text": server.name}]}

            try:
                yield Session()
            finally:
                closed.append(server.name)

        config = AgentRunConfig.from_parameters(
            {
                "mcp_servers_config": {
                    "one": {"url": "http://one/sse"},
                    "two": {"url": "http://two/sse"},
                }
            }
        )
        with McpToolProvider(config.mcp_servers, session_factory=session_factory) as provider:
            catalog = ToolCatalog.create(mcp_tools=provider.tool_specs())
            adapter = ToolAdapter(catalog, AgentState(), mcp_provider=provider)
            names = catalog.names_by_kind("mcp")
            self.assertEqual(names, ["mcp__one__search", "mcp__two__search"])
            self.assertEqual(catalog.resolve(names[0]).prompt_tool["parameters"], schema)
            result = adapter.execute(ToolCall("call-1", names[1], {"filters": [{"id": 7}]}))
            self.assertEqual(result.llm_observation, "two")
            self.assertEqual(calls, [("two", "search", {"filters": [{"id": 7}]})])
        self.assertEqual(set(closed), {"one", "two"})


class McpRuntimeTests(unittest.TestCase):
    def test_media_outputs_and_user_interrupts_release_connections_in_both_strategies(self):
        from types import SimpleNamespace

        from cc_agent.core.profiles import AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE
        from cc_agent.core.runtime import DifyAgentRuntime
        from cc_agent.core.state_variable import AgentStateBundle, decode_agent_state, encode_agent_state
        from cc_agent.tests.mcp_test_server import mcp_server

        for profile in (AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE):
            cases = ("binary", "resume_binary", "interrupt") if profile == AGUI_STRATEGY_PROFILE else ("binary", "resume_binary")
            for case in cases:
                with self.subTest(profile=profile.name, case=case), mcp_server() as (url, requests):
                    prompts = []

                    def invoke_llm(case=case, prompts=prompts, **kwargs):
                        prompts.append(kwargs)
                        if len(prompts) > 1 or case == "resume_binary":
                            return SimpleNamespace(
                                message=SimpleNamespace(content="done", tool_calls=[]), usage=None
                            )
                        name = "UserPrompt" if case == "interrupt" else "mcp__one__echo"
                        arguments = (
                            '{"question":"Which record?"}'
                            if case == "interrupt"
                            else '{"text":"binary"}'
                        )
                        return SimpleNamespace(
                            message=SimpleNamespace(
                                content="",
                                tool_calls=[
                                    SimpleNamespace(
                                        id="call-1",
                                        function=SimpleNamespace(name=name, arguments=arguments),
                                    )
                                ],
                            ),
                            usage=None,
                        )

                    strategy = SimpleNamespace(
                        session=SimpleNamespace(
                            conversation_id="conv-1",
                            model=SimpleNamespace(llm=SimpleNamespace(invoke=invoke_llm)),
                        )
                    )
                    resume_parameters = {}
                    if case == "resume_binary":
                        call = {"id": "call-1", "name": "mcp__one__echo", "arguments": {"text": "binary"}}
                        pending = {
                            "role": "tool", "name": call["name"], "tool_call_id": call["id"], "content": "waiting",
                            "metadata": {"requires_user_input": True, "pending_tool_execution": {"name": call["name"], "arguments": call["arguments"]}},
                        }
                        state = encode_agent_state(AgentStateBundle(
                            history={"messages": [{"role": "assistant", "content": "", "tool_calls": [call]}, pending]},
                            last_execution_metadata={"finish_reason": "awaiting_user", "question": {"id": call["id"]}},
                        ))
                        resume_parameters = {"agent_state": state.value, "user_prompt_response": {"promptId": call["id"], "answer": "allow_once"}}
                    events = list(
                        DifyAgentRuntime(strategy, strategy_profile=profile).run(
                            {
                                **resume_parameters,
                                "query": "hello",
                                "stream": False,
                                "mcp_servers_config": {
                                    "one": {
                                        "url": url + "/mcp",
                                        "transport": "streamable_http",
                                        "timeout": 2,
                                        "headers": {"Authorization": "Bearer RUNTIME_SECRET"},
                                    }
                                },
                            }
                        )
                    )
                    state = next(
                        event["value"]
                        for event in events
                        if event.get("type") == "dify_variable"
                        and event.get("name") == "agent_state"
                    )
                    decoded = decode_agent_state(state).bundle
                    if case in {"binary", "resume_binary"}:
                        self.assertEqual(
                            [event["blob"] for event in events if event.get("type") == "dify_blob"],
                            [b"runtime image"],
                        )
                        self.assertNotIn(base64.b64encode(b"runtime image").decode(), str(decoded))
                    else:
                        self.assertEqual(
                            decoded.last_execution_metadata["finish_reason"], "awaiting_user"
                        )
                    self.assertNotIn("RUNTIME_SECRET", str(decoded))
                    self.assertNotIn("RUNTIME_SECRET", str(prompts))
                    self.assertNotIn("RUNTIME_SECRET", str(events))
                    self.assertTrue(any(data["method"] == "DELETE" for data, _ in requests))

    def test_early_generator_close_and_model_failure_release_the_remote_session(self):
        from types import SimpleNamespace

        from cc_agent.core.runtime import DifyAgentRuntime
        from cc_agent.tests.mcp_test_server import mcp_server

        for fail in (False, True):
            with self.subTest(model_failure=fail), mcp_server() as (url, requests):

                def invoke_llm(fail=fail, **kwargs):
                    if fail:
                        raise RuntimeError("model unavailable")
                    return SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-1",
                                    function=SimpleNamespace(
                                        name="mcp__one__echo", arguments='{"text":"hello"}'
                                    ),
                                )
                            ],
                        ),
                        usage=None,
                    )

                strategy = SimpleNamespace(
                    session=SimpleNamespace(
                        conversation_id="conv-1",
                        model=SimpleNamespace(llm=SimpleNamespace(invoke=invoke_llm)),
                    )
                )
                stream = DifyAgentRuntime(strategy).run(
                    {
                        "query": "hello",
                        "stream": False,
                        "mcp_servers_config": {
                            "one": {
                                "url": url + "/mcp",
                                "transport": "streamable_http",
                                "timeout": 2,
                            }
                        },
                    }
                )
                if fail:
                    list(stream)
                else:
                    for event in stream:
                        if event.get("type") == "TOOL_CALL_START":
                            break
                    stream.close()
                self.assertTrue(any(data["method"] == "DELETE" for data, _ in requests))

    def test_both_strategies_discover_and_call_mcp_with_the_normal_agent_loop(self):
        from types import SimpleNamespace

        from cc_agent.core.profiles import AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE
        from cc_agent.core.runtime import DifyAgentRuntime
        from cc_agent.core.state_variable import decode_agent_state
        from cc_agent.tests.mcp_test_server import mcp_server

        tools = [
            {"name": "echo", "inputSchema": {"type": "object"}},
            {
                "name": "app_hidden",
                "inputSchema": {"type": "object"},
                "_meta": {"ui": {"visibility": ["app"]}},
            },
            {
                "name": "open_ui",
                "inputSchema": {"type": "object"},
                "_meta": {"ui": {"resourceUri": "ui://test/app.html"}},
            },
        ]
        for profile in (AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE):
            with self.subTest(profile=profile.name), mcp_server(tools=tools) as (url, requests):
                prompts = []

                def invoke_llm(prompts=prompts, **kwargs):
                    prompts.append(kwargs)
                    if len(prompts) == 1:
                        return SimpleNamespace(
                            message=SimpleNamespace(
                                content="",
                                tool_calls=[
                                    SimpleNamespace(
                                        id="call-1",
                                        function=SimpleNamespace(
                                            name="mcp__business__echo",
                                            arguments='{"text":"runtime MCP"}',
                                        ),
                                    )
                                ],
                            ),
                            usage=None,
                        )
                    return SimpleNamespace(
                        message=SimpleNamespace(content="done", tool_calls=[]), usage=None
                    )

                strategy = SimpleNamespace(
                    session=SimpleNamespace(
                        conversation_id="conv-mcp",
                        model=SimpleNamespace(llm=SimpleNamespace(invoke=invoke_llm)),
                    )
                )
                events = list(
                    DifyAgentRuntime(strategy, strategy_profile=profile).run(
                        {
                            "query": "use the echo tool",
                            "stream": False,
                            "mcp_servers_config": {
                                "business": {
                                    "transport": "streamable_http",
                                    "url": url + "/mcp",
                                    "timeout": 2,
                                }
                            },
                        }
                    )
                )
                state = next(
                    event["value"]
                    for event in events
                    if event.get("type") == "dify_variable" and event.get("name") == "agent_state"
                )
                history = decode_agent_state(state).bundle.history["messages"]
                self.assertTrue(
                    any(
                        message.get("role") == "tool" and message.get("content") == "runtime MCP"
                        for message in history
                    )
                )
                self.assertEqual([data["method"] for data, _ in requests].count("tools/call"), 1)
                self.assertNotIn("mcp__business__app_hidden", str(prompts))
                self.assertNotIn("mcp__business__open_ui", str(prompts))


if __name__ == "__main__":
    unittest.main()
