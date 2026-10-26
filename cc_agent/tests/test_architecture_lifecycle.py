import unittest

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.messages import AgentRunResult
from cc_agent.core.state_backend import DifyStateBackend
from cc_agent.core.state_variable import decode_agent_state


class StateCommitTests(unittest.TestCase):
    def test_summary_describes_the_saved_snapshot_after_compaction(self):
        result = AgentRunResult(
            answer="done",
            history=[{"role": "user", "content": "x" * 2000} for _ in range(200)],
            tasks=[{"id": "1", "subject": "keep the task", "status": "pending"}],
            execution_metadata={"finish_reason": "final"},
        )

        DifyStateBackend(AgentRunConfig(), "conversation").commit(result)
        saved = decode_agent_state(result.encoded_agent_state)

        self.assertTrue(result.state_ref["compacted"])
        self.assertEqual(result.state_summary["history_message_count"], 4)
        self.assertEqual(len(saved.history_payload["messages"]), 4)
        self.assertEqual(result.state_summary["task_count"], len(saved.tasks))
        self.assertEqual(result.state_summary["revision"], saved.revision)


class FeatureScopeTests(unittest.TestCase):
    def test_old_memory_is_dropped_without_losing_the_pending_conversation(self):
        import base64
        import gzip
        import json

        from cc_agent.core.state_variable import AGENT_STATE_PREFIX, encode_agent_state

        question = {"id": "pending", "tool_call_id": "pending"}
        history = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "pending",
                        "type": "function",
                        "function": {"name": "UserPrompt", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "pending",
                "name": "UserPrompt",
                "content": "waiting",
                "metadata": {"requires_user_input": True},
            },
        ]
        payload = {
            "schema_version": 1,
            "revision": 5,
            "history": {"messages": history, "summary": "conversation", "version": 1},
            "memory": [{"id": "obsolete", "content": "retired memory"}],
            "tasks": [{"id": "task", "subject": "keep task"}],
            "permissions": {"allowed_tools": {"clock": "conversation"}},
            "active_skills": [{"name": "answers-ui", "summary": "keep skill"}],
            "last_execution_metadata": {"finish_reason": "awaiting_user", "question": question},
        }
        old_value = (
            AGENT_STATE_PREFIX
            + base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()
        )

        loaded = decode_agent_state(old_value)
        saved = decode_agent_state(encode_agent_state(loaded.bundle).value)

        self.assertNotIn("memory", saved.record)
        self.assertEqual(saved.history_payload["messages"], loaded.history_payload["messages"])
        for name in ("tasks", "permissions", "active_skills", "last_execution_metadata"):
            self.assertEqual(getattr(saved, name), payload[name])
        self.assertEqual(saved.history_payload["summary"], "conversation")

    def test_memory_tools_are_retired_while_tasks_remain_available(self):
        from cc_agent.core.messages import AgentState, ToolCall
        from cc_agent.core.tool_adapter import ToolAdapter
        from cc_agent.core.tool_catalog import ToolCatalog

        catalog = ToolCatalog.create()
        adapter = ToolAdapter(catalog, AgentState())
        for name in ("MemoryList", "MemorySearch", "MemorySave", "MemoryDelete"):
            with self.subTest(name=name):
                self.assertNotIn(name, catalog.names())
                self.assertTrue(adapter.execute(ToolCall("retired", name)).is_error)
        created = adapter.execute(ToolCall("task", "TaskCreate", {"subject": "ship changes"}))
        self.assertFalse(created.is_error)
        self.assertIn("ship changes", adapter.execute(ToolCall("list", "TaskList")).llm_observation)


