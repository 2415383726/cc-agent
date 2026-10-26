import unittest
from types import SimpleNamespace

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.dify_stream_writer import DifyNativeWriter
from cc_agent.core.loop import AgentLoop
from cc_agent.core.messages import AgentRunResult, AgentState, AssistantTurn, ToolCall
from cc_agent.core.runtime import DifyAgentRuntime
from cc_agent.core import runtime as runtime_module
from cc_agent.core.state_variable import AgentStateBundle, encode_agent_state
from cc_agent.core.tool_adapter import ToolAdapter
from cc_agent.core.tool_catalog import ToolCatalog


class FakeStorage:
    def __init__(self):
        self.data = {}

    def exist(self, key):
        return key in self.data

    def get(self, key):
        return self.data[key]

    def set(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)


class DifyNativeWriterTests(unittest.TestCase):
    def test_streams_text_and_does_not_duplicate_finished_answer(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")
        result = AgentRunResult(
            answer="hello",
            history=[],
            tasks=[],
            execution_metadata={"finish_reason": "final"},
        )

        events = []
        events.extend(writer.write_run_started())
        events.extend(writer.write_text_delta("hello"))
        events.extend(writer.write_run_finished(result))

        self.assertEqual([event["content"] for event in events if event["type"] == "dify_text"], ["hello"])

    def test_reasoning_delta_opens_think_tag_for_default_dify_chat(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")

        events = writer.write_reasoning_delta("checking", iteration=1)

        self.assertEqual(events, [{"type": "dify_text", "content": "<think>checking"}])

    def test_reasoning_delta_does_not_double_wrap_existing_think_tags(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")

        events = writer.write_reasoning_delta("<think>checking</think>", iteration=1)

        self.assertEqual(events, [{"type": "dify_text", "content": "<think>checking"}])

    def test_reasoning_stream_chunks_close_before_text(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")

        events = []
        events.extend(writer.write_reasoning_delta("first ", iteration=1))
        events.extend(writer.write_reasoning_delta("second", iteration=1))
        events.extend(writer.write_text_delta("answer", iteration=1))

        self.assertEqual(
            [event["content"] for event in events],
            ["<think>first ", "second", "</think>answer"],
        )

    def test_reasoning_stream_closes_before_tool_result(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")
        writer.write_tool_call("call-1", "Search", {"q": "demo"})

        events = []
        events.extend(writer.write_reasoning_delta("thinking", iteration=1))
        events.extend(writer.write_tool_result("call-1", "Search", "done"))

        self.assertEqual(events[0]["content"], "<think>thinking")
        self.assertTrue(events[1]["content"].startswith("</think>"))
        self.assertIn(">_&nbsp;Search", events[1]["content"])

    def test_tool_call_start_is_not_visible_until_result(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")

        events = writer.write_tool_call("call-1", "Search", {"q": "demo"})

        self.assertEqual(events, [])

    def test_tool_result_emits_escaped_html_text_card(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")
        writer.write_tool_call("call-1", "Search", {"q": "<script>alert(1)</script>"})

        events = writer.write_tool_result(
            "call-1",
            "Search",
            "result <script>alert(2)</script>",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "dify_text")
        content = events[0]["content"]
        self.assertTrue(content.startswith("<div"))
        self.assertIn("<details", content)
        self.assertIn("<summary", content)
        self.assertIn("已运行", content)
        self.assertIn(">_&nbsp;Search", content)
        self.assertIn("参数 (Params)", content)
        self.assertIn("结果 (Result)", content)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", content)
        self.assertNotIn("<script>alert(1)</script>", content)
        self.assertNotIn("<script>alert(2)</script>", content)
        self.assertNotIn("<tool-call", content)
        self.assertNotIn("调用工具：Search", content)

    def test_tool_result_can_be_hidden_by_show_tool_calls_flag(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1", show_tool_calls=False)
        writer.write_tool_call("call-1", "Search", {"q": "demo"})

        events = writer.write_tool_result("call-1", "Search", "hidden")

        self.assertEqual(events, [])

    def test_error_emits_dify_log(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")

        error = writer.write_run_error("boom", code="model_error")

        self.assertEqual(error[0]["type"], "dify_log")
        self.assertTrue(error[0]["is_error"])
        self.assertEqual(error[1], {"type": "dify_text", "content": "Agent run failed: boom"})

    def test_finished_model_error_emits_visible_text_for_default_dify_chat(self):
        writer = DifyNativeWriter(thread_id="thread-1", run_id="run-1")
        result = AgentRunResult(
            answer="",
            history=[{"role": "user", "content": "hello"}],
            tasks=[],
            execution_metadata={"finish_reason": "model_error", "error": "read llm model failed"},
        )

        events = writer.write_run_finished(result)

        self.assertEqual(events[0]["type"], "dify_text")
        self.assertIn("模型调用失败", events[0]["content"])
        self.assertIn("read llm model failed", events[0]["content"])
        self.assertEqual(events[1]["type"], "dify_log")


class RuntimeProtocolSwitchTests(unittest.TestCase):
    def setUp(self):
        self.original_loop = runtime_module.AgentLoop

    def tearDown(self):
        runtime_module.AgentLoop = self.original_loop

    def test_runtime_run_defaults_to_raw_agui_events(self):
        captured = {}

        class FakeLoop:
            def __init__(self, **kwargs):
                captured["writer"] = kwargs["writer"]
                self.final_result = None

            def run(self):
                yield from captured["writer"].write_text_delta("ok")
                self.final_result = AgentRunResult(
                    answer="ok",
                    history=[{"role": "assistant", "content": "ok"}],
                    tasks=[],
                    execution_metadata={"finish_reason": "final"},
                )

        runtime_module.AgentLoop = FakeLoop
        strategy = SimpleNamespace(
            session=SimpleNamespace(app_id="app-1", session_id="session-1", conversation_id="conv-1", storage=FakeStorage()),
            runtime=SimpleNamespace(user_id="user-1"),
            _init_prompt_tools=lambda tools: [],
        )

        events = list(DifyAgentRuntime(strategy).run({"query": "hello", "conversation_id": "conv-1"}))

        self.assertEqual(events[0]["type"], "RUN_STARTED")
        run_finished = next(event for event in events if event.get("type") == "RUN_FINISHED")
        self.assertEqual(run_finished["result"]["state_ref"]["conversation_id"], "conv-1")
        self.assertEqual([event["content"] for event in events if event.get("type") == "dify_text"], ["ok"])
        final_answer_log = next(event for event in events if event.get("type") == "dify_finish_log")
        self.assertEqual(final_answer_log["data"]["answer"], "ok")

    def test_runtime_run_can_emit_dify_native_payloads(self):
        captured = {}

        class FakeLoop:
            def __init__(self, **kwargs):
                captured["writer"] = kwargs["writer"]
                self.final_result = None

            def run(self):
                yield from captured["writer"].write_reasoning_delta("thinking")
                yield from captured["writer"].write_tool_call("call-1", "Search", {"q": "<script>alert(1)</script>"})
                yield from captured["writer"].write_tool_result(
                    "call-1",
                    "Search",
                    "tool result <script>alert(2)</script>",
                )
                yield from captured["writer"].write_text_delta("native")
                self.final_result = AgentRunResult(
                    answer="native",
                    history=[
                        {"role": "assistant", "content": "", "tool_calls": [{"id": "call-1", "name": "Search", "arguments": {"q": "<script>alert(1)</script>"}}]},
                        {"role": "tool", "tool_call_id": "call-1", "name": "Search", "content": "tool result <script>alert(2)</script>"},
                        {"role": "assistant", "content": "native"},
                    ],
                    tasks=[],
                    execution_metadata={"finish_reason": "final"},
                )
                captured["final_result"] = self.final_result

        runtime_module.AgentLoop = FakeLoop
        strategy = SimpleNamespace(
            session=SimpleNamespace(app_id="app-1", session_id="session-1", conversation_id="conv-1", storage=FakeStorage()),
            runtime=SimpleNamespace(user_id="user-1"),
            _init_prompt_tools=lambda tools: [],
        )

        events = list(DifyAgentRuntime(strategy).run({
            "query": "hello",
            "conversation_id": "conv-1",
            "output_protocol": False,
        }))

        text_outputs = [event["content"] for event in events if event["type"] == "dify_text"]
        self.assertEqual(text_outputs[0], "<think>thinking")
        self.assertTrue(text_outputs[1].startswith("</think>"))
        self.assertIn(">_&nbsp;Search", text_outputs[1])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text_outputs[1])
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", text_outputs[1])
        self.assertEqual(text_outputs[2], "native")
        self.assertTrue(any(event["type"] == "dify_log" and event["label"] == "Run finished" for event in events))
        history_preview = captured["final_result"].history
        self.assertTrue(all("<details" not in str(message) for message in history_preview))
        self.assertTrue(all("<tool-call" not in str(message) for message in history_preview))
        self.assertTrue(any("tool result <script>alert(2)</script>" in str(message) for message in history_preview))

    def test_compact_command_emits_compression_started_and_completed_activity(self):
        original_summarizer = runtime_module.DifyHistorySummarizer

        class FakeSummarizer:
            def __init__(self, *args, **kwargs):
                pass

            def __call__(self, messages, existing_summary=""):
                return "manual compact summary"

        runtime_module.DifyHistorySummarizer = FakeSummarizer
        try:
            strategy = SimpleNamespace(
                session=SimpleNamespace(app_id="app-1", session_id="session-1", conversation_id="conv-1", storage=FakeStorage()),
                runtime=SimpleNamespace(user_id="user-1"),
                _init_prompt_tools=lambda tools: [],
            )
            history = [{"role": "user", "content": f"old message {index} " * 30} for index in range(12)]
            encoded_state = encode_agent_state(
                AgentStateBundle(
                    history={"messages": history, "summary": "", "version": 1},
                )
            )
            events = list(
                DifyAgentRuntime(strategy).run(
                    {
                        "query": "/compact",
                        "conversation_id": "conv-1",
                        "agent_state": encoded_state.value,
                        "model": SimpleNamespace(),
                        "runtime_config": '{"max_history_messages": 4}',
                    }
                )
            )
        finally:
            runtime_module.DifyHistorySummarizer = original_summarizer

        compression_events = [
            event
            for event in events
            if event.get("type") == "ACTIVITY_SNAPSHOT" and event.get("activityType") == "cc_agent.compression"
        ]

        self.assertEqual([event["content"]["status"] for event in compression_events], ["started", "completed"])
        self.assertEqual(compression_events[0]["content"]["trigger"], "manual")
        self.assertEqual(compression_events[1]["content"]["trigger"], "manual")
        self.assertEqual(
            compression_events[0]["content"]["compressionId"],
            compression_events[1]["content"]["compressionId"],
        )
        self.assertGreater(compression_events[1]["content"]["summarized_messages"], 0)


class AgentLoopWriterBoundaryTests(unittest.TestCase):
    def test_loop_yields_writer_payloads_instead_of_internal_wire_events(self):
        class RecordingWriter:
            def __init__(self):
                self.calls = []

            def write_reasoning_delta(self, text, iteration=0):
                self.calls.append(("reasoning", text, iteration))
                return [{"type": "reasoning", "text": text}]

            def write_text_delta(self, text, iteration=0):
                self.calls.append(("text", text, iteration))
                return [{"type": "text", "text": text}]

            def write_tool_call(self, tool_call_id, tool_name, args=None):
                self.calls.append(("tool_call", tool_call_id, tool_name, args))
                return [{"type": "tool_call", "id": tool_call_id, "name": tool_name}]

            def write_tool_result(self, tool_call_id, tool_name="", observation=None, **kwargs):
                self.calls.append(("tool_result", tool_call_id, tool_name, observation, kwargs))
                return [{"type": "tool_result", "id": tool_call_id, "name": tool_name}]

            def write_activity(self, activity_type, content=None):
                self.calls.append(("activity", activity_type, content))
                return [{"type": "activity", "activityType": activity_type}]

        class FakeModel:
            def __init__(self):
                self.calls = 0

            def invoke(self, messages, tools, force_final=False):
                self.calls += 1
                if self.calls == 1:
                    return AssistantTurn(
                        text="",
                        tool_calls=[ToolCall(id="call-1", name="TaskCreate", arguments={"key": "k", "value": "v"})],
                    )
                return AssistantTurn(text="done")

        writer = RecordingWriter()
        state = AgentState()
        registry = ToolCatalog.create()
        loop = AgentLoop(
            config=AgentRunConfig(query="remember", maximum_iterations=2),
            state=state,
            registry=registry,
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(registry, state),
            writer=writer,
        )

        events = list(loop.run())

        self.assertTrue(events)
        self.assertTrue(all(isinstance(event, dict) for event in events))
        self.assertIn(("tool_call", "call-1", "TaskCreate", {"key": "k", "value": "v"}), writer.calls)
        self.assertTrue(any(call[0] == "tool_result" and call[1] == "call-1" for call in writer.calls))
        self.assertEqual(loop.final_result.answer, "done")

    def test_loop_emits_compression_started_and_completed_with_same_id(self):
        class RecordingWriter:
            def write_activity(self, activity_type, content=None):
                return [{"type": "activity", "activityType": activity_type, "content": content or {}}]

            def write_text_delta(self, text, iteration=0):
                return [{"type": "text", "text": text}]

        class FakeModel:
            def invoke(self, messages, tools, force_final=False):
                return AssistantTurn(text="done")

        history = [{"role": "user", "content": f"old message {index} " * 30} for index in range(12)]
        loop = AgentLoop(
            config=AgentRunConfig(query="hello", max_history_messages=4),
            state=AgentState(history=history),
            registry=ToolCatalog.create(),
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(ToolCatalog.create(), AgentState()),
            summarizer=lambda messages, existing_summary="": "auto compact summary",
            writer=RecordingWriter(),
        )

        events = list(loop.run())
        compression_events = [
            event
            for event in events
            if event.get("activityType") == "cc_agent.compression"
        ]

        self.assertEqual([event["content"]["status"] for event in compression_events], ["started", "completed"])
        self.assertEqual(compression_events[0]["content"]["trigger"], "auto")
        self.assertEqual(compression_events[1]["content"]["trigger"], "auto")
        self.assertEqual(
            compression_events[0]["content"]["compressionId"],
            compression_events[1]["content"]["compressionId"],
        )
        self.assertGreater(compression_events[1]["content"]["summarized_messages"], 0)


class StrategyProtocolDispatchTests(unittest.TestCase):
    def test_strategy_dispatches_agui_dify_text_and_dify_log(self):
        from cc_agent.strategies.cc_agent_dify import CCAgentDifyStrategy

        class FakeRuntime:
            def __init__(self, strategy, strategy_profile=None):
                pass

            def run(self, parameters):
                yield {"type": "RUN_STARTED", "threadId": "thread-1", "runId": "run-1"}
                yield {"type": "dify_text", "content": "native answer"}
                yield {
                    "type": "dify_log",
                    "label": "Tool: Search",
                    "data": {"raw": {"ok": True}},
                    "is_error": True,
                }
                yield {
                    "type": "dify_blob",
                    "blob": b"artifact",
                    "meta": {"filename": "report.md", "mime_type": "text/markdown"},
                }
                yield {
                    "type": "dify_finish_log",
                    "label": "Final answer",
                    "data": {"kind": "cc_agent.final_answer", "answer": "native answer"},
                }
                yield {"type": "dify_variable", "name": "answer", "value": "native answer"}
                yield {"type": "dify_json", "payload": {"agent_state": "ccagent-state:v1:gzip-base64:abc"}}

        original_runtime = CCAgentDifyStrategy.runtime_cls
        CCAgentDifyStrategy.runtime_cls = FakeRuntime
        try:
            strategy = object.__new__(CCAgentDifyStrategy)
            strategy.session = SimpleNamespace()
            strategy.create_log_message = lambda label, data, metadata, status: {
                "kind": "log",
                "label": label,
                "data": data,
                "metadata": metadata,
                "status": status,
            }
            strategy.create_text_message = lambda text: {"kind": "text", "text": text}
            strategy.create_json_message = lambda payload: {
                "kind": "json",
                "payload": payload,
            }
            strategy.create_blob_message = lambda blob, meta: {
                "kind": "blob",
                "blob": blob,
                "meta": meta,
            }
            strategy.create_variable_message = lambda name, value: {
                "kind": "variable",
                "name": name,
                "value": value,
            }
            strategy.finish_log_message = lambda log, status, data, metadata: {
                "kind": "finish_log",
                "label": log["label"],
                "data": data,
                "metadata": metadata,
                "status": status,
            }

            emitted = list(strategy._invoke({"query": "x"}))
        finally:
            CCAgentDifyStrategy.runtime_cls = original_runtime

        self.assertEqual(emitted[0]["kind"], "log")
        self.assertEqual(emitted[0]["label"], "AG-UI RUN_STARTED")
        self.assertEqual(emitted[1], {"kind": "text", "text": "native answer"})
        self.assertEqual(emitted[2]["kind"], "log")
        self.assertEqual(emitted[2]["label"], "Tool: Search")
        self.assertEqual(emitted[3]["kind"], "blob")
        self.assertEqual(emitted[3]["blob"], b"artifact")
        self.assertEqual(emitted[3]["meta"]["filename"], "report.md")
        self.assertEqual(emitted[4]["kind"], "log")
        self.assertEqual(emitted[4]["label"], "Final answer")
        self.assertEqual(emitted[5]["kind"], "finish_log")
        self.assertEqual(emitted[5]["label"], "Final answer")
        self.assertEqual(emitted[5]["data"]["answer"], "native answer")
        self.assertEqual(emitted[6], {"kind": "variable", "name": "answer", "value": "native answer"})
        self.assertEqual(emitted[7], {"kind": "json", "payload": {"agent_state": "ccagent-state:v1:gzip-base64:abc"}})
