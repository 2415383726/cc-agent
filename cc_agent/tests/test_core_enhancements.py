import json
import unittest
from types import SimpleNamespace

from cc_agent.core import runtime as runtime_module
from cc_agent.core.compression import DifyHistorySummarizer
from cc_agent.core.config import AgentRunConfig, extract_model_features, resolve_stream_mode
from cc_agent.core.context_budget import (
    ContextBudget,
    estimate_context_tokens,
    find_split_point,
    snip_old_tool_results,
)
from cc_agent.core.error_classifier import classify_error
from cc_agent.core.guards import ToolGuard, ToolGuardConfig
from cc_agent.core.history import dump_history, load_history
from cc_agent.core.internal_events import ModelEnded, ModelError, ModelStarted, ToolCompleted
from cc_agent.core.internal_tools import InternalToolExecutor, internal_tool_schemas
from cc_agent.core.interrupts import UserInterrupts
from cc_agent.core.loop import AgentLoop
from cc_agent.core.messages import AgentRunResult, AgentState, AssistantTurn, ToolCall, ToolResult
from cc_agent.core.model_stream import AssistantTurnCompleted, TextDelta
from cc_agent.core.prompt_builder import PromptBuilder
from cc_agent.core.result_budget import ResultBudget
from cc_agent.core.runtime import DifyAgentRuntime
from cc_agent.core.tool_adapter import ToolAdapter
from cc_agent.core.tool_catalog import ToolCatalog
from cc_agent.core.tool_scheduler import SerialToolScheduler


class ConfigAndHistoryEnhancementTests(unittest.TestCase):
    def test_model_features_drive_stream_mode_without_disabling_unknown_models(self):
        model = SimpleNamespace(entity=SimpleNamespace(features=["tool-call", "vision"]))

        self.assertEqual(extract_model_features(model), ["tool-call", "vision"])
        self.assertFalse(resolve_stream_mode(True, ["tool-call", "vision"]))
        self.assertTrue(resolve_stream_mode(True, ["tool-call", "stream-tool-call"]))
        self.assertTrue(resolve_stream_mode(True, []))

    def test_model_feature_enums_enable_tool_calls_and_streaming(self):
        try:
            from dify_plugin.entities.model import ModelFeature
        except Exception:
            self.skipTest("dify_plugin ModelFeature is not available")
        model = SimpleNamespace(
            entity=SimpleNamespace(features=[ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL])
        )

        config = AgentRunConfig.from_parameters({"model": model, "query": "hello"})

        self.assertEqual(config.model_features, ["tool-call", "stream-tool-call"])
        self.assertTrue(config.tool_call_supported)
        self.assertTrue(config.stream)

    def test_context_limit_uses_model_entity_when_available(self):
        model = SimpleNamespace(entity=SimpleNamespace(features=["tool-call"], context_size=12345))

        config = AgentRunConfig.from_parameters({"model": model, "query": "hello"})

        self.assertEqual(config.resolved_context_limit, 12345)

    def test_explicit_context_limit_overrides_model_entity(self):
        model = SimpleNamespace(entity=SimpleNamespace(features=["tool-call"], context_size=12345))

        config = AgentRunConfig.from_parameters(
            {"model": model, "query": "hello", "max_total_context_tokens": 131072}
        )

        self.assertEqual(config.resolved_context_limit, 131072)

    def test_auth_token_error_is_not_context_overflow(self):
        self.assertEqual(classify_error(RuntimeError("invalid API token")), "model_error")
        self.assertEqual(
            classify_error(RuntimeError("maximum context length exceeded")), "context_overflow"
        )

    def test_config_ignores_optional_model_profiles(self):
        default_model = SimpleNamespace(name="default")
        think_model = SimpleNamespace(name="think")
        flash_model = SimpleNamespace(name="flash")
        multimodal_model = SimpleNamespace(name="multimodal")

        config = AgentRunConfig.from_parameters(
            {
                "model": default_model,
                "think_model": think_model,
                "flash_model": flash_model,
                "multimodal_model": multimodal_model,
                "query": "hello",
            }
        )

        self.assertIs(config.model_for("default"), default_model)
        self.assertIs(config.model_for("think"), default_model)
        self.assertIs(config.model_for("flash"), default_model)
        self.assertIs(config.model_for("multimodal"), default_model)
        self.assertEqual(config.model_profiles["think"], default_model)

    def test_optional_model_profiles_fall_back_to_default_model(self):
        default_model = SimpleNamespace(name="default")

        config = AgentRunConfig.from_parameters({"model": default_model, "query": "hello"})

        self.assertIs(config.model_for("think"), default_model)
        self.assertIs(config.model_for("flash"), default_model)
        self.assertIs(config.model_for("multimodal"), default_model)

    def test_output_protocol_accepts_boolean_agui_switch(self):
        self.assertEqual(
            AgentRunConfig.from_parameters(
                {"query": "hello", "output_protocol": True}
            ).output_protocol,
            "agui",
        )
        self.assertEqual(
            AgentRunConfig.from_parameters(
                {"query": "hello", "output_protocol": False}
            ).output_protocol,
            "dify_native",
        )
        with self.assertRaises(ValueError):
            AgentRunConfig.from_parameters({"query": "hello", "output_protocol": "dify_native"})

    def test_skill_denylist_accepts_semicolon_separated_names(self):
        config = AgentRunConfig.from_parameters(
            {"query": "hello", "skill_denylist": " answers-charts ; Skill-B "}
        )

        self.assertEqual(config.skill_denylist, ["answers-charts", "Skill-B"])

    def test_history_payload_is_versioned_and_backward_compatible(self):
        payload = dump_history([{"role": "user", "content": "hi"}], summary="s")
        loaded = load_history(payload)

        self.assertEqual(json.loads(payload)["version"], 1)
        self.assertEqual(loaded.version, 1)
        self.assertEqual(loaded.summary, "s")
        self.assertEqual(load_history({"history": [{"role": "user", "content": "old"}]}).version, 1)


