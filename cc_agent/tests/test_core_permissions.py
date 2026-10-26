import unittest

from cc_agent.core.messages import AgentState, ToolCall
from cc_agent.core.interrupts import UserInterrupts, apply_permission_decision


class UserInterruptsTests(unittest.TestCase):
    def test_external_tool_does_not_require_permission_by_default(self):
        state = AgentState(permissions={})
        manager = UserInterrupts(state,)

        result = manager.before_call(ToolCall(id="call-1", name="current_time", arguments={"timezone": "UTC"}))

        self.assertIsNone(result)

    def test_confirmation_list_tool_requires_permission_until_allowed_for_conversation(self):
        state = AgentState(permissions={})
        manager = UserInterrupts(
            state,
            confirmation_tools={"current_time"},
        )

        pending = manager.before_call(ToolCall(id="call-1", name="current_time", arguments={"timezone": "UTC"}))

        self.assertIsNotNone(pending)
        self.assertTrue(pending.metadata["requires_user_input"])
        self.assertEqual(pending.metadata["permission_request"]["tool_name"], "current_time")

        apply_permission_decision(
            state,
            {"selectedValues": ["allow_conversation"]},
            pending.metadata,
        )

        self.assertEqual(state.permissions["allowed_tools"]["current_time"], "conversation")
        self.assertIsNone(manager.before_call(ToolCall(id="call-2", name="current_time", arguments={})))

    def test_allow_once_does_not_persist_permission(self):
        state = AgentState(permissions={})
        manager = UserInterrupts(state, confirmation_tools={"current_time"})
        pending = manager.before_call(ToolCall(id="call-1", name="current_time", arguments={}))

        apply_permission_decision(state, {"selectedValues": ["allow_once"]}, pending.metadata)

        self.assertEqual(state.permissions.get("allowed_tools", {}), {})

    def test_removed_file_tool_names_are_not_special_cased(self):
        state = AgentState(permissions={})
        manager = UserInterrupts(state)

        for name in ("read_file", "write_file", "workspace_list", "run_skill_script"):
            result = manager.before_call(ToolCall(id=f"call-{name}", name=name, arguments={}))

            self.assertIsNone(result)

    def test_removed_file_tool_name_can_still_be_confirmed_explicitly(self):
        state = AgentState(permissions={})
        manager = UserInterrupts(state, confirmation_tools={"read_file"})

        result = manager.before_call(
            ToolCall(id="call-1", name="read_file", arguments={"url": "https://example.com/PLAN.md"})
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.metadata["requires_user_input"])

        apply_permission_decision(state, {"selectedValues": ["allow_conversation"]}, result.metadata)
        self.assertEqual(state.permissions["allowed_tools"]["read_file"], "conversation")

    def test_run_python_is_allowed_by_default_but_can_be_confirmed_explicitly(self):
        state = AgentState(permissions={})
        default_manager = UserInterrupts(state)

        self.assertIsNone(default_manager.before_call(ToolCall(id="call-1", name="run_python", arguments={})))

        confirm_manager = UserInterrupts(state, confirmation_tools={"run_python"})
        pending = confirm_manager.before_call(ToolCall(id="call-2", name="run_python", arguments={"code": "print(1)"}))

        self.assertIsNotNone(pending)
        self.assertTrue(pending.metadata["requires_user_input"])
        self.assertEqual(pending.metadata["permission_request"]["tool_name"], "run_python")

    def test_confirmation_list_overrides_default_safe_internal_tools(self):
        state = AgentState(permissions={})
        manager = UserInterrupts(state, confirmation_tools={"SkillList"})

        pending = manager.before_call(ToolCall(id="call-1", name="SkillList", arguments={}))

        self.assertIsNotNone(pending)
        self.assertTrue(pending.metadata["requires_user_input"])
        self.assertEqual(pending.metadata["permission_request"]["tool_name"], "SkillList")


if __name__ == "__main__":
    unittest.main()
