import unittest
from types import SimpleNamespace

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.loop import AgentLoop
from cc_agent.core.messages import AgentState, AssistantTurn, ToolCall
from cc_agent.core.model_adapter import DifyModelAdapter
from cc_agent.core.run_budget import RunBudget
from cc_agent.core.runtime import DifyAgentRuntime
from cc_agent.core.state_variable import AgentStateBundle, decode_agent_state, encode_agent_state
from cc_agent.core.tool_adapter import ToolAdapter
from cc_agent.core.tool_catalog import ToolCatalog


def chunk(arguments, *, call_id="call", index=0, name="echo"):
    return {
        "delta": {
            "message": {
                "tool_calls": [
                    {
                        "id": call_id,
                        "index": index,
                        "function": {"name": name, "arguments": arguments},
                    }
                ]
            }
        }
    }


class ModelArgumentContractTests(unittest.TestCase):
    def test_late_identity_is_retained_for_following_fragments(self):
        adapter = DifyModelAdapter(None, {})
        events = list(
            adapter.collect_stream_events(
                [
                    chunk('{"value":', call_id=""),
                    chunk("11", call_id="late", name=""),
                    chunk("}", call_id="", name=""),
                ]
            )
        )
        self.assertEqual(
            [(call.id, call.arguments) for call in events[-1].turn.tool_calls],
            [("late", {"value": 11})],
        )

    def test_ambiguous_fragment_is_rejected_before_any_tool_execution(self):
        adapter = DifyModelAdapter(None, {})
        ambiguous = {"delta": {"message": {"tool_calls": [{"function": {"arguments": "11}"}}]}}}
        with self.assertRaises(ValueError):
            list(
                adapter.collect_stream_events(
                    [
                        chunk('{"value":', call_id="a", index=0),
                        chunk('{"value":', call_id="b", index=1),
                        ambiguous,
                    ]
                )
            )

    def test_incremental_parameters_preserve_repeated_digits_and_first_chunk_identity(self):
        adapter = DifyModelAdapter(None, {})
        events = list(
            adapter.collect_stream_events(
                [
                    chunk('{"value":', name="echo"),
                    chunk("1", call_id="", name=""),
                    chunk("1", call_id="", name=""),
                    chunk("}", call_id="", name=""),
                ]
            )
        )
        self.assertEqual(len(events[-1].turn.tool_calls), 1)
        call = events[-1].turn.tool_calls[0]
        self.assertEqual(call.id, "call")
        self.assertEqual(call.arguments, {"value": 11})

    def test_snapshot_parameters_replace_previous_value(self):
        adapter = DifyModelAdapter(None, {}, tool_call_stream_mode="snapshot")
        events = list(
            adapter.collect_stream_events(
                [chunk('{"value":1}'), chunk('{"value":11}'), chunk('{"value":11}')]
            )
        )
        self.assertEqual(events[-1].turn.tool_calls[0].arguments, {"value": 11})

    def test_interleaved_calls_keep_ids_when_late_chunks_omit_them(self):
        adapter = DifyModelAdapter(None, {})
        events = list(
            adapter.collect_stream_events(
                [
                    chunk('{"value":', call_id="a", index=0),
                    chunk('{"value":', call_id="b", index=1),
                    chunk("11}", call_id="", index=0, name=""),
                    chunk("22}", call_id="", index=1, name=""),
                ]
            )
        )
        self.assertEqual(
            [(call.id, call.arguments) for call in events[-1].turn.tool_calls],
            [("a", {"value": 11}), ("b", {"value": 22})],
        )


class SkillContextContractTests(unittest.TestCase):
    def test_loaded_skill_has_one_complete_copy_in_each_model_request(self):
        marker = "WORKFLOW_MUST_VERIFY_EXPORT_JOB"
        state = AgentState(skills=[{"name": "workflow", "kind": "prompt", "body": marker}])
        catalog = ToolCatalog.create()
        calls = []

        def invoke(messages, tools, force_final=False):
            calls.append(messages)
            if len(calls) == 1:
                return AssistantTurn(tool_calls=[ToolCall("load", "Skill", {"name": "workflow"})])
            return AssistantTurn(text="done")

        loop = AgentLoop(
            AgentRunConfig(query="export"),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
        )
        list(loop.run())
        self.assertEqual(sum(str(m["content"]).count(marker) for m in calls[1]), 1)
        self.assertIn(marker, state.active_skills[0]["summary"])
        self.assertFalse(any(marker in str(m.get("content")) for m in loop.final_result.history))

    def test_fresh_skills_are_not_released_before_the_model_consumes_them(self):
        state = AgentState(
            skills=[
                {"name": name, "kind": "prompt", "body": name + "x" * 15000}
                for name in ("first", "second")
            ]
        )
        catalog = ToolCatalog.create()
        calls = []

        def invoke(messages, tools, force_final=False):
            calls.append(messages)
            return AssistantTurn(
                tool_calls=[ToolCall(name, "Skill", {"name": name}) for name in ("first", "second")]
            )

        loop = AgentLoop(
            AgentRunConfig(query="do both", max_total_context_tokens=10000),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
        )
        list(loop.run())
        self.assertEqual(len(calls), 1)
        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "context_overflow")
        self.assertEqual([skill["name"] for skill in state.active_skills], ["first", "second"])