class BudgetAndPromptEnhancementTests(unittest.TestCase):
    def test_context_budget_uses_recursive_estimate_and_persistent_summary_metadata(self):
        messages = [
            {"role": "system", "content": "系统"},
            {"role": "user", "content": "你好" * 30},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "name": "Search", "arguments": {"query": "关键词" * 80}}
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "Search", "content": "结果" * 120},
            {"role": "user", "content": "继续" * 80},
            {"role": "assistant", "content": "recent 1"},
            {"role": "user", "content": "recent 2"},
            {"role": "assistant", "content": "recent 3"},
            {"role": "user", "content": "recent 4"},
            {"role": "assistant", "content": "recent 5"},
            {"role": "user", "content": "recent 6"},
        ]
        calls = []

        def summarizer(old_messages, existing_summary=""):
            calls.append((old_messages, existing_summary))
            return f"{existing_summary}\nLLM summary".strip()

        result = ContextBudget(
            max_history_messages=10, max_observation_chars=80, max_total_context_chars=180
        ).compact_history(messages, existing_summary="old summary", summarizer=summarizer)

        self.assertGreater(estimate_context_tokens(messages), 180)
        self.assertTrue(result.metadata["compressed"])
        self.assertIn("observation_snipped", result.metadata["compressed_reason"])
        self.assertIn("history_summarized", result.metadata["compressed_reason"])
        self.assertEqual(result.metadata["snipped_tool_results"], 1)
        self.assertGreater(result.metadata["summarized_messages"], 0)
        self.assertTrue(calls)
        self.assertIn("old summary", result.summary)
        self.assertIn("LLM summary", result.summary)

    def test_persistent_compaction_writes_summary_to_final_payload(self):
        class FakeModel:
            def invoke(self, messages, tools, force_final=False):
                return AssistantTurn(text="ok")

        initial_history = [
            {"role": "user", "content": f"old turn {index} important decision"}
            for index in range(20)
        ]

        loop = AgentLoop(
            config=AgentRunConfig(
                query="current request", maximum_iterations=1, max_history_messages=6
            ),
            state=AgentState(history=list(initial_history)),
            registry=ToolCatalog.create(),
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(ToolCatalog.create(), AgentState()),
            summarizer=lambda messages, existing_summary="": "persistent summary",
        )
        list(loop.run())
        result = loop.final_result
        payload = result.to_json_payload()

        self.assertEqual(result.summary, "persistent summary")
        self.assertEqual(payload["history_payload"]["summary"], "persistent summary")
        self.assertLess(len(result.history), len(initial_history) + 1)

    def test_compaction_snips_old_tool_results_but_preserves_recent_tool_results(self):
        old_tool_content = "OLD-" * 100
        recent_tool_content = "RECENT-" * 100
        messages = [
            {"role": "user", "content": "old request"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "old_call", "name": "Search", "arguments": {}}],
            },
            {
                "role": "tool",
                "tool_call_id": "old_call",
                "name": "Search",
                "content": old_tool_content,
            },
            {"role": "user", "content": "recent one"},
            {"role": "assistant", "content": "recent two"},
            {"role": "user", "content": "recent three"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "recent_call", "name": "Search", "arguments": {}}],
            },
            {
                "role": "tool",
                "tool_call_id": "recent_call",
                "name": "Search",
                "content": recent_tool_content,
            },
            {"role": "user", "content": "recent five"},
        ]

        snipped = snip_old_tool_results(messages, max_chars=80, preserve_last_n_messages=6)

        self.assertEqual(snipped, 1)
        self.assertIn("snipped", messages[2]["content"])
        self.assertEqual(messages[7]["content"], recent_tool_content)

    def test_find_split_point_does_not_create_orphan_tool_messages(self):
        messages = [
            {"role": "user", "content": "old " * 100},
            {"role": "user", "content": "older " * 100},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "name": "Search", "arguments": {"q": "x"}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "Search", "content": "result"},
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "answer"},
        ]

        split = find_split_point(messages, keep_ratio=0.45)
        recent = messages[split:]

        self.assertNotEqual(recent[0]["role"], "tool")
        self.assertEqual(recent, load_history(recent).messages)

    def test_existing_summary_is_carried_into_next_summary(self):
        result = ContextBudget(
            max_history_messages=4, max_total_context_chars=100000
        ).compact_history(
            [{"role": "user", "content": f"old fact {index}"} for index in range(12)],
            existing_summary="OLD SUMMARY: user chose Dify",
            summarizer=lambda messages, existing_summary="": f"{existing_summary}\nNEW SUMMARY: loop stabilized",
        )

        self.assertIn("OLD SUMMARY: user chose Dify", result.summary)
        self.assertIn("NEW SUMMARY: loop stabilized", result.summary)

    def test_prompt_builder_is_a_dedicated_component(self):
        config = AgentRunConfig(query="q", instruction="be useful")
        state = AgentState(tasks=[{"id": "1", "subject": "claws", "status": "pending"}])
        prompt, metadata = PromptBuilder(config, state).build([{"role": "user", "content": "hi"}])

        self.assertEqual(prompt[0]["role"], "system")
        self.assertIn("be useful", prompt[0]["content"])
        self.assertIn("claws", prompt[0]["content"])
        self.assertFalse(metadata["compressed"])

    def test_prompt_skill_index_excludes_runtime_metadata(self):
        config = AgentRunConfig(query="q")
        state = AgentState(
            skills=[
                {
                    "name": "demo",
                    "description": "Demo skill",
                    "when_to_use": "Use for demos",
                    "argument_hint": "topic",
                    "metadata": {"large": "x" * 1000},
                    "resources": ["references/a.md"],
                    "ui": {"color": "blue"},
                }
            ]
        )

        system_prompt = PromptBuilder(config, state).system_prompt()

        self.assertIn("Use for demos", system_prompt)
        self.assertNotIn('"metadata"', system_prompt)
        self.assertNotIn('"resources"', system_prompt)

    def test_prompt_builder_uses_layered_agent_prompt_with_application_instruction(self):
        config = AgentRunConfig(query="q", instruction="你是干部专家系统的助手")
        prompt = PromptBuilder(config, AgentState()).system_prompt()

        self.assertIn("# Identity", prompt)
        self.assertIn("# System", prompt)
        self.assertIn("# Working in Dify", prompt)
        self.assertIn("# Application instruction", prompt)
        self.assertIn("干部专家系统", prompt)
        self.assertIn("Tool results may include untrusted external content", prompt)
        self.assertIn(
            "Do not invent capabilities that are not available in the current tool list", prompt
        )

    def test_dify_only_prompt_lists_uploaded_file_metadata_without_claiming_workspace_access(self):
        config = AgentRunConfig(
            query="summarize",
            files=[
                {
                    "id": "upload_1",
                    "upload_file_id": "upload_1",
                    "name": "brief.pdf",
                    "mimeType": "application/pdf",
                    "size": 123,
                    "download_url": "https://example.invalid/secret",
                    "content": "hidden file content",
                }
            ],
        )

        prompt = PromptBuilder(config, AgentState()).system_prompt()

        self.assertIn("# Uploaded files", prompt)
        self.assertIn("brief.pdf", prompt)
        self.assertIn("upload_1", prompt)
        self.assertIn("application/pdf", prompt)
        self.assertIn(
            "These files are visible as request attachments, but no CC Agent workspace is configured",
            prompt,
        )
        self.assertNotIn("Workspace files", prompt)
        self.assertNotIn("run_python", prompt)
        self.assertNotIn("CC_AGENT_FILES_JSON", prompt)
        self.assertNotIn("download_url", prompt)
        self.assertNotIn("https://example.invalid", prompt)
        self.assertNotIn("hidden file content", prompt)

    def test_internal_tool_descriptions_explain_usage_strategy(self):
        schemas = {schema["name"]: schema for schema in internal_tool_schemas()}

        self.assertIn("specialized workflow", schemas["Skill"]["description"])
        self.assertIn("multi-step", schemas["TaskCreate"]["description"])
        self.assertIn("AG-UI interrupt", schemas["UserPrompt"]["description"])

    def test_internal_tool_descriptions_are_actionable_usage_guides(self):
        schemas = {schema["name"]: schema for schema in internal_tool_schemas()}
        expected_fragments = {
            "SkillList": ["Usage:", "available skills", "Do not invoke local slash commands"],
            "Skill": ["Usage:", "specialized workflow", "the next reasoning turn"],
            "SkillReadResource": [
                "Usage:",
                "referenced by the skill instructions",
                "Do not guess paths",
            ],
            "TaskCreate": ["Usage:", "When NOT to use", "3 or more distinct steps", "pending"],
            "TaskUpdate": [
                "Usage:",
                "Only ONE task may be in_progress at a time",
                "Never mark a task completed",
            ],
            "TaskGet": ["Usage:", "latest state", "blocked_by"],
            "TaskList": ["Usage:", "Task IDs are not priority order", "Do not create duplicate"],
            "UserPrompt": [
                "Usage:",
                "AG-UI interrupt",
                "options",
                "multiSelect",
                "allowCustomInput",
            ],
        }

        self.assertEqual(set(expected_fragments), set(schemas))
        for name, fragments in expected_fragments.items():
            description = schemas[name]["description"]
            self.assertGreaterEqual(len(description), 180, name)
            for fragment in fragments:
                self.assertIn(fragment, description, name)
            for prop_name, prop_schema in schemas[name]["parameters"]["properties"].items():
                self.assertIn("description", prop_schema, f"{name}.{prop_name}")

    def test_task_tool_schemas_expose_task_v2_aliases_and_status_rules(self):
        schemas = {schema["name"]: schema for schema in internal_tool_schemas()}
        create_props = schemas["TaskCreate"]["parameters"]["properties"]
        update_props = schemas["TaskUpdate"]["parameters"]["properties"]
        get_props = schemas["TaskGet"]["parameters"]["properties"]

        self.assertIn("active_form", create_props)
        self.assertIn("task_id", update_props)
        self.assertIn("add_blocks", update_props)
        self.assertIn("add_blocked_by", update_props)
        self.assertIn("task_id", get_props)
        self.assertEqual(
            update_props["status"]["enum"],
            ["pending", "in_progress", "completed", "canceled", "deleted"],
        )
        self.assertIn("null", update_props["metadata"]["description"])

    def test_user_prompt_is_single_agui_interrupt_tool_and_hidden_in_dify_native(self):
        agui_schemas = {
            schema["name"]: schema for schema in internal_tool_schemas(output_protocol="agui")
        }
        native_schemas = {
            schema["name"]: schema
            for schema in internal_tool_schemas(output_protocol="dify_native")
        }

        self.assertIn("UserPrompt", agui_schemas)
        self.assertNotIn("AskUserQuestion", agui_schemas)
        self.assertNotIn("UserPrompt", native_schemas)
        self.assertNotIn("AskUserQuestion", native_schemas)

        prompt_props = agui_schemas["UserPrompt"]["parameters"]["properties"]
        self.assertIn("options", prompt_props)
        self.assertIn("multiSelect", prompt_props)
        self.assertIn("allowCustomInput", prompt_props)
        self.assertIn("fields", prompt_props)
        self.assertIn("radio", prompt_props["fields"]["items"]["properties"]["type"]["enum"])
        self.assertIn("daterange", prompt_props["fields"]["items"]["properties"]["type"]["enum"])
        self.assertEqual(
            prompt_props["purpose"]["enum"], ["clarification", "permission", "approval"]
        )

    def test_user_prompt_normalizes_structured_fields(self):
        result = InternalToolExecutor(AgentState()).execute(
            "UserPrompt",
            {
                "question": "Provide filters",
                "fields": [
                    {
                        "name": "keyword",
                        "label": "Keyword",
                        "type": "text",
                        "required": True,
                        "description": "Search name or code",
                        "group": "Scope",
                        "width": "half",
                        "maxLength": 40,
                        "prefix": "#",
                    },
                    {
                        "name": "levels",
                        "label": "Levels",
                        "type": "multiselect",
                        "options": ["A", "B"],
                        "defaultValue": ["B"],
                    },
                    {
                        "name": "period",
                        "label": "Period",
                        "type": "daterange",
                        "defaultValue": ["2026-01-01", "2026-06-30"],
                    },
                ],
            },
            "call_fields",
        )
        fields = result.metadata["question"]["fields"]
        self.assertEqual(fields[0]["name"], "keyword")
        self.assertTrue(fields[0]["required"])
        self.assertEqual(fields[0]["description"], "Search name or code")
        self.assertEqual(fields[0]["group"], "Scope")
        self.assertEqual(fields[0]["width"], "half")
        self.assertEqual(fields[0]["maxLength"], 40)
        self.assertEqual(fields[1]["defaultValue"], ["B"])
        self.assertEqual(fields[2]["defaultValue"], ["2026-01-01", "2026-06-30"])