class InterruptLifecycleTests(unittest.TestCase):
    def test_approved_legacy_confirmation_still_obeys_tool_policy(self):
        from types import SimpleNamespace

        from cc_agent.core.guards import ToolGuard, ToolGuardConfig
        from cc_agent.core.interrupts import UserInterrupts
        from cc_agent.core.messages import AgentState, ToolCall, ToolResult
        from cc_agent.core.tool_scheduler import SerialToolScheduler

        for policy in (ToolGuardConfig(denylist=["clock"]), ToolGuardConfig(allowlist=["other"])):
            with self.subTest(policy=policy):
                pending = {
                    "role": "tool",
                    "tool_call_id": "call",
                    "name": "clock",
                    "content": "waiting",
                    "metadata": {
                        "requires_user_input": True,
                        "pending_tool_execution": {"name": "clock", "arguments": {}},
                    },
                }
                state = AgentState(history=[pending])
                interrupts = UserInterrupts(state, confirmation_tools={"clock"})
                executions = []
                adapter = SimpleNamespace(
                    execute=lambda call: executions.append(call)
                    or ToolResult(call.id, call.name, "ok")
                )
                scheduler = SerialToolScheduler(
                    adapter, guard=ToolGuard(policy), interrupts=interrupts
                )
                config = AgentRunConfig(
                    user_prompt_response={"promptId": "call", "answer": "allow_once"}
                )

                resumed = interrupts.resume(
                    config,
                    {"finish_reason": "awaiting_user", "question": {"id": "call"}},
                    lambda call: scheduler.execute([call], 0)[0].result,
                )

                self.assertIsNone(resumed.error)
                self.assertTrue(resumed.result.metadata["guard_rejected"])
                self.assertTrue(pending["is_error"])
                self.assertEqual(executions, [])
                self.assertTrue(
                    interrupts.before_call(ToolCall("call", "clock")).metadata[
                        "requires_user_input"
                    ]
                )

    def test_wrong_interrupt_id_does_not_consume_the_response_or_execute(self):
        from cc_agent.core.interrupts import UserInterrupts
        from cc_agent.core.messages import AgentState

        config = AgentRunConfig(user_prompt_response={"promptId": "stale", "answer": "allow_once"})
        executions = []
        resumed = UserInterrupts(AgentState()).resume(
            config,
            {"finish_reason": "awaiting_user", "question": {"id": "current"}},
            lambda call: executions.append(call),
        )
        self.assertIn("does not match", resumed.error)
        self.assertIsNotNone(config.user_prompt_response)
        self.assertEqual(executions, [])

    def test_saved_conversation_allow_removes_later_confirmation(self):
        from types import SimpleNamespace

        from cc_agent.core.loop import AgentLoop
        from cc_agent.core.messages import AgentState, AssistantTurn, ToolCall
        from cc_agent.core.state_variable import AgentStateBundle, encode_agent_state
        from cc_agent.core.tool_adapter import ToolAdapter
        from cc_agent.core.tool_catalog import ToolCatalog

        encoded = encode_agent_state(
            AgentStateBundle(permissions={"allowed_tools": {"current_time": "conversation"}})
        )
        restored = DifyStateBackend(
            AgentRunConfig(agent_state_variable=encoded.value), "conv"
        ).load()
        state = AgentState(
            history=restored.history_state.messages, permissions=restored.permissions
        )
        tool_calls = []
        turns = iter(
            [
                AssistantTurn(tool_calls=[ToolCall("clock", "current_time")]),
                AssistantTurn(text="done"),
            ]
        )

        def invoke_tool(**kwargs):
            tool_calls.append(kwargs)
            return [SimpleNamespace(type="text", message=SimpleNamespace(text="12:00"))]

        catalog = ToolCatalog.create(external_tools=[{"name": "current_time", "provider": "clock"}])
        adapter = ToolAdapter(
            catalog, state, session=SimpleNamespace(tool=SimpleNamespace(invoke=invoke_tool))
        )
        loop = AgentLoop(
            AgentRunConfig(query="time", tool_confirmation_list=["current_time"]),
            state,
            catalog,
            SimpleNamespace(invoke=lambda *args, **kwargs: next(turns)),
            adapter,
        )

        list(loop.run())

        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "final")
        self.assertEqual(len(tool_calls), 1)


