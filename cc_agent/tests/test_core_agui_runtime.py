import unittest
from types import SimpleNamespace

from cc_agent.core.messages import AgentRunResult
from cc_agent.core.runtime import DifyAgentRuntime
from cc_agent.core import runtime as runtime_module
from cc_agent.core.state_variable import AgentStateBundle, encode_agent_state


class RuntimeAgUiBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.original_loop = runtime_module.AgentLoop

    def tearDown(self):
        runtime_module.AgentLoop = self.original_loop

    def test_run_yields_agui_events_and_persists_before_finished(self):
        captured = {}

        class FakeLoop:
            def __init__(self, **kwargs):
                captured["writer"] = kwargs["writer"]
                captured["state"] = kwargs["state"]
                self.final_result = None

            def run(self):
                yield from captured["writer"].write_text_delta("ok")
                self.final_result = AgentRunResult(
                    answer="ok",
                    history=[{"role": "assistant", "content": "ok"}],
                    memory=[],
                    tasks=[],
                    execution_metadata={"finish_reason": "final"},
                )

        runtime_module.AgentLoop = FakeLoop
        session = SimpleNamespace(
            app_id="app-1",
            session_id="session-1",
            conversation_id="conv-1",
            storage=SimpleNamespace(data={}),
        )
        strategy = SimpleNamespace(
            session=session,
            runtime=SimpleNamespace(user_id="user-1"),
            _init_prompt_tools=lambda tools: [],
        )

        events = list(DifyAgentRuntime(strategy).run({"query": "hello", "conversation_id": "conv-1"}))
        run_finished = next(event for event in events if event.get("type") == "RUN_FINISHED")

        self.assertEqual(events[0]["type"], "RUN_STARTED")
        self.assertEqual(run_finished["result"]["state_ref"]["conversation_id"], "conv-1")
        self.assertTrue(run_finished["result"]["state_ref"]["persisted"])
        self.assertEqual(run_finished["result"]["state_ref"]["variable_name"], "agent_state")
        self.assertIn("state_summary", run_finished["result"])
        self.assertTrue(any(event.get("type") == "dify_json" for event in events))
        self.assertTrue(any(event.get("type") == "dify_variable" and event.get("name") == "agent_state" for event in events))

    def test_run_without_conversation_id_uses_temporary_state_and_skips_persist(self):
        captured = {}

        class FakeLoop:
            def __init__(self, **kwargs):
                captured["state"] = kwargs["state"]
                captured["writer"] = kwargs["writer"]
                self.final_result = None

            def run(self):
                self.final_result = AgentRunResult(
                    answer="ok",
                    history=[],
                    memory=[],
                    tasks=[],
                    execution_metadata={"finish_reason": "final"},
                )
                return
                yield

        runtime_module.AgentLoop = FakeLoop
        storage = SimpleNamespace(data={})
        session = SimpleNamespace(app_id="app-1", session_id="session-1", conversation_id="", storage=storage)
        strategy = SimpleNamespace(
            session=session,
            runtime=SimpleNamespace(user_id="user-1"),
            _init_prompt_tools=lambda tools: [],
        )

        events = list(DifyAgentRuntime(strategy).run({"query": "hello"}))
        run_finished = next(event for event in events if event.get("type") == "RUN_FINISHED")

        self.assertEqual(captured["state"].history, [])
        self.assertEqual(storage.data, {})
        self.assertTrue(run_finished["result"]["state_ref"]["persisted"])
        self.assertEqual(run_finished["result"]["state_ref"]["backend"], "conversation_variable")
        self.assertEqual(run_finished["result"]["state_ref"]["variable_name"], "agent_state")
        self.assertTrue(any(event.get("type") == "dify_json" for event in events))

    def test_run_does_not_fallback_to_state_id_when_conversation_key_is_empty(self):
        captured = {}

        class FakeLoop:
            def __init__(self, **kwargs):
                captured["state"] = kwargs["state"]
                captured["writer"] = kwargs["writer"]
                self.final_result = None

            def run(self):
                state = captured["state"]
                self.final_result = AgentRunResult(
                    answer="ok",
                    history=state.history,
                    memory=state.memory,
                    tasks=state.tasks,
                    execution_metadata={"finish_reason": "final"},
                    summary=state.summary,
                )
                return
                yield

        runtime_module.AgentLoop = FakeLoop
        storage = SimpleNamespace(data={})
        session = SimpleNamespace(app_id="app-1", session_id="session-1", conversation_id="", storage=storage)
        strategy = SimpleNamespace(
            session=session,
            runtime=SimpleNamespace(user_id="user-1"),
            _init_prompt_tools=lambda tools: [],
        )

        events = list(DifyAgentRuntime(strategy).run({
            "query": "hello",
            "inputs": {"state_id": "legacy-state"},
        }))

        self.assertEqual(captured["state"].history, [])
        run_finished = next(event for event in events if event.get("type") == "RUN_FINISHED")
        self.assertEqual(run_finished["result"]["state_ref"]["conversation_id"], "")
        self.assertTrue(run_finished["result"]["state_ref"]["persisted"])
        self.assertEqual(run_finished["result"]["state_ref"]["backend"], "conversation_variable")
        self.assertEqual(run_finished["result"]["state_ref"]["variable_name"], "agent_state")
        self.assertEqual(storage.data, {})

    def test_external_tool_permission_decision_activity_is_emitted_once(self):
        history = [{
            "role": "tool", "name": "read_file", "tool_call_id": "call-1",
            "metadata": {
                "permission_decision": "allow_conversation",
                "permission_request": {"tool_name": "read_file"},
            },
        }]
        writer = runtime_module._make_writer("agui", "conv-1", "run-1")
        events = runtime_module._permission_decision_activities(writer, history)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["activityType"], "cc_agent.permission_decision")
        self.assertEqual(events[0]["content"], {
            "toolName": "read_file", "decision": "allow_conversation", "scope": "conversation",
        })
        self.assertEqual(runtime_module._permission_decision_activities(writer, history), [])

    def test_runtime_loads_state_from_input_agent_state(self):
        captured = {}
        encoded = encode_agent_state(
            AgentStateBundle(
                revision=4,
                history={
                    "messages": [{"role": "user", "content": "from saved variable"}],
                    "summary": "saved summary",
                    "version": 1,
                },
                memory=[{"key": "project", "content": "cc-agent"}],
                tasks=[{"id": "task-1", "subject": "stabilize"}],
                permissions={"schema_version": 1, "allowed_tools": {"run_python": "conversation"}},
                last_execution_metadata={"finish_reason": "final"},
                active_skills=[{"name": "xlsx-guide", "summary": "spreadsheet work"}],
            )
        )

        class FakeLoop:
            def __init__(self, **kwargs):
                captured["state"] = kwargs["state"]
                self.final_result = None

            def run(self):
                state = captured["state"]
                self.final_result = AgentRunResult(
                    answer="ok",
                    history=state.history,
                    memory=state.memory,
                    tasks=state.tasks,
                    permissions=state.permissions,
                    active_skills=state.active_skills,
                    execution_metadata={"finish_reason": "final"},
                    summary=state.summary,
                )
                return
                yield

        runtime_module.AgentLoop = FakeLoop
        strategy = SimpleNamespace(
            session=SimpleNamespace(app_id="app-1", session_id="session-1", conversation_id="conv-1"),
            runtime=SimpleNamespace(user_id="user-1"),
            _init_prompt_tools=lambda tools: [],
        )

        events = list(
            DifyAgentRuntime(strategy).run(
                {
                    "query": "continue",
                    "conversation_id": "conv-1",
                    "inputs": {
                        "agent_state": encoded.value,
                        "capability_mode": "minio",
                        "storage": "obsolete settings are not parsed",
                    },
                }
            )
        )
        run_finished = next(event for event in events if event.get("type") == "RUN_FINISHED")

        self.assertEqual(captured["state"].history[0]["content"], "from saved variable")
        self.assertEqual(captured["state"].summary, "saved summary")
        self.assertEqual(captured["state"].memory[0]["key"], "project")
        self.assertEqual(captured["state"].tasks[0]["id"], "task-1")
        self.assertEqual(captured["state"].permissions["allowed_tools"]["run_python"], "conversation")
        self.assertEqual(captured["state"].active_skills[0]["name"], "xlsx-guide")
        self.assertEqual(run_finished["result"]["state_ref"]["revision"], 6)
        self.assertIn("agent_state", run_finished["result"])
        self.assertNotIn("history", run_finished["result"])


if __name__ == "__main__":
    unittest.main()