class GuardSchedulerAndToolEnhancementTests(unittest.TestCase):
    def test_guard_rejects_denied_tool_with_synthetic_observation(self):
        guard = ToolGuard(ToolGuardConfig(denylist=["TaskCreate"]))
        result = guard.before_call(ToolCall(id="call_1", name="TaskCreate", arguments={}))

        self.assertIsNotNone(result)
        self.assertTrue(result.synthetic)
        self.assertTrue(result.is_error)
        self.assertIn("rejected by policy", result.llm_observation)

    def test_guard_requires_confirmation_for_listed_tool(self):
        guard = UserInterrupts(AgentState(), confirmation_tools={"current_time"})
        result = guard.before_call(
            ToolCall(id="call_1", name="current_time", arguments={"timezone": "Asia/Shanghai"})
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.synthetic)
        self.assertFalse(result.is_error)
        self.assertTrue(result.metadata["requires_user_input"])
        self.assertTrue(result.metadata["permission_required"])
        self.assertEqual(result.metadata["pending_tool_execution"]["name"], "current_time")
        self.assertEqual(result.metadata["question"]["purpose"], "permission")
        self.assertEqual(result.metadata["question"]["options"][0]["value"], "allow_once")
        self.assertEqual(result.metadata["question"]["options"][-1]["value"], "deny")

    def test_scheduler_preserves_order_and_applies_result_budget(self):
        class FakeAdapter:
            def execute(self, tool_call):
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    llm_observation=tool_call.arguments["text"],
                )

        scheduler = SerialToolScheduler(
            tool_adapter=FakeAdapter(), result_budget=ResultBudget(max_observation_chars=50)
        )
        calls = [
            ToolCall(id="a", name="One", arguments={"text": "A" * 120}),
            ToolCall(id="b", name="Two", arguments={"text": "ok"}),
        ]
        results = scheduler.execute(calls, iteration=1)

        self.assertEqual([item.tool_call.id for item in results], ["a", "b"])
        self.assertIn("truncated", results[0].result.llm_observation)
        self.assertTrue(results[0].result.metadata["truncated"])
        self.assertIn("total_duration_ms", results[0].result.metadata)

    def test_scheduler_enforces_aggregate_result_budget(self):
        class FakeAdapter:
            def execute(self, tool_call):
                return ToolResult(
                    tool_call_id=tool_call.id, tool_name=tool_call.name, llm_observation="X" * 50
                )

        scheduler = SerialToolScheduler(
            tool_adapter=FakeAdapter(), result_budget=ResultBudget(max_observation_chars=50)
        )
        results = scheduler.execute(
            [ToolCall(id=str(index), name=f"T{index}", arguments={}) for index in range(3)],
            iteration=1,
        )

        self.assertLessEqual(sum(len(item.result.llm_observation) for item in results), 100)
        self.assertTrue(any(item.result.metadata.get("batch_truncated") for item in results))
        self.assertEqual(len(results), 3)

    def test_scheduler_stops_after_confirmation_interrupt(self):
        class FakeAdapter:
            def __init__(self):
                self.executed = []

            def execute(self, tool_call):
                self.executed.append(tool_call.name)
                return ToolResult(
                    tool_call_id=tool_call.id, tool_name=tool_call.name, llm_observation="ok"
                )

        adapter = FakeAdapter()
        scheduler = SerialToolScheduler(
            tool_adapter=adapter,
            interrupts=UserInterrupts(AgentState(), confirmation_tools={"current_time"}),
        )

        results = scheduler.execute(
            [
                ToolCall(id="a", name="current_time", arguments={}),
                ToolCall(id="b", name="weekday", arguments={}),
            ],
            iteration=1,
        )

        self.assertEqual([item.tool_call.id for item in results], ["a", "b"])
        self.assertEqual(adapter.executed, [])
        self.assertTrue(results[0].result.metadata["requires_user_input"])
        self.assertTrue(results[1].result.metadata["skipped"])

    def test_task_get_and_richer_task_fields(self):
        state = AgentState()
        executor = InternalToolExecutor(state)

        created = executor.execute(
            "TaskCreate",
            {
                "subject": "ship system claws",
                "description": "stabilize loop",
                "blocks": ["2"],
                "metadata": {"priority": "high"},
            },
            "call_1",
        )
        got = executor.execute("TaskGet", {"id": created.metadata["task"]["id"]}, "call_2")

        self.assertFalse(got.is_error)
        self.assertEqual(state.tasks[0]["subject"], "ship system claws")
        self.assertEqual(state.tasks[0]["blocks"], ["2"])
        self.assertIn("priority", got.llm_observation)

    def test_task_tools_follow_task_v2_state_dependencies_and_delete_semantics(self):
        state = AgentState()
        executor = InternalToolExecutor(state)

        first = executor.execute(
            "TaskCreate",
            {
                "subject": "prepare data",
                "description": "Collect and validate the inputs.",
                "status": "open",
                "metadata": {"priority": "high"},
            },
            "call_1",
        )
        second = executor.execute(
            "TaskCreate",
            {"subject": "write report", "description": "Draft the final report."},
            "call_2",
        )

        self.assertFalse(first.is_error)
        self.assertFalse(second.is_error)
        self.assertIn("Task #1 created successfully", first.llm_observation)
        self.assertEqual(state.tasks[0]["status"], "pending")
        self.assertEqual(state.tasks[1]["status"], "pending")

        updated = executor.execute(
            "TaskUpdate",
            {
                "taskId": "1",
                "status": "in_progress",
                "activeForm": "Preparing data",
                "addBlocks": ["2"],
                "metadata": {"priority": None, "stage": "analysis"},
            },
            "call_3",
        )

        self.assertFalse(updated.is_error)
        self.assertIn("Updated task #1", updated.llm_observation)
        self.assertEqual(state.tasks[0]["active_form"], "Preparing data")
        self.assertEqual(state.tasks[0]["metadata"], {"stage": "analysis"})
        self.assertEqual(state.tasks[0]["blocks"], ["2"])
        self.assertEqual(state.tasks[1]["blocked_by"], ["1"])

        completed = executor.execute("TaskUpdate", {"id": "1", "status": "done"}, "call_4")
        self.assertFalse(completed.is_error)
        self.assertEqual(state.tasks[0]["status"], "completed")

        deleted = executor.execute("TaskUpdate", {"task_id": "2", "status": "deleted"}, "call_5")
        self.assertFalse(deleted.is_error)
        self.assertEqual(state.tasks[1]["status"], "deleted")
        self.assertEqual(state.tasks[0]["blocks"], [])

        listed = executor.execute("TaskList", {}, "call_6")
        self.assertFalse(listed.is_error)
        self.assertIn("#1 [completed] prepare data", listed.llm_observation)
        self.assertNotIn("write report", listed.llm_observation)

    def test_prompt_builder_filters_deleted_tasks_and_injects_task_discipline(self):
        state = AgentState(
            tasks=[
                {"id": "1", "subject": "prepare data", "status": "in_progress", "blocked_by": []},
                {"id": "2", "subject": "old report", "status": "deleted", "blocked_by": []},
            ]
        )

        prompt = PromptBuilder(AgentRunConfig(query="q"), state).system_prompt()

        self.assertIn("# Current tasks", prompt)
        self.assertIn("Only ONE task may be in_progress at a time", prompt)
        self.assertIn("blocked_by", prompt)
        self.assertIn("prepare data", prompt)
        self.assertNotIn("old report", prompt)

    def test_skill_list_exposes_registry_metadata_for_inline_skills(self):
        state = AgentState(
            skills=[
                {
                    "name": "brief",
                    "description": "Briefing",
                    "allowed_tools": ["TaskList"],
                    "argument_hint": "input",
                    "model": "fast",
                    "context": ["references/brief.md"],
                    "body": "Brief {{input}}",
                }
            ]
        )
        result = InternalToolExecutor(state).execute("SkillList", {}, "call_1")
        payload = json.loads(result.llm_observation)

        self.assertEqual(payload["skills"][0]["allowed_tools"], ["TaskList"])
        self.assertEqual(payload["skills"][0]["argument_hint"], "input")
        self.assertEqual(payload["skills"][0]["context"], ["references/brief.md"])
        self.assertEqual(payload["warnings"], [])
        self.assertNotIn("body", payload["skills"][0])

    def test_ask_user_question_is_not_available(self):
        result = InternalToolExecutor(AgentState()).execute(
            "AskUserQuestion", {"question": "Which account?"}, "call_1"
        )

        self.assertTrue(result.is_error)
        self.assertNotIn("requires_user_input", result.metadata)
        self.assertRegex(result.llm_observation, r"(not available|unknown)")

    def test_user_prompt_finishes_with_structured_question(self):
        class FakeModel:
            def invoke(self, messages, tools, force_final=False):
                return AssistantTurn(
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            name="UserPrompt",
                            arguments={
                                "question": "Allow Search?",
                                "purpose": "permission",
                                "options": [
                                    {
                                        "label": "Allow once",
                                        "description": "Run this time",
                                        "value": "allow_once",
                                    },
                                    "Deny",
                                ],
                                "multiSelect": False,
                            },
                        )
                    ]
                )

        state = AgentState()
        registry = ToolCatalog.create()
        loop = AgentLoop(
            config=AgentRunConfig(query="help", maximum_iterations=3),
            state=state,
            registry=registry,
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(registry, state),
        )
        list(loop.run())
        question = loop.final_result.execution_metadata["question"]

        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "awaiting_user")
        self.assertEqual(question["id"], "call_1")
        self.assertEqual(question["purpose"], "permission")
        self.assertFalse(question["multiSelect"])
        self.assertFalse(question["allowCustomInput"])
        self.assertEqual(
            question["options"][0],
            {
                "label": "Allow once",
                "description": "Run this time",
                "value": "allow_once",
                "disabled": False,
            },
        )
        self.assertEqual(
            question["options"][1],
            {"label": "Deny", "description": "", "value": "Deny", "disabled": False},
        )

    def test_user_prompt_invalid_purpose_falls_back_to_clarification(self):
        result = InternalToolExecutor(AgentState()).execute(
            "UserPrompt",
            {"question": "What next?", "purpose": "unknown", "options": ["A"]},
            "call_1",
        )

        self.assertFalse(result.is_error)
        self.assertEqual(result.metadata["question"]["purpose"], "clarification")
        self.assertTrue(result.metadata["question"]["allowCustomInput"])

    def test_config_reads_user_prompt_response_from_inputs(self):
        config = AgentRunConfig.from_parameters(
            {
                "query": "Allow once",
                "inputs": {
                    "user_prompt_response": {
                        "promptId": "call_1",
                        "purpose": "permission",
                        "selectedValues": ["allow_once"],
                        "answer": "Allow once",
                    }
                },
            }
        )
        prompt, _ = PromptBuilder(config, AgentState()).build(
            [{"role": "user", "content": config.query}]
        )

        self.assertEqual(config.user_prompt_response["promptId"], "call_1")
        self.assertNotIn("Structured user prompt response:", prompt[0]["content"])
        self.assertNotIn('"selectedValues": ["allow_once"]', prompt[0]["content"])

    def test_config_ignores_removed_tool_confirmation_list_parameter(self):
        config = AgentRunConfig.from_parameters(
            {"query": "time", "tool_confirmation_list": "current_time; weekday ;TaskCreate"}
        )

        self.assertIsNone(config.tool_confirmation_list)

    def test_runtime_accepts_tool_selector_dicts_without_sdk_identity_conversion(self):
        class FakeStrategy:
            def _init_prompt_tools(self, tools):
                raise AssertionError(
                    "ToolSelector dicts should not be passed to SDK _init_prompt_tools"
                )

        selector = {
            "provider_id": "demo_provider",
            "tool_name": "Search",
            "tool_description": "Search documents",
            "tool_configuration": {"fixed": "runtime"},
            "tool_parameters": {
                "query": {
                    "name": "query",
                    "type": "string",
                    "required": True,
                    "description": "Search query",
                }
            },
        }

        prompt_tools = DifyAgentRuntime(FakeStrategy())._init_external_prompt_tools([selector])

        self.assertEqual(prompt_tools[0].name, "Search")
        self.assertEqual(prompt_tools[0].parameters["properties"]["query"]["type"], "string")
        self.assertEqual(prompt_tools[0].parameters["required"], ["query"])

    def test_runtime_accepts_tool_entity_like_dicts_without_sdk_identity_conversion(self):
        class FakeStrategy:
            def _init_prompt_tools(self, tools):
                raise AssertionError(
                    "Tool entity dicts should not be passed to SDK _init_prompt_tools"
                )

        entity = {
            "identity": {"name": "Lookup", "provider": "demo_provider"},
            "description": {"llm": "Lookup documents"},
            "parameters": [
                {
                    "name": "query",
                    "form": "llm",
                    "type": "string",
                    "required": True,
                    "llm_description": "Lookup query",
                },
                {"name": "fixed", "form": "form", "type": "string", "required": True},
            ],
        }

        prompt_tools = DifyAgentRuntime(FakeStrategy())._init_external_prompt_tools([entity])

        self.assertEqual(prompt_tools[0].name, "Lookup")
        self.assertEqual(prompt_tools[0].description, "Lookup documents")
        self.assertEqual(
            prompt_tools[0].parameters["properties"]["query"]["description"], "Lookup query"
        )
        self.assertNotIn("fixed", prompt_tools[0].parameters["properties"])

    def test_loop_can_skip_user_query_when_resuming_interrupt(self):
        captured = {}

        class FakeModel:
            def invoke(self, messages, tools, force_final=False):
                captured["messages"] = messages
                return AssistantTurn(text="resumed")

        state = AgentState(
            history=[
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "call_1", "name": "UserPrompt", "arguments": {}}],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "UserPrompt",
                    "content": "User answered: A",
                },
            ]
        )
        loop = AgentLoop(
            config=AgentRunConfig(query="A", maximum_iterations=1),
            state=state,
            registry=ToolCatalog.create(),
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(ToolCatalog.create(), state),
            include_user_query=False,
        )
        list(loop.run())

        self.assertEqual(loop.final_result.answer, "resumed")
        self.assertFalse(
            any(
                message.get("role") == "user" and message.get("content") == "A"
                for message in captured["messages"]
            )
        )

    def test_loop_finishes_with_awaiting_user_for_confirmation_guard(self):
        class FakeModel:
            def invoke(self, messages, tools, force_final=False):
                return AssistantTurn(
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            name="current_time",
                            arguments={"timezone": "Asia/Shanghai"},
                        )
                    ]
                )

        state = AgentState()
        registry = ToolCatalog.create(
            external_tools=[
                {
                    "provider_id": "demo_provider",
                    "tool_name": "current_time",
                    "tool_description": "Get current time",
                    "tool_configuration": {},
                    "tool_parameters": {},
                }
            ],
            external_prompt_tools=[],
        )
        loop = AgentLoop(
            config=AgentRunConfig(
                query="今天星期几", tool_confirmation_list=["current_time"], maximum_iterations=3
            ),
            state=state,
            registry=registry,
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(registry, state),
        )
        list(loop.run())
        result = loop.final_result

        self.assertEqual(result.execution_metadata["finish_reason"], "awaiting_user")
        self.assertEqual(result.execution_metadata["question"]["purpose"], "permission")
        self.assertEqual(result.execution_metadata["question"]["options"][0]["value"], "allow_once")
        self.assertEqual(result.execution_metadata["question"]["options"][-1]["value"], "deny")
        pending = next(
            message for message in result.history if message.get("tool_call_id") == "call_1"
        )
        self.assertTrue(pending["metadata"]["permission_required"])

    def test_tool_selector_dict_registers_and_invokes_as_external_tool(self):
        selector = {
            "provider_id": "demo_provider",
            "tool_name": "Search",
            "tool_description": "Search documents",
            "tool_configuration": {"fixed": "runtime"},
            "tool_parameters": {},
        }

        class FakeToolSession:
            def __init__(self):
                self.calls = []

            def invoke(self, **kwargs):
                self.calls.append(kwargs)
                return [SimpleNamespace(type="text", message=SimpleNamespace(text="result"))]

        session = SimpleNamespace(tool=FakeToolSession())
        registry = ToolCatalog.create(external_tools=[selector], external_prompt_tools=[])
        result = ToolAdapter(registry, AgentState(), session=session).execute(
            ToolCall(id="call_1", name="Search", arguments={"query": "dify"})
        )

        self.assertFalse(result.is_error)
        self.assertEqual(result.llm_observation, "result")
        self.assertEqual(session.tool.calls[0]["provider"], "demo_provider")
        self.assertEqual(session.tool.calls[0]["tool_name"], "Search")
        self.assertEqual(session.tool.calls[0]["parameters"], {"fixed": "runtime", "query": "dify"})
        self.assertNotIn("parameters", result.metadata)
        self.assertNotIn("parameters", result.to_history()["metadata"])

    def test_runtime_uses_default_model_for_agent_and_summarizer(self):
        created = {}

        class FakeSummarizer:
            def __init__(self, session, model_config):
                created["summarizer_model"] = model_config

        class FakeModelAdapter:
            def __init__(
                self, session, model_config, stream=True, deepseek_thinking_compat=False, **kwargs
            ):
                created["agent_model"] = model_config
                created["stream"] = stream
                created["deepseek_thinking_compat"] = deepseek_thinking_compat

        class FakeLoop:
            def __init__(self, **kwargs):
                created["loop_kwargs"] = kwargs

            def run(self):
                self.final_result = AgentRunResult(
                    answer="", history=[], tasks=[], execution_metadata={"finish_reason": "final"}
                )
                return
                yield

        original_summarizer = runtime_module.DifyHistorySummarizer
        original_model_adapter = runtime_module.DifyModelAdapter
        original_loop = runtime_module.AgentLoop
        runtime_module.DifyHistorySummarizer = FakeSummarizer
        runtime_module.DifyModelAdapter = FakeModelAdapter
        runtime_module.AgentLoop = FakeLoop
        try:
            strategy = SimpleNamespace(
                session=SimpleNamespace(), _init_prompt_tools=lambda tools: []
            )
            events = list(
                DifyAgentRuntime(strategy).run(
                    {
                        "query": "hello",
                        "model": SimpleNamespace(name="default"),
                        "think_model": SimpleNamespace(name="think"),
                        "flash_model": SimpleNamespace(name="flash"),
                    }
                )
            )
        finally:
            runtime_module.DifyHistorySummarizer = original_summarizer
            runtime_module.DifyModelAdapter = original_model_adapter
            runtime_module.AgentLoop = original_loop

        self.assertTrue(any(event["type"] == "RUN_FINISHED" for event in events))
        self.assertEqual(created["agent_model"].name, "default")
        self.assertEqual(created["summarizer_model"].name, "default")
        self.assertFalse(created["deepseek_thinking_compat"])

    def test_runtime_model_routing_falls_back_to_default_model(self):
        created = {}

        class FakeSummarizer:
            def __init__(self, session, model_config):
                created["summarizer_model"] = model_config

        class FakeModelAdapter:
            def __init__(
                self, session, model_config, stream=True, deepseek_thinking_compat=False, **kwargs
            ):
                created["agent_model"] = model_config

        class FakeLoop:
            def __init__(self, **kwargs):
                pass

            def run(self):
                self.final_result = AgentRunResult(
                    answer="", history=[], tasks=[], execution_metadata={"finish_reason": "final"}
                )
                return
                yield

        original_summarizer = runtime_module.DifyHistorySummarizer
        original_model_adapter = runtime_module.DifyModelAdapter
        original_loop = runtime_module.AgentLoop
        runtime_module.DifyHistorySummarizer = FakeSummarizer
        runtime_module.DifyModelAdapter = FakeModelAdapter
        runtime_module.AgentLoop = FakeLoop
        try:
            default_model = SimpleNamespace(name="default")
            strategy = SimpleNamespace(
                session=SimpleNamespace(), _init_prompt_tools=lambda tools: []
            )
            list(DifyAgentRuntime(strategy).run({"query": "hello", "model": default_model}))
        finally:
            runtime_module.DifyHistorySummarizer = original_summarizer
            runtime_module.DifyModelAdapter = original_model_adapter
            runtime_module.AgentLoop = original_loop

        self.assertIs(created["agent_model"], default_model)
        self.assertIs(created["summarizer_model"], default_model)

    def test_loop_records_model_tool_guard_and_compression_events(self):
        class FakeModel:
            def __init__(self):
                self.calls = 0

            def invoke(self, messages, tools, force_final=False):
                self.calls += 1
                if self.calls == 1:
                    return AssistantTurn(
                        tool_calls=[ToolCall(id="call_1", name="Denied", arguments={})]
                    )
                return AssistantTurn(text="done")

        config = AgentRunConfig(
            query="x",
            maximum_iterations=2,
            tool_denylist=["Denied"],
            max_history_messages=4,
            max_total_context_tokens=131072,
        )
        state = AgentState(
            history=[{"role": "user", "content": f"old {index} " * 30} for index in range(8)]
        )
        loop = AgentLoop(
            config=config,
            state=state,
            registry=ToolCatalog.create(),
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(ToolCatalog.create(), state),
        )
        wire_events = list(loop.run())
        result = loop.final_result

        event_types = [type(event) for event in result.events]
        self.assertIn(ModelStarted, event_types)
        self.assertIn(ModelEnded, event_types)
        self.assertIn(ToolCompleted, event_types)
        self.assertTrue(result.execution_metadata["compressed"])
        self.assertEqual(wire_events, [])

    def test_request_budget_rejects_static_overflow_before_model_call(self):
        class NeverModel:
            def __init__(self):
                self.calls = 0

            def invoke(self, messages, tools, force_final=False):
                self.calls += 1
                return AssistantTurn(text="unexpected")

        model = NeverModel()
        config = AgentRunConfig(query="x", max_total_context_tokens=100)
        state = AgentState()
        registry = ToolCatalog.create()
        loop = AgentLoop(
            config=config,
            state=state,
            registry=registry,
            model_adapter=model,
            tool_adapter=ToolAdapter(registry, state),
        )

        list(loop.run())

        self.assertEqual(model.calls, 0)
        self.assertEqual(loop.final_result.execution_metadata["finish_reason"], "context_overflow")

    def test_length_finish_reason_continues_once_without_repeating_answer(self):
        class FakeModel:
            def __init__(self):
                self.calls = []

            def invoke(self, messages, tools, force_final=False):
                self.calls.append(force_final)
                if len(self.calls) == 1:
                    return AssistantTurn(
                        text="first ", finish_reason="length", usage={"total_tokens": 4}
                    )
                return AssistantTurn(text="second", finish_reason="stop", usage={"total_tokens": 3})

        model = FakeModel()
        state = AgentState()
        registry = ToolCatalog.create()
        loop = AgentLoop(
            config=AgentRunConfig(query="write", maximum_iterations=2),
            state=state,
            registry=registry,
            model_adapter=model,
            tool_adapter=ToolAdapter(registry, state),
        )

        list(loop.run())

        self.assertEqual(loop.final_result.answer, "first second")
        self.assertEqual(model.calls, [False, True])
        self.assertEqual(loop.final_result.execution_metadata["continuation_count"], 1)
        self.assertEqual(
            load_history(loop.final_result.history).messages, loop.final_result.history
        )

    def test_history_summarizer_opens_circuit_after_three_failures(self):
        class FailingLLM:
            def __init__(self):
                self.calls = 0

            def invoke(self, **kwargs):
                self.calls += 1
                raise RuntimeError("summary unavailable")

        llm = FailingLLM()
        session = SimpleNamespace(model=SimpleNamespace(llm=llm))
        summarizer = DifyHistorySummarizer(session, model_config=SimpleNamespace())

        for _ in range(5):
            summarizer([{"role": "user", "content": "fact"}])

        self.assertEqual(llm.calls, 3)
        self.assertEqual(summarizer.failure_count, 3)
        self.assertTrue(summarizer.circuit_open)

    def test_context_overflow_model_error_reactive_compacts_and_retries_once(self):
        class FlakyModel:
            def __init__(self):
                self.calls = 0
                self.retry_messages = None

            def invoke(self, messages, tools, force_final=False):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("maximum context length exceeded")
                self.retry_messages = messages
                return AssistantTurn(text="recovered")

        model = FlakyModel()
        loop = AgentLoop(
            config=AgentRunConfig(query="now"),
            state=AgentState(history=[{"role": "user", "content": "old" * 100}]),
            registry=ToolCatalog.create(),
            model_adapter=model,
            tool_adapter=ToolAdapter(ToolCatalog.create(), AgentState()),
        )
        list(loop.run())
        result = loop.final_result

        self.assertEqual(result.answer, "recovered")
        self.assertEqual(result.execution_metadata["finish_reason"], "final")
        self.assertEqual(model.calls, 2)
        self.assertIn("# Identity", model.retry_messages[0]["content"])
        self.assertTrue(result.execution_metadata["context_overflow_detected"])
        self.assertEqual(result.execution_metadata["context_retry_count"], 1)

    def test_loop_passes_prompt_tools_when_model_feature_is_enum(self):
        try:
            from dify_plugin.entities.model import ModelFeature
        except Exception:
            self.skipTest("dify_plugin ModelFeature is not available")

        class FakeModel:
            def __init__(self):
                self.tool_counts = []

            def invoke(self, messages, tools, force_final=False):
                self.tool_counts.append(len(tools))
                return AssistantTurn(text="done")

        model_config = SimpleNamespace(
            entity=SimpleNamespace(features=[ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL])
        )
        fake_model = FakeModel()
        loop = AgentLoop(
            config=AgentRunConfig.from_parameters({"model": model_config, "query": "use tools"}),
            state=AgentState(),
            registry=ToolCatalog.create(),
            model_adapter=fake_model,
            tool_adapter=ToolAdapter(ToolCatalog.create(), AgentState()),
        )
        list(loop.run())

        self.assertEqual(loop.final_result.answer, "done")
        self.assertGreater(fake_model.tool_counts[0], 0)

    def test_max_iterations_final_synthesis_streams_and_disables_tools(self):
        class FakeModel:
            def __init__(self):
                self.calls = []

            def invoke_stream(self, messages, tools, force_final=False):
                self.calls.append({"tools": tools, "force_final": force_final})
                if not force_final:
                    yield AssistantTurnCompleted(
                        turn=AssistantTurn(
                            tool_calls=[ToolCall(id="call_1", name="Missing", arguments={})]
                        )
                    )
                    return
                yield TextDelta(text="final after limit")
                yield AssistantTurnCompleted(
                    turn=AssistantTurn(text="final after limit", usage={"total_tokens": 3})
                )

        model = FakeModel()
        loop = AgentLoop(
            config=AgentRunConfig(query="x", maximum_iterations=1),
            state=AgentState(),
            registry=ToolCatalog.create(),
            model_adapter=model,
            tool_adapter=ToolAdapter(ToolCatalog.create(), AgentState()),
        )
        list(loop.run())
        result = loop.final_result

        self.assertEqual(result.answer, "final after limit")
        self.assertEqual(result.execution_metadata["finish_reason"], "max_iterations")
        self.assertTrue(model.calls[-1]["force_final"])
        self.assertEqual(model.calls[-1]["tools"], [])

    def test_max_iterations_empty_final_synthesis_emits_fallback_text_delta(self):
        class FakeModel:
            def __init__(self):
                self.calls = 0

            def invoke_stream(self, messages, tools, force_final=False):
                self.calls += 1
                if self.calls == 1:
                    yield AssistantTurnCompleted(
                        turn=AssistantTurn(
                            tool_calls=[ToolCall(id="call_1", name="Missing", arguments={})]
                        )
                    )
                    return
                yield AssistantTurnCompleted(turn=AssistantTurn(text=""))

        loop = AgentLoop(
            config=AgentRunConfig(query="x", maximum_iterations=1),
            state=AgentState(),
            registry=ToolCatalog.create(),
            model_adapter=FakeModel(),
            tool_adapter=ToolAdapter(ToolCatalog.create(), AgentState()),
        )
        list(loop.run())
        result = loop.final_result
        fallback = "Maximum iteration limit reached before a final answer was produced."

        self.assertEqual(result.answer, fallback)

    def test_model_error_event_has_event_field(self):
        class FailingModel:
            def invoke(self, messages, tools, force_final=False):
                raise RuntimeError("boom")

        loop = AgentLoop(
            config=AgentRunConfig(query="x"),
            state=AgentState(),
            registry=ToolCatalog.create(),
            model_adapter=FailingModel(),
            tool_adapter=ToolAdapter(ToolCatalog.create(), AgentState()),
        )
        list(loop.run())
        result = loop.final_result
        model_errors = [event for event in result.events if isinstance(event, ModelError)]

        self.assertEqual(model_errors[0].finish_reason, "model_error")

    def test_runtime_run_contract_is_generator(self):
        self.assertEqual(
            DifyAgentRuntime.run.__annotations__["return"], "Generator[dict[str, Any], None, None]"
        )

    def test_strategy_maps_stream_events_to_dify_messages(self):
        from cc_agent.strategies.cc_agent_agui import CCAgentAgUiStrategy

        class FakeRuntime:
            def __init__(self, strategy, strategy_profile=None):
                pass

            def run(self, parameters):
                from cc_agent.core.agui_stream import AgUiStreamWriter

                writer = AgUiStreamWriter("thread-1", "run-1")
                yield from writer.write_run_started()
                yield from writer.write_reasoning_delta("think")
                yield from writer.write_text_delta("answer")
                yield from writer.write_run_finished(
                    AgentRunResult(
                        answer="answer",
                        history=[],
                        tasks=[],
                        execution_metadata={"finish_reason": "final"},
                    )
                )

        original_runtime = CCAgentAgUiStrategy.runtime_cls
        CCAgentAgUiStrategy.runtime_cls = FakeRuntime
        try:
            strategy = object.__new__(CCAgentAgUiStrategy)
            strategy.session = SimpleNamespace()
            strategy.create_log_message = lambda label, data, metadata, status: {
                "kind": "log",
                "label": label,
                "data": data,
                "metadata": metadata,
                "status": status,
            }
            strategy.create_text_message = lambda text: {"kind": "text", "text": text}
            strategy.create_json_message = lambda payload: {"kind": "json", "payload": payload}

            emitted = list(strategy._invoke({"query": "x"}))
        finally:
            CCAgentAgUiStrategy.runtime_cls = original_runtime

        agui_types = [item["data"]["type"] for item in emitted if item.get("kind") == "log"]

        self.assertEqual(agui_types[0], "RUN_STARTED")
        self.assertIn("REASONING_MESSAGE_CONTENT", agui_types)
        self.assertIn("TEXT_MESSAGE_CONTENT", agui_types)
        self.assertEqual(agui_types[-1], "RUN_FINISHED")

    def test_strategy_reads_show_tool_calls_from_inputs(self):
        from cc_agent.strategies.cc_agent_agui import CCAgentAgUiStrategy

        class FakeRuntime:
            def __init__(self, strategy, strategy_profile=None):
                pass

            def run(self, parameters):
                from cc_agent.core.agui_stream import AgUiStreamWriter

                writer = AgUiStreamWriter("thread-1", "run-1")
                yield from writer.write_run_started()
                yield from writer.write_tool_result("call_1", "Search", "ok")
                yield from writer.write_run_finished(
                    AgentRunResult(
                        answer="",
                        history=[],
                        tasks=[],
                        execution_metadata={"finish_reason": "final"},
                    )
                )

        original_runtime = CCAgentAgUiStrategy.runtime_cls
        CCAgentAgUiStrategy.runtime_cls = FakeRuntime
        try:
            strategy = object.__new__(CCAgentAgUiStrategy)
            strategy.session = SimpleNamespace()
            strategy.create_log_message = lambda label, data, metadata, status: {
                "kind": "log",
                "label": label,
                "data": data,
                "metadata": metadata,
                "status": status,
            }

            emitted = list(strategy._invoke({"query": "x", "inputs": {"show_tool_calls": True}}))
        finally:
            CCAgentAgUiStrategy.runtime_cls = original_runtime

        agui_types = [item["data"]["type"] for item in emitted if item.get("kind") == "log"]

        self.assertEqual(agui_types[0], "RUN_STARTED")
        self.assertIn("TOOL_CALL_RESULT", agui_types)
        self.assertIn("TOOL_CALL_END", agui_types)


