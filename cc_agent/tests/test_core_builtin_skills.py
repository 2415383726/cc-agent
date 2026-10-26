import unittest

from cc_agent.core.builtin_skills import register_all
from cc_agent.core.config import AgentRunConfig
from cc_agent.core.messages import AgentState


class BuiltinSkillsTests(unittest.TestCase):
    def test_register_all_returns_expected_local_skills(self):
        skills = register_all()
        self.assertEqual(len(skills), 6)
        names = [s["name"] for s in skills]
        self.assertEqual(
            names,
            [
                "help",
                "status",
                "context",
                "cost",
                "compact",
                "reset",
            ],
        )
        for skill in skills:
            self.assertEqual(skill["kind"], "local")
            self.assertTrue(callable(skill["handler"]))
            self.assertIsInstance(skill["description"], str)

    def test_status_handler_reports_session_counts(self):
        skills = {s["name"]: s for s in register_all()}
        state = AgentState(
            history=[{"role": "user", "content": "hi"}],
            tasks=[{"id": "1", "subject": "ship"}],
        )
        result = skills["status"]["handler"](state, "")
        self.assertIn("history messages", result)
        self.assertIn("1", result)

    def test_context_handler_reports_history_and_summary(self):
        skills = {s["name"]: s for s in register_all()}
        state = AgentState(
            history=[{"role": "user", "content": "older"}],
            summary="user selected Dify workflow state",
        )
        result = skills["context"]["handler"](state, "", config=AgentRunConfig())
        self.assertIn("Context", result)
        self.assertIn("summary", result)

    def test_cost_handler_reports_usage(self):
        skills = {s["name"]: s for s in register_all()}
        state = AgentState(
            history=[
                {"role": "assistant", "content": "done", "usage": {"total_tokens": 123}},
            ],
        )
        result = skills["cost"]["handler"](state, "")
        self.assertIn("123", result)

    def test_compact_handler_reduces_history(self):
        skills = {s["name"]: s for s in register_all()}
        history = [{"role": "user", "content": f"old message {index} " * 30} for index in range(12)]
        state = AgentState(history=list(history))
        result = skills["compact"]["handler"](
            state,
            "",
            config=AgentRunConfig(max_history_messages=4),
            summarizer=lambda messages, existing_summary="": "manual compact summary",
        )
        self.assertIn("Context compacted", result["text"])
        self.assertEqual(result["events"][0]["activity_type"], "cc_agent.compression")
        self.assertEqual(result["events"][0]["activity"]["status"], "completed")
        self.assertEqual(result["events"][0]["activity"]["trigger"], "manual")
        self.assertEqual(state.summary, "manual compact summary")
        self.assertLess(len(state.history), len(history))

    def test_reset_handler_clears_all_persisted_state_fields(self):
        skills = {s["name"]: s for s in register_all()}
        state = AgentState(
            history=[{"role": "user", "content": "old"}],
            summary="old summary",
            tasks=[{"id": "old-task"}],
        )

        result = skills["reset"]["handler"](state, "")

        self.assertIn("State reset", result)
        self.assertEqual(state.history, [])
        self.assertEqual(state.summary, "")
        self.assertEqual(state.tasks, [])

    def test_help_handler_lists_all_skills(self):
        skills = {s["name"]: s for s in register_all()}
        all_skills = list(register_all()) + [
            {"name": "frontend-design", "kind": "prompt", "description": "Create frontend interfaces"},
            {"name": "brainstorming", "kind": "prompt", "description": "Turn ideas into designs"},
        ]
        result = skills["help"]["handler"](AgentState(), "", all_skills=all_skills)
        self.assertIn("Available commands", result)
        self.assertIn("/help", result)
        self.assertIn("/status", result)
        self.assertIn("Available skills", result)
        self.assertIn("frontend-design", result)
        self.assertIn("brainstorming", result)

    def test_unknown_command_handler_not_in_registry(self):
        skills = register_all()
        names = [s["name"] for s in skills]
        self.assertNotIn("nonexistent", names)




if __name__ == "__main__":
    unittest.main()
