import unittest
from types import SimpleNamespace

from cc_agent.core.app_skills import load_app_skills
from cc_agent.core.config import AgentRunConfig
from cc_agent.core.runtime import DifyAgentRuntime


class AppSkillsTests(unittest.TestCase):
    def test_parses_yaml_list_with_block_instructions_and_inline_tools(self):
        config = AgentRunConfig.from_parameters(
            {
                "query": "hello",
                "app_skills_yaml": """
- name: sales-summary
  display_name: Sales Summary
  description: Summarize sales weekly reports
  when_to_use: Use for sales reports
  argument_hint: raw weekly notes
  allowed_tools: [MemorySearch, TaskList]
  instructions: |
    You are a sales report assistant.
    Include progress, risks, and next steps.
""",
            }
        )

        snapshot = load_app_skills(config.app_skills_yaml)

        self.assertEqual(snapshot.warnings, [])
        self.assertEqual(len(snapshot.skills), 1)
        skill = snapshot.skills[0]
        self.assertEqual(skill["name"], "sales-summary")
        self.assertEqual(skill["display_name"], "Sales Summary")
        self.assertEqual(skill["description"], "Summarize sales weekly reports")
        self.assertEqual(skill["when_to_use"], "Use for sales reports")
        self.assertEqual(skill["argument_hint"], "raw weekly notes")
        self.assertEqual(skill["allowed_tools"], ["MemorySearch", "TaskList"])
        self.assertEqual(skill["kind"], "prompt")
        self.assertEqual(skill["source"], "app")
        self.assertIn("sales report assistant", skill["body"])
        self.assertIn("next steps", skill["body"])

    def test_parses_allowed_tools_as_indented_list(self):
        snapshot = load_app_skills(
            """
- name: policy-explainer
  description: Explain policies
  allowed_tools:
    - MemorySearch
    - TaskList
  instructions: |
    Explain the policy clearly.
"""
        )

        self.assertEqual(snapshot.warnings, [])
        self.assertEqual(snapshot.skills[0]["allowed_tools"], ["MemorySearch", "TaskList"])

    def test_skips_invalid_and_conflicting_skills(self):
        snapshot = load_app_skills(
            """
- name: meeting-notes
  description: Conflicts with bundled skill
  instructions: |
    Should be skipped.
- name: bad name
  description: Invalid name
  instructions: |
    Should also be skipped.
- name: valid-app-skill
  description: Valid app skill
  instructions: |
    Keep this one.
""",
            reserved_names={"meeting-notes", "help"},
        )

        self.assertEqual([skill["name"] for skill in snapshot.skills], ["valid-app-skill"])
        reasons = " ".join(warning["reason"] for warning in snapshot.warnings)
        self.assertIn("conflicts", reasons)
        self.assertIn("invalid name", reasons)

    def test_invalid_yaml_does_not_raise(self):
        snapshot = load_app_skills("- name sales-summary\n  description: missing colon")

        self.assertEqual(snapshot.skills, [])
        self.assertTrue(snapshot.warnings)

    def test_agent_run_config_reads_top_level_before_inputs(self):
        config = AgentRunConfig.from_parameters(
            {
                "query": "hello",
                "app_skills_yaml": "top-level",
                "inputs": {"app_skills_yaml": "input-level"},
            }
        )

        self.assertEqual(config.app_skills_yaml, "top-level")

    def test_runtime_help_lists_app_skills(self):
        runtime = DifyAgentRuntime(SimpleNamespace(session=SimpleNamespace(conversation_id="test-conversation")))

        events = list(
            runtime.run(
                {
                    "query": "/help",
                    "output_protocol": False,
                    "conversation_id": "test-conversation",
                    "app_skills_yaml": """
- name: sales-summary
  description: Summarize sales weekly reports
  instructions: |
    Write a concise sales weekly report.
""",
                }
            )
        )

        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "dify_text")
        self.assertIn("sales-summary", text)
        self.assertIn("Summarize sales weekly reports", text)


if __name__ == "__main__":
    unittest.main()
