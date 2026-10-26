import unittest

from cc_agent.core.builtin_skills import register_all
from cc_agent.core.config import AgentRunConfig
from cc_agent.core.messages import AgentState
from cc_agent.core.prompt_builder import PromptBuilder
from cc_agent.core.runtime import _dispatch_slash_command


class SlashCommandDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all_skills = register_all()

    def test_non_command_returns_none(self):
        result = _dispatch_slash_command("hello", AgentState(), AgentRunConfig(), self.all_skills)
        self.assertIsNone(result)

    def test_status_command_returns_session_summary(self):
        result = _dispatch_slash_command(
            "/status",
            AgentState(
                history=[{"role": "user", "content": "hi"}],
                memory=[{"key": "project", "content": "cc-agent"}],
                tasks=[{"id": "1", "subject": "ship"}],
            ),
            AgentRunConfig(),
            self.all_skills,
        )

        self.assertIsNotNone(result)
        result_text, skill_def = result
        self.assertEqual(skill_def["name"], "status")
        self.assertIn("Status", result_text)
        self.assertIn("history", result_text)

    def test_context_command_reports_history_and_summary(self):
        result = _dispatch_slash_command(
            "/context",
            AgentState(
                history=[{"role": "user", "content": "older"}],
                summary="user selected Dify workflow state",
            ),
            AgentRunConfig(),
            self.all_skills,
        )

        self.assertIsNotNone(result)
        result_text, skill_def = result
        self.assertEqual(skill_def["name"], "context")
        self.assertIn("Context", result_text)
        self.assertIn("user selected Dify workflow state", result_text)

    def test_cost_command_reports_known_usage_when_history_has_usage(self):
        result = _dispatch_slash_command(
            "/cost",
            AgentState(
                history=[
                    {"role": "assistant", "content": "done", "usage": {"total_tokens": 123}},
                ],
            ),
            AgentRunConfig(),
            self.all_skills,
        )

        self.assertIsNotNone(result)
        result_text, skill_def = result
        self.assertEqual(skill_def["name"], "cost")
        self.assertIn("123", result_text)

    def test_compact_command_forces_history_compaction(self):
        history = [{"role": "user", "content": f"old message {index} " * 30} for index in range(12)]
        state = AgentState(history=list(history))
        result = _dispatch_slash_command(
            "/compact",
            state,
            AgentRunConfig(max_history_messages=4),
            self.all_skills,
            summarizer=lambda messages, existing_summary="": "manual compact summary",
        )

        self.assertIsNotNone(result)
        result_payload, skill_def = result
        self.assertEqual(skill_def["name"], "compact")
        self.assertIn("Context compacted", result_payload["text"])
        self.assertEqual(result_payload["events"][0]["activity_type"], "cc_agent.compression")
        self.assertEqual(result_payload["events"][0]["activity"]["status"], "completed")
        self.assertEqual(result_payload["events"][0]["activity"]["trigger"], "manual")
        self.assertEqual(state.summary, "manual compact summary")
        self.assertLess(len(state.history), len(history))

    def test_help_lists_local_commands_and_prompt_skills_from_shared_registry(self):
        all_skills = [
            {"name": "frontend-design", "kind": "prompt", "description": "Create frontend interfaces"},
            *register_all(),
        ]

        result = _dispatch_slash_command("/help", AgentState(), AgentRunConfig(), all_skills)

        self.assertIsNotNone(result)
        result_text, skill_def = result
        self.assertEqual(skill_def["name"], "help")
        self.assertIn("/help", result_text)
        self.assertIn("frontend-design", result_text)
        self.assertIn("/a2ui-demo", result_text)
        self.assertIn("/weekly-report-card", result_text)

    def test_a2ui_demo_command_returns_structured_payload(self):
        result = _dispatch_slash_command("/a2ui-demo", AgentState(), AgentRunConfig(), self.all_skills)

        self.assertIsNotNone(result)
        result_payload, skill_def = result
        self.assertEqual(skill_def["name"], "a2ui-demo")
        self.assertIsInstance(result_payload, dict)
        self.assertIn("text", result_payload)
        self.assertIn("events", result_payload)

    def test_weekly_report_card_command_returns_structured_payload(self):
        result = _dispatch_slash_command(
            "/weekly-report-card completed A2UI validation; next week use a real report.",
            AgentState(),
            AgentRunConfig(),
            self.all_skills,
        )

        self.assertIsNotNone(result)
        result_payload, skill_def = result
        self.assertEqual(skill_def["name"], "weekly-report-card")
        self.assertIsInstance(result_payload, dict)
        self.assertIn("text", result_payload)
        self.assertIn("events", result_payload)

    def test_prompt_builder_shows_prompt_skills_but_not_local_handlers(self):
        state = AgentState(
            skills=[
                {"name": "frontend-design", "kind": "prompt", "description": "Create frontend interfaces"},
                {"name": "help", "kind": "local", "description": "Show commands", "handler": lambda *_: "help"},
            ]
        )

        system_prompt = PromptBuilder(AgentRunConfig(), state).system_prompt()

        self.assertIn("frontend-design", system_prompt)
        self.assertIn("Slash commands", system_prompt)
        self.assertIn("/help", system_prompt)
        self.assertNotIn("handler", system_prompt)


if __name__ == "__main__":
    unittest.main()
