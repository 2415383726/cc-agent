import unittest
from types import SimpleNamespace

from cc_agent.core.compression import DifyHistorySummarizer
from cc_agent.core.config import AgentRunConfig
from cc_agent.core.context_budget import ContextBudget
from cc_agent.core.history import dump_history, load_history, sanitize_history
from cc_agent.core.internal_tools import InternalToolExecutor
from cc_agent.core.loop import AgentLoop
from cc_agent.core.messages import AgentState, AssistantTurn, ToolCall
from cc_agent.core.model_adapter import (
    DifyModelAdapter,
    StreamToolCallAccumulator,
    to_dify_prompt_messages,
)
from cc_agent.core.model_stream import AssistantTurnCompleted, TextDelta, ThinkingDelta
from cc_agent.core.tool_adapter import ToolAdapter, normalize_tool_invoke_messages
from cc_agent.core.tool_catalog import ToolCatalog


def fake_tool(name: str, provider: str = "demo"):
    return SimpleNamespace(
        identity=SimpleNamespace(name=name, provider=provider),
        provider_type="builtin",
        runtime_parameters={"fixed": "runtime"},
        parameters=[],
    )


class HistoryTests(unittest.TestCase):
    def test_history_round_trips_and_removes_orphan_tool_messages(self):
        messages = [
            {"role": "user", "content": "remember this"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "TaskCreate",
                        "arguments": {"key": "topic", "value": "dify"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "TaskCreate", "content": "saved"},
            {
                "role": "tool",
                "tool_call_id": "orphan",
                "name": "Missing",
                "content": "should be dropped",
            },
            {
                "role": "assistant",
                "content": "unfinished",
                "tool_calls": [{"id": "call_2", "name": "TaskList", "arguments": {}}],
            },
            {"role": "user", "content": "continue"},
        ]

        clean = sanitize_history(messages)

        self.assertEqual(
            [m["role"] for m in clean], ["user", "assistant", "tool", "assistant", "user"]
        )
        self.assertNotIn("tool_calls", clean[3])
        payload = dump_history(clean, summary="previous summary")
        loaded = load_history(payload)
        self.assertEqual(loaded.messages, clean)
        self.assertEqual(loaded.summary, "previous summary")


class StreamToolCallAccumulatorTests(unittest.TestCase):
    def test_accumulates_incremental_name_and_arguments_with_empty_id(self):
        acc = StreamToolCallAccumulator()

        acc.add_delta(
            [{"index": 0, "id": "", "function": {"name": "Task", "arguments": '{"query":"di'}}]
        )
        acc.add_delta([{"index": 0, "function": {"name": "List", "arguments": 'fy"}'}}])

        calls = acc.finalize()

        self.assertEqual(calls[0].id, "call_0")
        self.assertEqual(calls[0].name, "TaskList")
        self.assertEqual(calls[0].arguments, {"query": "dify"})

    def test_accepts_cumulative_arguments_and_preserves_raw_invalid_json(self):
        acc = StreamToolCallAccumulator(mode="snapshot")

        acc.add_delta(
            [{"index": 0, "id": "abc", "function": {"name": "Skill", "arguments": '{"name":'}}]
        )
        acc.add_delta([{"index": 0, "id": "abc", "function": {"arguments": '{"name":"brief"}'}}])
        acc.add_delta([{"index": 1, "function": {"name": "Broken", "arguments": "{bad"}}])

        calls = acc.finalize()

        self.assertEqual(calls[0].arguments, {"name": "brief"})
        self.assertEqual(calls[1].arguments, {"_raw_arguments": "{bad"})

    def test_replaces_restarted_stream_arguments_instead_of_concatenating(self):
        acc = StreamToolCallAccumulator(mode="snapshot")

        acc.add_delta(
            [{"index": 0, "id": "abc", "function": {"name": "weekday", "arguments": '{"year":2'}}]
        )
        acc.add_delta(
            [{"index": 0, "id": "abc", "function": {"arguments": '{"year":5,"month":3,"day":24}'}}]
        )

        calls = acc.finalize()

        self.assertEqual(calls[0].arguments, {"year": 5, "month": 3, "day": 24})

    def test_stream_collector_separates_thinking_from_text(self):
        chunks = [
            SimpleNamespace(
                delta=SimpleNamespace(
                    message=SimpleNamespace(content="<think>abc</think>final", tool_calls=[])
                )
            )
        ]

        events = list(DifyModelAdapter(None, {}, stream=True).collect_stream_events(chunks))
        turn = events[-1].turn

        self.assertEqual(
            [type(event) for event in events], [ThinkingDelta, TextDelta, AssistantTurnCompleted]
        )
        self.assertEqual(events[0].text, "abc")
        self.assertEqual(events[1].text, "final")
        self.assertEqual(turn.text, "final")
        self.assertEqual(turn.reasoning_content, "abc")

    def test_stream_collector_handles_think_tags_split_across_chunks(self):
        chunks = [
            SimpleNamespace(
                delta=SimpleNamespace(message=SimpleNamespace(content="<thi", tool_calls=[]))
            ),
            SimpleNamespace(
                delta=SimpleNamespace(message=SimpleNamespace(content="nk>abc</thi", tool_calls=[]))
            ),
            SimpleNamespace(
                delta=SimpleNamespace(message=SimpleNamespace(content="nk>final", tool_calls=[]))
            ),
        ]

        events = list(DifyModelAdapter(None, {}, stream=True).collect_stream_events(chunks))
        turn = events[-1].turn

        self.assertEqual(
            [(type(event), getattr(event, "text", None)) for event in events],
            [(ThinkingDelta, "abc"), (TextDelta, "final"), (AssistantTurnCompleted, None)],
        )
        self.assertEqual(turn.text, "final")
        self.assertEqual(turn.reasoning_content, "abc")

    def test_stream_collector_keeps_tool_calls_when_thinking_is_present(self):
        chunks = [
            SimpleNamespace(
                delta=SimpleNamespace(
                    message=SimpleNamespace(content="<think>abc</think>", tool_calls=[])
                )
            ),
            SimpleNamespace(
                delta=SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call_1",
                                function=SimpleNamespace(
                                    name="TaskList", arguments='{"query":"dify"}'
                                ),
                            )
                        ],
                    )
                )
            ),
        ]

        events = list(DifyModelAdapter(None, {}, stream=True).collect_stream_events(chunks))
        turn = events[-1].turn

        self.assertEqual(turn.reasoning_content, "abc")
        self.assertEqual(turn.tool_calls[0].name, "TaskList")
        self.assertEqual(turn.tool_calls[0].arguments, {"query": "dify"})

    def test_blocking_collector_separates_thinking_from_text(self):
        result = SimpleNamespace(
            message=SimpleNamespace(content="<think>abc</think>final", tool_calls=[]),
            usage={"total_tokens": 1},
            finish_reason="stop",
        )

        turn = DifyModelAdapter(None, {}, stream=False)._collect_result(result)

        self.assertEqual(turn.text, "final")
        self.assertEqual(turn.reasoning_content, "abc")
        self.assertEqual(
            [(type(event), event.text) for event in turn.stream_chunks],
            [(ThinkingDelta, "abc"), (TextDelta, "final")],
        )

    def test_blocking_collector_reads_reasoning_content_field(self):
        result = SimpleNamespace(
            message=SimpleNamespace(content="final", reasoning_content="abc", tool_calls=[]),
            usage={"total_tokens": 1},
            finish_reason="stop",
        )

        turn = DifyModelAdapter(None, {}, stream=False)._collect_result(result)

        self.assertEqual(turn.text, "final")
        self.assertEqual(turn.reasoning_content, "abc")
        self.assertEqual(
            [(type(event), event.text) for event in turn.stream_chunks],
            [(ThinkingDelta, "abc"), (TextDelta, "final")],
        )

    def test_blocking_collector_merges_reasoning_field_and_think_tags(self):
        result = SimpleNamespace(
            message=SimpleNamespace(
                content="<think>tag</think>final", reasoning_content="field", tool_calls=[]
            ),
            usage={"total_tokens": 1},
            finish_reason="stop",
        )

        turn = DifyModelAdapter(None, {}, stream=False)._collect_result(result)

        self.assertEqual(turn.text, "final")
        self.assertEqual(turn.reasoning_content, "fieldtag")

    def test_model_adapter_strips_dify_history_from_stream_model_config(self):
        captured = {}

        class FakeLLM:
            def invoke(self, **kwargs):
                captured.update(kwargs)
                return [
                    SimpleNamespace(
                        delta=SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))
                    )
                ]

        session = SimpleNamespace(model=SimpleNamespace(llm=FakeLLM()))
        adapter = DifyModelAdapter(
            session,
            {
                "model": "demo",
                "provider": "p",
                "mode": "chat",
                "history_prompt_messages": [{"role": "user", "content": "old"}],
            },
            stream=True,
        )

        events = list(adapter.invoke_stream([{"role": "user", "content": "current"}], []))

        self.assertEqual(events[-1].turn.text, "ok")
        self.assertFalse(hasattr(captured["model_config"], "history_prompt_messages"))
        if isinstance(captured["model_config"], dict):
            self.assertNotIn("history_prompt_messages", captured["model_config"])

    def test_model_adapter_strips_dify_history_from_blocking_model_config(self):
        captured = {}

        class FakeLLM:
            def invoke(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    message=SimpleNamespace(content="ok", tool_calls=[]),
                    usage={},
                    finish_reason="stop",
                )

        session = SimpleNamespace(model=SimpleNamespace(llm=FakeLLM()))
        adapter = DifyModelAdapter(
            session,
            SimpleNamespace(
                model="demo",
                provider="p",
                history_prompt_messages=[{"role": "user", "content": "old"}],
            ),
            stream=False,
        )

        turn = adapter.invoke([{"role": "user", "content": "current"}], [])

        self.assertEqual(turn.text, "ok")
        self.assertFalse(hasattr(captured["model_config"], "history_prompt_messages"))

    def test_summarizer_strips_dify_history_from_model_config(self):
        captured = {}

        class FakeLLM:
            def invoke(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(message=SimpleNamespace(content="summary"))

        session = SimpleNamespace(model=SimpleNamespace(llm=FakeLLM()))
        summarizer = DifyHistorySummarizer(
            session,
            {
                "model": "demo",
                "provider": "p",
                "mode": "chat",
                "history_prompt_messages": [{"role": "user", "content": "old"}],
            },
        )

        result = summarizer([{"role": "user", "content": "current"}])

        self.assertEqual(result, "summary")
        self.assertFalse(hasattr(captured["model_config"], "history_prompt_messages"))
        if isinstance(captured["model_config"], dict):
            self.assertNotIn("history_prompt_messages", captured["model_config"])

    def test_deepseek_compat_prompt_messages_preserve_reasoning_content(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "I should call the weekday tool.",
                "tool_calls": [{"id": "call_1", "name": "weekday", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "weekday", "content": "Monday"},
        ]

        converted = to_dify_prompt_messages(messages, preserve_reasoning_content=True)
        assistant = converted[0]

        if isinstance(assistant, dict):
            self.assertEqual(assistant["reasoning_content"], "I should call the weekday tool.")
        else:
            self.assertEqual(
                getattr(assistant, "reasoning_content"), "I should call the weekday tool."
            )

    def test_deepseek_reasoning_error_retries_with_flattened_tool_history(self):
        captured = []

        def failing_stream():
            raise Exception(
                "The `reasoning_content` in the thinking mode must be passed back to the API."
            )
            yield

        class FakeLLM:
            def invoke(self, **kwargs):
                captured.append(kwargs)
                if len(captured) == 1:
                    return failing_stream()
                return [
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            message=SimpleNamespace(content="今天是星期一。", tool_calls=[])
                        )
                    )
                ]

        session = SimpleNamespace(model=SimpleNamespace(llm=FakeLLM()))
        adapter = DifyModelAdapter(
            session,
            {"model": "deepseek-v4-pro", "provider": "deepseek", "mode": "chat"},
            stream=True,
            deepseek_thinking_compat=True,
        )
        messages = [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "I need the current time.",
                "tool_calls": [{"id": "call_1", "name": "current_time", "arguments": {}}],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "current_time",
                "content": "2026-05-25 11:26:28",
            },
            {"role": "user", "content": "今天星期几？"},
        ]

        events = list(
            adapter.invoke_stream(
                messages, [{"name": "weekday", "description": "", "parameters": {}}]
            )
        )

        self.assertEqual(events[-1].turn.text, "今天是星期一。")
        self.assertEqual(len(captured), 2)
        first_messages = captured[0]["prompt_messages"]
        first_assistant = first_messages[0]
        if isinstance(first_assistant, dict):
            self.assertEqual(first_assistant["reasoning_content"], "I need the current time.")
        else:
            self.assertEqual(
                getattr(first_assistant, "reasoning_content"), "I need the current time."
            )
        retry_messages = captured[1]["prompt_messages"]
        retry_roles = [
            (
                getattr(message, "role", None).value
                if hasattr(getattr(message, "role", None), "value")
                else getattr(message, "role", None) or message.get("role")
            )
            for message in retry_messages
        ]
        self.assertNotIn("tool", retry_roles)
        retry_assistant_messages = [
            message
            for message in retry_messages
            if (
                getattr(getattr(message, "role", None), "value", getattr(message, "role", None))
                if not isinstance(message, dict)
                else message.get("role")
            )
            == "assistant"
        ]
        self.assertTrue(
            all(
                not (
                    message.get("tool_calls")
                    if isinstance(message, dict)
                    else getattr(message, "tool_calls", [])
                )
                for message in retry_assistant_messages
            )
        )
        retry_text = "\n".join(
            str(
                getattr(message, "content", "")
                if not isinstance(message, dict)
                else message.get("content", "")
            )
            for message in retry_messages
        )
        self.assertIn("Tool result for current_time", retry_text)


