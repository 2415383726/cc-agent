import unittest

from cc_agent.core.agui_stream import AgUiStreamWriter
from cc_agent.core.messages import AgentRunResult


class AgUiStreamWriterTests(unittest.TestCase):
    def test_text_delta_closes_reasoning_before_assistant_text(self):
        writer = AgUiStreamWriter(thread_id="thread-1", run_id="run-1")

        events = []
        events.extend(writer.write_reasoning_delta("thinking"))
        events.extend(writer.write_text_delta("answer"))

        self.assertEqual(
            [event["type"] for event in events],
            [
                "REASONING_START",
                "REASONING_MESSAGE_START",
                "REASONING_MESSAGE_CONTENT",
                "REASONING_MESSAGE_END",
                "REASONING_END",
                "TEXT_MESSAGE_START",
                "TEXT_MESSAGE_CONTENT",
            ],
        )

    def test_tool_call_closes_open_text_and_emits_tool_lifecycle(self):
        writer = AgUiStreamWriter(thread_id="thread-1", run_id="run-1")

        events = []
        events.extend(writer.write_text_delta("before tool"))
        events.extend(writer.write_tool_call("call-1", "Search", {"q": "demo"}))
        events.extend(writer.write_tool_result("call-1", "Search", {"ok": True}))

        self.assertEqual(
            [event["type"] for event in events],
            [
                "TEXT_MESSAGE_START",
                "TEXT_MESSAGE_CONTENT",
                "TEXT_MESSAGE_END",
                "TOOL_CALL_START",
                "TOOL_CALL_ARGS",
                "TOOL_CALL_RESULT",
                "TOOL_CALL_END",
            ],
        )

    def test_tool_calls_can_be_hidden_without_leaving_text_open(self):
        writer = AgUiStreamWriter(thread_id="thread-1", run_id="run-1", show_tool_calls=False)

        events = []
        events.extend(writer.write_text_delta("before tool"))
        events.extend(writer.write_tool_call("call-1", "Search", {"q": "demo"}))
        events.extend(writer.write_tool_result("call-1", "Search", {"ok": True}))

        self.assertEqual([event["type"] for event in events], ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END"])
    def test_run_finished_carries_interrupt_outcome(self):
        writer = AgUiStreamWriter(thread_id="thread-1", run_id="run-1")
        result = AgentRunResult(
            answer="Which account?",
            history=[],
            memory=[],
            tasks=[],
            execution_metadata={
                "finish_reason": "awaiting_user",
                "question": {
                    "tool_call_id": "call-1",
                    "question": "Which account?",
                    "purpose": "clarification",
                    "options": [{"label": "A", "value": "a"}],
                    "fields": [{"name": "reason", "label": "Reason", "type": "textarea"}],
                    "allowCustomInput": True,
                    "multiSelect": False,
                },
            },
        )

        events = writer.write_run_finished(result)

        self.assertEqual(events[-1]["type"], "RUN_FINISHED")
        self.assertEqual(events[-1]["outcome"]["type"], "interrupt")
        self.assertEqual(events[-1]["outcome"]["interrupts"][0]["toolCallId"], "call-1")
        self.assertEqual(
            events[-1]["outcome"]["interrupts"][0]["metadata"]["fields"],
            [{"name": "reason", "label": "Reason", "type": "textarea"}],
        )


if __name__ == "__main__":
    unittest.main()
