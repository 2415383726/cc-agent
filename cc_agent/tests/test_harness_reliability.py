import copy
import random
import string
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.context_budget import ContextBudget, estimate_context_tokens
from cc_agent.core.interrupts import UserInterrupts
from cc_agent.core.loop import AgentLoop
from cc_agent.core.messages import (
    AgentRunResult,
    AgentState,
    AssistantTurn,
    ToolCall,
    ToolResult,
    assistant_message,
)
from cc_agent.core.profiles import strategy_profile_for_output
from cc_agent.core.protocol_renderer import ProtocolRenderer
from cc_agent.core.result_budget import ResultBudget
from cc_agent.core.runtime import DifyAgentRuntime
from cc_agent.core.skill_catalog import SkillCatalog
from cc_agent.core.state_backend import DifyStateBackend
from cc_agent.core.state_variable import decode_agent_state
from cc_agent.core.tool_adapter import ToolAdapter
from cc_agent.core.tool_catalog import ToolCatalog, ToolSpec
from cc_agent.core.tool_scheduler import SerialToolScheduler


class SkillActivationTests(unittest.TestCase):
    def test_user_cannot_invoke_a_model_only_skill_with_a_slash_command(self):
        calls = []
        strategy = SimpleNamespace(
            session=SimpleNamespace(
                conversation_id="conversation",
                model=SimpleNamespace(llm=SimpleNamespace(invoke=lambda **kw: calls.append(kw))),
            )
        )
        events = list(
            DifyAgentRuntime(strategy, strategy_profile_for_output("agui")).run(
                {
                    "query": "/workflow",
                    "run_id": "slash-run",
                    "app_skills_yaml": "- name: workflow\n  description: Test\n  instructions: Do work\n  user_invocable: false\n",
                }
            )
        )
        failures = [
            event["payload"]
            for event in events
            if event.get("type") == "dify_json" and event["payload"].get("event") == "agent_failed"
        ]
        self.assertEqual(calls, [])
        self.assertEqual(failures[0]["code"], "skill_invocation_forbidden")

    def test_changed_or_incomplete_skill_instructions_are_available_for_reloading_after_save(self):
        for body in ("Current instructions.", "x" * 6000 + "ESSENTIAL_FINAL_RULE"):
            with self.subTest(long=len(body) > 5000):
                skill = {"name": "workflow", "kind": "prompt", "body": body}
                state = AgentState(skills=[skill])
                result = ToolAdapter(ToolCatalog.create(), state).execute(
                    ToolCall("load", "Skill", {"name": "workflow"})
                )
                self.assertFalse(result.is_error)
                saved = AgentRunResult(
                    "done", [], [], {"finish_reason": "final"}, active_skills=state.active_skills
                )
                DifyStateBackend(AgentRunConfig(), "conversation").commit(saved)
                records = decode_agent_state(saved.encoded_agent_state).active_skills
                current = SkillCatalog(prompt_skills=[skill])
                if len(body) <= 5000:
                    self.assertEqual(current.restore_active(records)[0]["name"], "workflow")
                else:
                    self.assertEqual(current.restore_active(records), [])
                updated = SkillCatalog(
                    prompt_skills=[{**skill, "body": "Changed workflow instructions."}]
                )
                self.assertEqual(updated.restore_active(records), [])

    def test_model_cannot_activate_a_manual_only_skill(self):
        state = AgentState(
            skills=[
                {
                    "name": "manual",
                    "kind": "prompt",
                    "body": "Do private work.",
                    "disable_model_invocation": True,
                }
            ]
        )
        result = ToolAdapter(ToolCatalog.create(), state).execute(
            ToolCall("load", "Skill", {"name": "manual"})
        )
        self.assertTrue(result.is_error)
        self.assertEqual(state.active_skills, [])