class ToolMessageNormalizationTests(unittest.TestCase):
    def test_retriever_resources_enter_observation_and_display_messages(self):
        response = SimpleNamespace(
            type="retriever_resources",
            message=[
                {
                    "title": "Doc A",
                    "source": "kb",
                    "content": "The answer is in this passage.",
                    "metadata": {"score": 0.91},
                }
            ],
        )

        observation, display_messages, metadata = normalize_tool_invoke_messages([response])

        self.assertIn("Retrieved resources:", observation)
        self.assertIn("Doc A", observation)
        self.assertIn("The answer is in this passage.", observation)
        self.assertEqual(display_messages, [response])
        self.assertEqual(metadata, {})

    def test_unknown_retriever_resource_shape_uses_json_fallback(self):
        response = SimpleNamespace(
            type="retriever_resources", message=SimpleNamespace(custom={"x": 1})
        )

        observation, display_messages, _ = normalize_tool_invoke_messages([response])

        self.assertIn("Retrieved resources:", observation)
        self.assertIn('"custom": {"x": 1}', observation)
        self.assertEqual(display_messages, [response])

    def test_log_messages_do_not_enter_observation(self):
        response = SimpleNamespace(type="log", message=SimpleNamespace(text="internal trace"))

        observation, display_messages, _ = normalize_tool_invoke_messages([response])

        self.assertEqual(observation, "")
        self.assertEqual(display_messages, [response])

    def test_deduplicates_semantically_equal_json_with_reordered_keys(self):
        first = SimpleNamespace(
            type="text", message=SimpleNamespace(text='{"result":[{"b":2,"a":1}]}')
        )
        second = SimpleNamespace(
            type="text", message=SimpleNamespace(text='{"result":[{"a":1,"b":2}]}')
        )

        observation, _, _ = normalize_tool_invoke_messages([first, second])

        self.assertEqual(observation, '{"result":[{"b":2,"a":1}]}')

    def test_deduplicates_repeated_full_tool_output_halves(self):
        responses = [
            SimpleNamespace(type="text", message=SimpleNamespace(text="summary")),
            SimpleNamespace(type="text", message=SimpleNamespace(text='{"b":2,"a":1}')),
            SimpleNamespace(type="text", message=SimpleNamespace(text="summary")),
            SimpleNamespace(type="text", message=SimpleNamespace(text='{"a":1,"b":2}')),
        ]

        observation, _, _ = normalize_tool_invoke_messages(responses)

        self.assertEqual(observation, 'summary\n{"b":2,"a":1}')

    def test_keeps_non_halved_repeated_tool_output(self):
        responses = [
            SimpleNamespace(type="text", message=SimpleNamespace(text="alpha")),
            SimpleNamespace(type="text", message=SimpleNamespace(text="beta")),
            SimpleNamespace(type="text", message=SimpleNamespace(text="alpha")),
        ]

        observation, _, _ = normalize_tool_invoke_messages(responses)

        self.assertEqual(observation, "alpha\nbeta\nalpha")