class RunLifecycleContractTests(unittest.TestCase):
    def test_state_variable_is_emitted_before_completed_event(self):
        strategy = SimpleNamespace(
            session=SimpleNamespace(
                conversation_id="conv",
                model=SimpleNamespace(
                    llm=SimpleNamespace(
                        invoke=lambda **kw: iter([{"delta": {"message": {"content": "done"}}}])
                    )
                ),
            )
        )
        events = list(DifyAgentRuntime(strategy).run({"query": "hello", "run_id": "run"}))
        state_index = next(
            i
            for i, e in enumerate(events)
            if e.get("type") == "dify_variable" and e.get("name") == "agent_state"
        )
        finish_index = next(i for i, e in enumerate(events) if e.get("type") == "RUN_FINISHED")
        self.assertLess(state_index, finish_index)
        payload = events[finish_index]["result"]
        self.assertEqual(payload["execution_metadata"]["run_status"], "completed")
        self.assertEqual(payload["state_ref"]["delivery_status"], "emitted")
        self.assertIsNone(payload["state_ref"]["platform_persisted"])

    def test_tool_results_are_visible_before_next_tool_executes(self):
        state = AgentState()
        catalog = ToolCatalog.create()
        model_calls = []
        order = []

        def invoke(messages, tools, force_final=False):
            model_calls.append(messages)
            return (
                AssistantTurn(tool_calls=[ToolCall("a", "TaskList"), ToolCall("b", "TaskList")])
                if len(model_calls) == 1
                else AssistantTurn(text="done")
            )

        class Writer:
            def write_tool_call(self, call_id, *args, **kwargs):
                order.append("start:" + call_id)
                return []

            def write_tool_result(self, call_id, *args, **kwargs):
                order.append("result:" + call_id)
                return []

        loop = AgentLoop(
            AgentRunConfig(query="list"),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
            writer=Writer(),
        )
        list(loop.run())
        self.assertEqual(order, ["start:a", "result:a", "start:b", "result:b"])

    def test_tool_budget_stops_remaining_calls_and_keeps_history_paired(self):
        state = AgentState()
        catalog = ToolCatalog.create()
        calls = []

        def invoke(messages, tools, force_final=False):
            calls.append(messages)
            return AssistantTurn(
                tool_calls=[
                    ToolCall("a", "TaskCreate", {"subject": "first"}),
                    ToolCall("b", "TaskCreate", {"subject": "second"}),
                ]
            )

        loop = AgentLoop(
            AgentRunConfig(query="work", max_tool_calls=1),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
        )
        list(loop.run())
        self.assertEqual(len(state.tasks), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "budget_exhausted")
        results = [m for m in loop.final_result.history if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in results], ["a", "b"])
        self.assertEqual(results[1]["metadata"]["execution_outcome"], "not_executed")

    def test_context_retry_counts_against_total_model_budget(self):
        state = AgentState()
        catalog = ToolCatalog.create()
        calls = []

        def invoke(messages, tools, force_final=False):
            calls.append(messages)
            raise RuntimeError("maximum context length exceeded")

        loop = AgentLoop(
            AgentRunConfig(query="work", max_model_calls=1),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
        )
        list(loop.run())
        self.assertEqual(len(calls), 1)
        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "budget_exhausted")

    def test_summarization_shares_the_runtime_model_budget_and_records_usage(self):
        calls = []

        def invoke(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                message=SimpleNamespace(content="Earlier work summarized"),
                usage=SimpleNamespace(total_tokens=12, prompt_tokens=8, completion_tokens=4),
            )

        saved = encode_agent_state(
            AgentStateBundle(
                history={
                    "messages": [
                        {
                            "role": "user" if i % 2 == 0 else "assistant",
                            "content": f"old message {i}",
                        }
                        for i in range(12)
                    ]
                }
            )
        ).value
        strategy = SimpleNamespace(
            session=SimpleNamespace(
                conversation_id="conv", model=SimpleNamespace(llm=SimpleNamespace(invoke=invoke))
            )
        )
        events = list(
            DifyAgentRuntime(strategy).run(
                {
                    "query": "continue",
                    "agent_state": saved,
                    "runtime_config": {"max_history_messages": 4, "max_model_calls": 1},
                }
            )
        )
        result = next(e["result"] for e in events if e.get("type") == "RUN_FINISHED")
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["execution_metadata"]["run_status"], "budget_exhausted")
        self.assertEqual(result["execution_metadata"]["run_budget"]["total_tokens"], 12)

    def test_resumed_operation_uses_the_same_tool_budget_as_the_following_loop(self):
        pending = ToolCall("pending", "TaskCreate", {"subject": "approved"})
        saved = encode_agent_state(
            AgentStateBundle(
                history={
                    "messages": [
                        {"role": "assistant", "content": "", "tool_calls": [pending.to_history()]},
                        {
                            "role": "tool",
                            "content": "waiting",
                            "tool_call_id": "pending",
                            "name": "TaskCreate",
                            "metadata": {
                                "requires_user_input": True,
                                "pending_tool_execution": pending.to_history(),
                            },
                        },
                    ]
                },
                last_execution_metadata={
                    "finish_reason": "awaiting_user",
                    "question": {"id": "pending", "question": "Continue?"},
                },
            )
        ).value
        strategy = SimpleNamespace(
            session=SimpleNamespace(
                conversation_id="conv",
                model=SimpleNamespace(
                    llm=SimpleNamespace(
                        invoke=lambda **kw: iter(
                            [
                                {
                                    "delta": {
                                        "message": {
                                            "tool_calls": [
                                                {
                                                    "id": "new",
                                                    "function": {
                                                        "name": "TaskCreate",
                                                        "arguments": '{"subject":"extra"}',
                                                    },
                                                }
                                            ]
                                        }
                                    }
                                }
                            ]
                        )
                    )
                ),
            )
        )
        events = list(
            DifyAgentRuntime(strategy).run(
                {
                    "query": "allow_once",
                    "agent_state": saved,
                    "runtime_config": {"max_tool_calls": 1},
                }
            )
        )
        encoded = next(e["value"] for e in events if e.get("name") == "agent_state")
        loaded = decode_agent_state(encoded)
        self.assertEqual([task["subject"] for task in loaded.tasks], ["approved"])
        self.assertEqual(loaded.last_execution_metadata["run_budget"]["tool_calls"], 1)
        self.assertEqual(loaded.last_execution_metadata["finish_reason"], "budget_exhausted")

    def test_elapsed_budget_stops_tool_execution_after_a_slow_model_call(self):
        state = AgentState()
        catalog = ToolCatalog.create()
        now = [0.0]
        calls = []
        budget = RunBudget(max_run_seconds=1, clock=lambda: now[0])

        def invoke(messages, tools, force_final=False):
            calls.append(messages)
            now[0] = 2
            return AssistantTurn(tool_calls=[ToolCall("a", "TaskList")])

        loop = AgentLoop(
            AgentRunConfig(query="list"),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
            run_budget=budget,
        )
        list(loop.run())
        self.assertEqual(len(calls), 1)
        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "budget_exhausted")
        self.assertEqual(
            loop.final_result.history[-1]["metadata"]["execution_outcome"], "not_executed"
        )

    def test_reported_token_budget_stops_tools_after_the_model_has_consumed_it(self):
        state = AgentState()
        catalog = ToolCatalog.create()
        model = SimpleNamespace(
            invoke=lambda *args, **kw: AssistantTurn(
                tool_calls=[ToolCall("a", "TaskCreate", {"subject": "work"})],
                usage={"total_tokens": 100},
            )
        )
        loop = AgentLoop(
            AgentRunConfig(query="work", max_run_tokens=100),
            state,
            catalog,
            model,
            ToolAdapter(catalog, state),
        )
        list(loop.run())
        self.assertEqual(state.tasks, [])
        self.assertEqual(loop.final_result.execution_metadata["run_budget"]["total_tokens"], 100)
        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "budget_exhausted")