class RuntimeFailureTests(unittest.TestCase):
    def test_runtime_does_not_publish_success_or_invalid_state_after_an_oversized_interrupt(self):
        import json

        question = "".join(random.Random(42).choices(string.ascii_letters, k=100000))
        chunk = SimpleNamespace(
            delta=SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            index=0,
                            id="large-prompt",
                            function=SimpleNamespace(
                                name="UserPrompt", arguments=json.dumps({"question": question})
                            ),
                        )
                    ],
                )
            )
        )
        strategy = SimpleNamespace(
            session=SimpleNamespace(
                conversation_id="conversation",
                model=SimpleNamespace(llm=SimpleNamespace(invoke=lambda **kw: iter([chunk]))),
            )
        )
        events = list(
            DifyAgentRuntime(strategy, strategy_profile_for_output("agui")).run(
                {"query": "Ask", "run_id": "large-state"}
            )
        )
        payloads = [event["payload"] for event in events if event.get("type") == "dify_json"]
        failures = [payload for payload in payloads if payload.get("event") == "agent_failed"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["code"], "state_save_failed")
        self.assertFalse(failures[0]["state_ref"]["persisted"])
        self.assertFalse(any(payload.get("event") == "agent_finished" for payload in payloads))
        self.assertFalse(any(event.get("type") == "RUN_FINISHED" for event in events))
        self.assertFalse(
            any(
                event.get("type") == "dify_variable" and event.get("name") == "agent_state"
                for event in events
            )
        )

    def test_external_tool_failure_does_not_echo_runtime_credentials(self):
        secret = "business-token-must-not-leak"
        catalog = ToolCatalog.create(
            external_tools=[
                {"name": "submit", "provider": "business", "runtime_parameters": {"token": secret}}
            ]
        )

        def invoke(**kwargs):
            raise RuntimeError(f"Connection failed with Authorization: {secret}")

        adapter = ToolAdapter(
            catalog, AgentState(), session=SimpleNamespace(tool=SimpleNamespace(invoke=invoke))
        )
        result = adapter.execute(ToolCall("submit", "submit", {"value": 1}))

        self.assertTrue(result.is_error)
        self.assertNotIn(secret, repr(result))
        self.assertEqual(result.metadata["execution_outcome"], "unknown")
        self.assertEqual(result.metadata["error_code"], "external_tool_failed")

    def test_unhandled_failures_emit_safe_json_in_both_output_strategies(self):
        import json

        secret = "credential-must-not-leak"
        for protocol in ("agui", "dify_native"):
            with self.subTest(protocol=protocol):
                chunk = SimpleNamespace(
                    delta=SimpleNamespace(
                        message=SimpleNamespace(content="Ready", tool_calls=[]),
                        usage={"total_tokens": secret},
                        finish_reason="stop",
                    )
                )
                strategy = SimpleNamespace(
                    session=SimpleNamespace(
                        conversation_id="conversation",
                        model=SimpleNamespace(
                            llm=SimpleNamespace(invoke=lambda chunk=chunk, **kw: iter([chunk]))
                        ),
                    )
                )
                events = list(
                    DifyAgentRuntime(strategy, strategy_profile_for_output(protocol)).run(
                        {"query": "Hi", "run_id": "run-safe"}
                    )
                )
                failures = [
                    event["payload"]
                    for event in events
                    if event.get("type") == "dify_json"
                    and event["payload"].get("event") == "agent_failed"
                ]
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0]["run_id"], "run-safe")
                self.assertEqual(failures[0]["code"], "runtime_failed")
                self.assertNotIn(secret, json.dumps(events, default=str))