class InternalToolTests(unittest.TestCase):
    def test_internal_tools_update_tasks_and_render_skills(self):
        state = AgentState(
            skills=[
                {
                    "name": "brief",
                    "description": "Make a compact brief",
                    "body": "Summarize for {{audience}}: {{input}}",
                    "resources": [],
                    "source": "inline",
                }
            ],
            tasks=[],
        )
        executor = InternalToolExecutor(state)

        skill_result = executor.execute(
            "Skill", {"name": "brief", "args": {"audience": "architects", "input": "loop"}}
        )
        task_result = executor.execute("TaskCreate", {"title": "design loop", "status": "open"})
        executor.execute("TaskUpdate", {"id": task_result.metadata["task"]["id"], "status": "done"})

        self.assertEqual(skill_result.llm_observation, "Skill brief loaded.")
        self.assertTrue(skill_result.metadata["inject_user_message"])
        self.assertIn("Summarize for architects: loop", skill_result.metadata["injected_message"])
        self.assertEqual(skill_result.metadata["skill_name"], "brief")
        self.assertEqual(state.tasks[0]["status"], "completed")

    def test_skill_tool_rejects_local_kind_skills(self):
        state = AgentState(
            history=[],
            skills=[
                {
                    "name": "status",
                    "kind": "local",
                    "description": "查看状态",
                    "handler": lambda s, a: "ok",
                },
                {
                    "name": "brief",
                    "kind": "prompt",
                    "description": "brief",
                    "body": "Brief for {{topic}} with $ARGUMENTS.",
                    "source": "inline",
                },
            ],
            tasks=[],
        )
        executor = InternalToolExecutor(state)

        # prompt type still works
        prompt_result = executor.execute("Skill", {"name": "brief", "args": {"topic": "x"}})
        self.assertFalse(prompt_result.is_error)
        self.assertIn("Brief for x", prompt_result.metadata["injected_message"])

        # local type gets rejected
        local_result = executor.execute("Skill", {"name": "status"})
        self.assertTrue(local_result.is_error)
        self.assertIn("not available for model invocation", local_result.llm_observation)