class RequestRecoveryTests(unittest.TestCase):
    def test_continuation_overflow_still_finishes_as_context_overflow(self):
        from cc_agent.core.loop import AgentLoop
        from cc_agent.core.messages import AgentState, AssistantTurn
        from cc_agent.core.tool_adapter import ToolAdapter
        from cc_agent.core.tool_catalog import ToolCatalog

        class Model:
            calls = 0

            def invoke(self, messages, tools, force_final=False):
                self.calls += 1
                if self.calls == 1:
                    return AssistantTurn(text="partial", finish_reason="length")
                raise RuntimeError("maximum context length exceeded")

        state, catalog, model = AgentState(), ToolCatalog.create(), Model()
        loop = AgentLoop(
            AgentRunConfig(query="hello"), state, catalog, model, ToolAdapter(catalog, state)
        )
        list(loop.run())
        self.assertEqual(model.calls, 3)
        self.assertEqual(loop.final_result.answer, "partial")
        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "context_overflow")
        self.assertEqual(loop.final_result.execution_metadata["context_retry_count"], 1)

    def test_persistent_context_overflow_stops_after_one_retry(self):
        from cc_agent.core.loop import AgentLoop
        from cc_agent.core.messages import AgentState
        from cc_agent.core.tool_adapter import ToolAdapter
        from cc_agent.core.tool_catalog import ToolCatalog

        class OverflowModel:
            calls = 0

            def invoke(self, messages, tools, force_final=False):
                self.calls += 1
                raise RuntimeError("maximum context length exceeded")

        state = AgentState()
        catalog = ToolCatalog.create()
        model = OverflowModel()
        loop = AgentLoop(
            AgentRunConfig(query="hello"), state, catalog, model, ToolAdapter(catalog, state)
        )

        list(loop.run())

        self.assertEqual(model.calls, 2)
        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "context_overflow")