class StateCapacityTests(unittest.TestCase):
    def test_oversized_pending_operation_is_not_reported_as_persisted_or_silently_modified(self):
        body = "".join(
            random.Random(20261027).choices(string.ascii_letters + string.digits, k=40000)
        )
        call = ToolCall("pending", "send_report", {"body": body})
        interrupts = UserInterrupts(AgentState(), {"send_report"})
        pending = interrupts.before_call(call)
        history = [assistant_message(AssistantTurn(tool_calls=[call])), pending.to_history()]
        result = AgentRunResult(
            "Confirm",
            history,
            [],
            {
                "finish_reason": "awaiting_user",
                "question": interrupts.question_from_result(pending),
            },
        )
        DifyStateBackend(AgentRunConfig(), "conversation").commit(result)

        self.assertFalse(result.state_ref["persisted"])
        self.assertEqual(result.state_ref["storage_error"], "agent_state_exceeds_variable_limit")
        self.assertEqual(result.encoded_agent_state, "")
        self.assertEqual(
            result.history[1]["metadata"]["pending_tool_execution"]["arguments"]["body"], body
        )


class SkillResourcePagingTests(unittest.TestCase):
    def test_batch_shrinking_updates_each_resource_cursor_to_the_delivered_content(self):
        source = "ABCDEFGHIJ" * 200
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text("Read refs", encoding="utf-8")
            (root / "reference.md").write_text(source, encoding="utf-8")
            state = AgentState(skills=[{"name": "refs", "path": str(root / "SKILL.md")}])
            catalog = ToolCatalog.create()
            scheduler = SerialToolScheduler(ToolAdapter(catalog, state), ResultBudget(400))
            results = scheduler.execute(
                [
                    ToolCall(str(i), "SkillReadResource", {"skill": "refs", "path": "reference.md"})
                    for i in range(3)
                ],
                1,
            )
            self.assertLessEqual(sum(len(item.result.llm_observation) for item in results), 800)
            for item in results:
                page = item.result.metadata["resource_page"]
                delivered = item.result.llm_observation.split("\n\n", 1)[1]
                self.assertEqual(delivered, source[: page["next_offset"]])

    def test_resource_can_be_read_completely_through_the_final_result_budget(self):
        source = "你好\n" * 400 + "MIDDLE_RULE\n" + "x" * 1200 + "\nFINAL_RULE"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text("Read reference.md", encoding="utf-8")
            (root / "reference.md").write_text(source, encoding="utf-8")
            state = AgentState(skills=[{"name": "refs", "path": str(root / "SKILL.md")}])
            catalog = ToolCatalog.create()
            scheduler = SerialToolScheduler(ToolAdapter(catalog, state), ResultBudget(400))
            offset = 0
            received = []
            for turn in range(50):
                result = scheduler.execute(
                    [
                        ToolCall(
                            f"read-{turn}",
                            "SkillReadResource",
                            {
                                "skill": "refs",
                                "path": "reference.md",
                                "offset": offset,
                                "limit": 5000,
                            },
                        )
                    ],
                    turn,
                )[0].result
                self.assertFalse(result.is_error)
                self.assertLessEqual(len(result.llm_observation), 400)
                page = result.metadata["resource_page"]
                received.append(result.llm_observation.split("\n\n", 1)[1])
                if page["next_offset"] is None:
                    break
                self.assertGreater(page["next_offset"], offset)
                offset = page["next_offset"]
            else:
                self.fail("Resource paging did not finish")
            self.assertEqual("".join(received), source)