from cc_agent.core.builtin_skills import register_all
from cc_agent.core.runtime import _dispatch_slash_command


class SlashDispatchTests(unittest.TestCase):
    def test_non_slash_returns_none(self):
        result = _dispatch_slash_command("hello", AgentState(), AgentRunConfig(), [])
        self.assertIsNone(result)

    def test_local_skill_returns_result_text(self):
        skills = register_all()
        state = AgentState(history=[{"role": "user", "content": "hi"}])
        result = _dispatch_slash_command("/status", state, AgentRunConfig(), skills)
        self.assertIsNotNone(result)
        result_text, skill_def = result
        self.assertIn("history messages", result_text)
        self.assertEqual(skill_def["name"], "status")

    def test_prompt_skill_returns_args_payload(self):
        skills = [
            {
                "name": "frontend-design",
                "kind": "prompt",
                "description": "design",
                "body": "design prompt",
            }
        ]
        result = _dispatch_slash_command(
            "/frontend-design mobile", AgentState(), AgentRunConfig(), skills
        )
        self.assertIsNotNone(result)
        payload, skill_def = result
        self.assertEqual(payload["skill_args"], "mobile")
        self.assertEqual(skill_def["name"], "frontend-design")

    def test_unknown_slash_returns_none(self):
        result = _dispatch_slash_command("/unknown", AgentState(), AgentRunConfig(), register_all())
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