class SkillLifecycleTests(unittest.TestCase):
    def test_restore_obeys_current_profile_and_denylist(self):
        from cc_agent.core.profiles import AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE
        from cc_agent.core.skill_catalog import SkillCatalog

        records = [
            {"name": "answers-ui", "summary": "old UI"},
            {"name": "missing", "summary": "removed"},
        ]
        for profile in (AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE):
            with self.subTest(profile=profile.name):
                config = AgentRunConfig.from_parameters(
                    {"skill_denylist": "answers-ui"}, strategy_profile=profile
                )
                self.assertEqual(SkillCatalog.build(config=config).restore_active(records), [])
        config = AgentRunConfig.from_parameters({}, strategy_profile=DIFY_STRATEGY_PROFILE)
        self.assertEqual(SkillCatalog.build(config=config).restore_active(records), [])

    def test_slash_and_model_activation_share_injection_and_active_summary(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from cc_agent.core.internal_tools import InternalToolExecutor
        from cc_agent.core.messages import AgentState, AssistantTurn
        from cc_agent.core.runtime import DifyAgentRuntime
        from cc_agent.core.skill_catalog import SkillCatalog

        yaml = "- name: report\n  description: report\n  instructions: Create $ARGUMENTS\n"
        config = AgentRunConfig.from_parameters({"app_skills_yaml": yaml})
        catalog = SkillCatalog.build(config=config)
        model_state = AgentState(skills=catalog.list_visible())
        prompts = []
        model = SimpleNamespace(
            invoke=lambda messages, *args, **kwargs: prompts.append(messages)
            or AssistantTurn(text="done")
        )
        strategy = SimpleNamespace(session=SimpleNamespace(conversation_id="conv"))
        with patch("cc_agent.core.runtime.DifyModelAdapter", return_value=model):
            events = list(
                DifyAgentRuntime(strategy).run(
                    {"query": "/report quarterly", "app_skills_yaml": yaml}
                )
            )
        saved = next(
            event["value"]
            for event in events
            if event.get("type") == "dify_variable" and event.get("name") == "agent_state"
        )
        result = InternalToolExecutor(model_state).execute(
            "Skill", {"name": "report", "args": {"_raw": "quarterly"}}, "skill"
        )
        self.assertFalse(result.is_error)
        self.assertTrue(
            any(
                message.get("content") == result.metadata["injected_message"]
                for message in prompts[0]
            )
        )
        self.assertEqual(model_state.active_skills, decode_agent_state(saved).active_skills)


class ArtifactLifecycleTests(unittest.TestCase):
    def test_dify_repeated_result_halves_stay_deduplicated_without_forwarding_artifacts_again(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from cc_agent.core.interrupts import UserInterrupts
        from cc_agent.core.messages import AgentState, AssistantTurn, ToolCall
        from cc_agent.core.profiles import AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE
        from cc_agent.core.runtime import DifyAgentRuntime
        from cc_agent.core.state_variable import AgentStateBundle, encode_agent_state

        displays = [
            SimpleNamespace(
                type="blob",
                message=SimpleNamespace(blob=b"download bytes"),
                meta={"filename": "report.pdf", "mime_type": "application/pdf"},
            ),
            SimpleNamespace(
                type="link", message=SimpleNamespace(text="https://example.com/report")
            ),
            SimpleNamespace(
                type="image", message=SimpleNamespace(text="https://example.com/chart.png")
            ),
        ]
        response = [
            SimpleNamespace(type="json", message=SimpleNamespace(json_object={"unique": "value"})),
            SimpleNamespace(type="text", message=SimpleNamespace(text="one observation")),
            *displays,
        ]
        for profile in (AGUI_STRATEGY_PROFILE, DIFY_STRATEGY_PROFILE):
            for resume in (False, True):
                with self.subTest(profile=profile.name, resume=resume):
                    call = ToolCall("download", "download_report")
                    state = AgentState()
                    pending = UserInterrupts(state, {call.name}).before_call(call)
                    history = [
                        {"role": "assistant", "content": "", "tool_calls": [call.to_history()]},
                        pending.to_history(),
                    ]
                    encoded = encode_agent_state(
                        AgentStateBundle(
                            history={"messages": history},
                            last_execution_metadata={
                                "finish_reason": "awaiting_user",
                                "question": {"id": call.id},
                            },
                        )
                    )
                    turns = iter(
                        ([AssistantTurn(tool_calls=[call])] if not resume else [])
                        + [AssistantTurn(text="done")]
                    )
                    invocations = []
                    strategy = SimpleNamespace(
                        session=SimpleNamespace(
                            conversation_id="conv",
                            tool=SimpleNamespace(
                                invoke=lambda **kwargs: invocations.append(kwargs) or response * 2
                            ),
                        )
                    )
                    parameters = {
                        "query": "download",
                        "tools": [{"name": call.name, "provider": "files"}],
                    }
                    if resume:
                        parameters.update(
                            agent_state=encoded.value,
                            user_prompt_response={"promptId": call.id, "answer": "allow_once"},
                        )
                    with patch(
                        "cc_agent.core.runtime.DifyModelAdapter",
                        return_value=SimpleNamespace(invoke=lambda *args, **kwargs: next(turns)),
                    ):
                        events = list(DifyAgentRuntime(strategy, profile).run(parameters))

                    self.assertEqual(len(invocations), 1)
                    self.assertFalse(
                        any(
                            event.get("type") in {"dify_blob", "dify_tool_message"}
                            for event in events
                        )
                    )
                    saved = next(
                        event["value"]
                        for event in events
                        if event.get("type") == "dify_variable"
                        and event.get("name") == "agent_state"
                    )
                    self.assertEqual(
                        decode_agent_state(saved).last_execution_metadata["finish_reason"], "final"
                    )
                    self.assertNotIn("download bytes", str(decode_agent_state(saved).record))
                    tool = next(
                        message
                        for message in decode_agent_state(saved).history_payload["messages"]
                        if message.get("role") == "tool"
                    )
                    self.assertEqual(tool["content"].count('"unique": "value"'), 1)
                    self.assertEqual(tool["content"].count("one observation"), 1)