class ToolBatchHistoryTests(unittest.TestCase):
    def test_interrupt_finishes_unexecuted_tail_without_running_it(self):
        state = AgentState()
        catalog = ToolCatalog.create()
        loop = AgentLoop(
            AgentRunConfig(query="Track work", tool_confirmation_list=["TaskCreate"]),
            state,
            catalog,
            SimpleNamespace(
                invoke=lambda *a, **kw: AssistantTurn(
                    tool_calls=[
                        ToolCall("pending", "TaskCreate", {"subject": "Needs approval"}),
                        ToolCall("tail", "TaskList"),
                    ]
                )
            ),
            ToolAdapter(catalog, state),
            writer=ProtocolRenderer("agui", "thread", "run"),
        )
        events = list(loop.run())

        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "awaiting_user")
        self.assertEqual(state.tasks, [])
        self.assertEqual(
            [event["toolCallId"] for event in events if event.get("type") == "TOOL_CALL_RESULT"],
            ["pending", "tail"],
        )
        history = [message for message in loop.final_result.history if message["role"] == "tool"]
        self.assertEqual([message["tool_call_id"] for message in history], ["pending", "tail"])
        self.assertTrue(history[-1]["metadata"]["skipped"])

    def test_skill_injection_keeps_all_executed_results_paired(self):
        state = AgentState(
            skills=[{"name": "workflow", "kind": "prompt", "body": "Use the task tools."}]
        )
        catalog = ToolCatalog.create()
        prompts = []

        def invoke(messages, tools, force_final=False):
            prompts.append(copy.deepcopy(messages))
            if len(prompts) == 1:
                return AssistantTurn(
                    tool_calls=[
                        ToolCall("skill", "Skill", {"name": "workflow"}),
                        ToolCall("task", "TaskCreate", {"subject": "Keep this task"}),
                    ]
                )
            return AssistantTurn(text="done")

        loop = AgentLoop(
            AgentRunConfig(query="Track the work"),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
        )
        list(loop.run())

        self.assertEqual(len(state.tasks), 1)
        self.assertEqual(
            [message["tool_call_id"] for message in prompts[1] if message["role"] == "tool"],
            ["skill", "task"],
        )
        self.assertEqual(
            [
                message["tool_call_id"]
                for message in loop.final_result.history
                if message["role"] == "tool"
            ],
            ["skill", "task"],
        )