class RegistryAndBudgetTests(unittest.TestCase):
    def test_external_tool_conflicts_are_namespaced_without_overriding_internal_tools(self):
        registry = ToolCatalog.create(
            external_tools=[fake_tool("TaskCreate", "web"), fake_tool("Search", "web")]
        )

        self.assertEqual(registry.resolve("TaskCreate").kind, "internal")
        self.assertEqual(registry.resolve("dify__web__TaskCreate").kind, "external")
        self.assertEqual(registry.resolve("Search").kind, "external")

    def test_budget_truncates_large_observations_without_orphaning_tool_pairs(self):
        messages = [
            {"role": "user", "content": "search"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "name": "Search", "arguments": {"q": "x"}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "Search", "content": "A" * 200},
        ]

        prepared, metadata = ContextBudget(
            max_history_messages=10, max_observation_chars=60
        ).prepare(messages)

        self.assertTrue(metadata["compressed"])
        self.assertIn("truncated", prepared[2]["content"])
        self.assertEqual(sanitize_history(prepared), prepared)


class LoopTests(unittest.TestCase):
    def test_loop_passes_external_tools_when_model_features_omit_tool_call(self):
        captured = {}
        external_prompt_tool = {
            "name": "get_time",
            "description": "Get current time",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }

        class FakeModel:
            def invoke(self, messages, tools, force_final=False):
                captured["tools"] = tools
                return AssistantTurn(text="done")

        config = AgentRunConfig(
            query="今天星期几",
            model_features=["agent-thought"],
            tool_call_supported=False,
            maximum_iterations=1,
        )
        state = AgentState()
        registry = ToolCatalog.create(
            external_tools=[{"tool_name": "get_time", "provider_id": "time_provider"}],
            external_prompt_tools=[external_prompt_tool],
        )

        loop = AgentLoop(
            config=config,
            state=state,
            registry=registry,
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(registry=registry, state=state),
        )
        list(loop.run())

        self.assertEqual(loop.final_result.answer, "done")
        tool_names = [
            tool["name"] if isinstance(tool, dict) else getattr(tool, "name", "")
            for tool in captured["tools"]
        ]
        self.assertIn("get_time", tool_names)

    def test_loop_appends_tool_result_for_each_assistant_tool_call(self):
        class FakeModel:
            def __init__(self):
                self.calls = 0

            def invoke(self, messages, tools, force_final=False):
                self.calls += 1
                if self.calls == 1:
                    return AssistantTurn(
                        text="",
                        tool_calls=[
                            ToolCall(
                                id="call_1",
                                name="TaskCreate",
                                arguments={"subject": "record project"},
                            )
                        ],
                    )
                return AssistantTurn(text="已记录。")

        config = AgentRunConfig(
            query="记住这个项目", instruction="你是系统助手", maximum_iterations=3
        )
        state = AgentState()
        registry = ToolCatalog.create()
        loop = AgentLoop(
            config=config,
            state=state,
            registry=registry,
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(registry=registry, state=state),
        )
        list(loop.run())
        result = loop.final_result

        self.assertEqual(result.answer, "已记录。")
        tool_messages = [m for m in result.history if m["role"] == "tool"]
        self.assertEqual(tool_messages[0]["tool_call_id"], "call_1")

    def test_loop_forces_final_answer_after_empty_post_tool_turn(self):
        calls = []

        class FakeModel:
            def invoke(self, messages, tools, force_final=False):
                calls.append({"force_final": force_final, "tools": tools})
                if len(calls) == 1:
                    return AssistantTurn(
                        text="我先查一下。",
                        tool_calls=[
                            ToolCall(
                                id="call_1", name="TaskList", arguments={"query": "上一个问题"}
                            )
                        ],
                    )
                if not force_final:
                    return AssistantTurn(text="")
                return AssistantTurn(text="你的上一个问题是：今天星期几？")

        config = AgentRunConfig(
            query="我上一个问题是什么", instruction="你是系统助手", maximum_iterations=3
        )
        state = AgentState()
        registry = ToolCatalog.create()
        loop = AgentLoop(
            config=config,
            state=state,
            registry=registry,
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(registry=registry, state=state),
        )
        list(loop.run())
        result = loop.final_result

        self.assertEqual(result.answer, "你的上一个问题是：今天星期几？")
        self.assertTrue(calls[-1]["force_final"])
        self.assertEqual(calls[-1]["tools"], [])


if __name__ == "__main__":
    unittest.main()