class HarnessBudgetTests(unittest.TestCase):
    def test_a_long_single_request_can_summarize_consumed_tool_cycles_and_keep_the_query(self):
        prompts = []
        summaries = []

        def invoke(messages, tools, force_final=False):
            prompts.append(copy.deepcopy(messages))
            if len(prompts) < 4:
                return AssistantTurn(tool_calls=[ToolCall(str(len(prompts)), "TaskList")])
            return AssistantTurn(text="Done")

        def summarize(messages, existing_summary=""):
            summaries.append(copy.deepcopy(messages))
            return "Earlier tool cycles completed."

        state = AgentState()
        catalog = ToolCatalog.create()
        loop = AgentLoop(
            AgentRunConfig(query="CURRENT_REQUEST", max_history_messages=4),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
            summarizer=summarize,
        )
        list(loop.run())
        self.assertTrue(summaries)
        self.assertTrue(any(message.get("role") == "tool" for message in summaries[0]))
        for prompt in prompts:
            self.assertTrue(any(message.get("content") == "CURRENT_REQUEST" for message in prompt))
        self.assertEqual(loop.final_result.answer, "Done")

    def test_replacement_summary_with_a_chinese_tail_stays_inside_its_token_budget(self):
        history = [{"role": "user", "content": f"fact {index}"} for index in range(20)]
        result = ContextBudget(max_history_messages=4).compact_history(
            history, summarizer=lambda *args, **kw: "a" * 1000 + "中" * 1000, max_summary_tokens=100
        )
        self.assertLessEqual(estimate_context_tokens(result.summary), 100)

    def test_snipping_only_keeps_the_retained_source_available_for_a_later_summary(self):
        marker = "MIDDLE_FACT"
        history = [
            {"role": "user", "content": "Research"},
            assistant_message(AssistantTurn(tool_calls=[ToolCall("old", "lookup")])),
            ToolResult("old", "lookup", "x" * 12000 + marker + "z" * 12000).to_history(),
            *[{"role": "assistant", "content": "n" * 1500} for _ in range(8)],
            {"role": "user", "content": "Continue"},
        ]
        budget = ContextBudget(max_total_context_tokens=8192)
        first = budget.compact_history(history)
        self.assertEqual(first.metadata["summarized_messages"], 0)
        captured = []

        def summarize(messages, existing_summary=""):
            captured.extend(messages)
            return "Summary"

        budget.compact_history(first.messages, force=True, summarizer=summarize)
        self.assertTrue(any(marker in message.get("content", "") for message in captured))

    def test_adding_english_instructions_does_not_reduce_the_same_chinese_input_estimate(self):
        chinese = "中" * 5000
        self.assertGreater(
            estimate_context_tokens("a" * 3000 + chinese), estimate_context_tokens(chinese)
        )

    def test_context_pressure_shrinks_consumed_results_without_overwriting_sources(self):
        messages = [
            {"role": "user", "content": "Old query"},
            assistant_message(AssistantTurn(tool_calls=[ToolCall("old", "lookup")])),
            ToolResult("old", "lookup", "o" * 7000).to_history(),
            {"role": "assistant", "content": "I have used the old result."},
            {"role": "user", "content": "New query"},
            assistant_message(AssistantTurn(tool_calls=[ToolCall("new", "lookup")])),
            ToolResult("new", "lookup", "n" * 7000).to_history(),
        ]
        budget = ContextBudget(max_total_context_tokens=8192)
        projected, metadata = budget.prepare(messages)
        results = {
            message["tool_call_id"]: message["content"]
            for message in projected
            if message["role"] == "tool"
        }

        self.assertLessEqual(len(results["old"]), 800)
        self.assertEqual(results["new"], "n" * 7000)
        self.assertEqual(messages[2]["content"], "o" * 7000)
        self.assertEqual(metadata["masked_observations"], 1)

    def test_summary_sees_retained_tool_content_before_old_result_snipping(self):
        marker = "ESSENTIAL_MIDDLE_FACT"
        history = [
            {"role": "user", "content": "Research"},
            assistant_message(AssistantTurn(tool_calls=[ToolCall("old", "lookup")])),
            ToolResult("old", "lookup", "x" * 3000 + marker + "z" * 3000).to_history(),
        ]
        for index in range(8):
            history.extend(
                [
                    {"role": "user", "content": f"fact {index}" + "n" * 400},
                    {"role": "assistant", "content": "noted " * 50},
                ]
            )
        captured = []

        def summarize(messages, existing_summary=""):
            captured.extend(messages)
            return "Research completed."

        state = AgentState(history=history)
        catalog = ToolCatalog({})
        loop = AgentLoop(
            AgentRunConfig(query="Continue", max_history_messages=4),
            state,
            catalog,
            SimpleNamespace(invoke=lambda *a, **kw: AssistantTurn(text="done")),
            ToolAdapter(catalog, state),
            summarizer=summarize,
        )
        list(loop.run())

        self.assertTrue(any(marker in message.get("content", "") for message in captured))

    def test_compaction_replaces_a_superseded_decision_instead_of_restoring_it(self):
        state = AgentState(
            summary="Old decision: deploy A.",
            history=[{"role": "user", "content": f"fact {index}"} for index in range(20)],
        )
        prompts = []
        catalog = ToolCatalog({})
        loop = AgentLoop(
            AgentRunConfig(query="Deploy B instead of A", max_history_messages=4),
            state,
            catalog,
            SimpleNamespace(
                invoke=lambda messages, tools, **kw: prompts.append(copy.deepcopy(messages))
                or AssistantTurn(text="done")
            ),
            ToolAdapter(catalog, state),
            summarizer=lambda messages, existing_summary="": "Current decision: deploy B. A was cancelled.",
        )
        list(loop.run())

        self.assertEqual(loop.final_result.summary, "Current decision: deploy B. A was cancelled.")
        self.assertFalse(
            any("Old decision: deploy A." in message.get("content", "") for message in prompts[0])
        )

    def test_large_latest_result_keeps_current_request_while_old_prefix_is_summarized(self):
        state = AgentState(
            history=[{"role": "user", "content": f"old-{i}:" + "x" * 250} for i in range(20)]
        )
        prompts = []
        summarized = []

        def invoke(messages, tools, force_final=False):
            prompts.append(copy.deepcopy(messages))
            if len(prompts) == 1:
                return AssistantTurn(tool_calls=[ToolCall("search", "Search")])
            return AssistantTurn(text="done")

        def summarize(messages, existing_summary=""):
            summarized.extend(messages)
            return "Older user facts summarized."

        entity = {"name": "Search", "provider": "demo"}
        catalog = ToolCatalog(
            {
                "Search": ToolSpec(
                    "Search",
                    "external",
                    "Search",
                    entity=entity,
                    prompt_tool={
                        "name": "Search",
                        "description": "Search",
                        "parameters": {"type": "object"},
                    },
                )
            }
        )
        session = SimpleNamespace(
            tool=SimpleNamespace(
                invoke=lambda **kw: [
                    SimpleNamespace(type="text", message=SimpleNamespace(text="z" * 8000))
                ]
            )
        )
        loop = AgentLoop(
            AgentRunConfig(query="CURRENT_QUERY", max_total_context_tokens=8192),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state, session=session),
            summarizer=summarize,
        )
        list(loop.run())

        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "final")
        self.assertEqual(len(prompts), 2)
        self.assertTrue(summarized)
        self.assertNotIn("CURRENT_QUERY", [message.get("content") for message in summarized])
        self.assertIn("CURRENT_QUERY", [message.get("content") for message in prompts[1]])
        self.assertEqual(
            next(message["content"] for message in prompts[1] if message["role"] == "tool"),
            "z" * 8000,
        )

    def test_unusable_fixed_context_preserves_history_without_spending_summary_calls(self):
        history = [{"role": "user", "content": f"Old fact {index}"} for index in range(30)]
        state = AgentState(history=copy.deepcopy(history))
        summaries = []
        calls = []
        catalog = ToolCatalog(
            {
                "lookup": ToolSpec(
                    "lookup",
                    "external",
                    "lookup",
                    prompt_tool={
                        "name": "lookup",
                        "description": "x" * 30000,
                        "parameters": {"type": "object"},
                    },
                )
            }
        )
        loop = AgentLoop(
            AgentRunConfig(query="Current request", max_total_context_tokens=4096),
            state,
            catalog,
            SimpleNamespace(invoke=lambda *a, **k: calls.append(True)),
            ToolAdapter(catalog, state),
            summarizer=lambda messages, existing_summary="": summaries.append(messages)
            or "summary",
        )
        list(loop.run())

        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "context_overflow")
        self.assertEqual(calls, [])
        self.assertEqual(summaries, [])
        self.assertEqual(loop.final_result.history[:-1], history)

    def test_display_output_does_not_overflow_a_small_model_request_or_repeat_in_history(self):
        result = ResultBudget(1000).apply(
            ToolResult(
                "lookup", "lookup", "x" * 200000, metadata={"output": {"rows": "x" * 200000}}
            )
        )
        state = AgentState(
            history=[
                {"role": "user", "content": "Count matching rows"},
                assistant_message(AssistantTurn(tool_calls=[ToolCall("lookup", "lookup")])),
                result.to_history(),
            ]
        )
        prompts = []

        def invoke(messages, tools, force_final=False):
            prompts.append(copy.deepcopy(messages))
            return AssistantTurn(text="There are matching rows.")

        catalog = ToolCatalog({})
        loop = AgentLoop(
            AgentRunConfig(
                query="Continue", max_total_context_tokens=32000, max_observation_chars=1000
            ),
            state,
            catalog,
            SimpleNamespace(invoke=invoke),
            ToolAdapter(catalog, state),
        )
        list(loop.run())

        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "final")
        self.assertEqual(len(prompts), 1)
        tool_message = next(message for message in prompts[0] if message["role"] == "tool")
        self.assertLessEqual(len(tool_message["content"]), 1000)
        self.assertNotIn("metadata", tool_message)
        saved_tool = next(
            message for message in loop.final_result.history if message["role"] == "tool"
        )
        self.assertNotIn("output", saved_tool.get("metadata", {}))
        self.assertEqual(len(result.metadata["output"]["rows"]), 200000)
