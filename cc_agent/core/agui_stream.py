from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from ag_ui.core import (
    ActivitySnapshotEvent,
    BaseEvent,
    CustomEvent,
    ReasoningEndEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    ReasoningStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)

from .messages import AgentRunResult


UI_CARD_TOOL_NAMES = {
    "ui_show_person_card",
    "ui_show_people_compare",
    "ui_show_roster_table",
    "ui_open_feature_card",
}


class AgUiStreamWriter:
    """Stateful AG-UI event writer for one agent run."""

    def __init__(self, thread_id: str, run_id: str, show_tool_calls: bool = True):
        self.thread_id = thread_id or "default"
        self.run_id = run_id or f"run_{uuid4().hex}"
        self.show_tool_calls = bool(show_tool_calls)
        self._reasoning_message_id = ""
        self._text_message_id = ""
        self._reasoning_open = False
        self._text_open = False
        self._tool_names: dict[str, str] = {}
        self._tool_inputs: dict[str, Any] = {}

    def write_run_started(self) -> list[dict[str, Any]]:
        return [self._event(RunStartedEvent(thread_id=self.thread_id, run_id=self.run_id))]

    def write_reasoning_delta(self, text: Any, iteration: int = 0) -> list[dict[str, Any]]:
        value = _non_empty_text(text)
        if value is None:
            return []
        events: list[dict[str, Any]] = []
        if not self._reasoning_open:
            self._reasoning_message_id = _message_id("reasoning")
            self._reasoning_open = True
            events.extend(
                [
                    self._event(ReasoningStartEvent(message_id=self._reasoning_message_id)),
                    self._event(
                        ReasoningMessageStartEvent(
                            message_id=self._reasoning_message_id,
                            role="reasoning",
                        )
                    ),
                ]
            )
        events.append(self._event(ReasoningMessageContentEvent(message_id=self._reasoning_message_id, delta=value)))
        return events

    def write_text_delta(self, text: Any, iteration: int = 0) -> list[dict[str, Any]]:
        value = _non_empty_text(text)
        if value is None:
            return []
        events = self.close_reasoning()
        if not self._text_open:
            self._text_message_id = _message_id("assistant")
            self._text_open = True
            events.append(self._event(TextMessageStartEvent(message_id=self._text_message_id, role="assistant")))
        events.append(self._event(TextMessageContentEvent(message_id=self._text_message_id, delta=value)))
        return events

    def write_tool_call(self, tool_call_id: str, tool_name: str, arguments: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        events = [*self.close_reasoning(), *self.close_text()]
        tc_id = str(tool_call_id or _message_id("tool"))
        name = str(tool_name or "unknown_tool")
        args = arguments if isinstance(arguments, dict) else {}
        self._tool_names[tc_id] = name
        self._tool_inputs[tc_id] = args
        if not self.show_tool_calls:
            return events
        events.append(
            self._event(
                ToolCallStartEvent(
                    tool_call_id=tc_id,
                    tool_call_name=name,
                    parent_message_id=self._text_message_id or None,
                )
            )
        )
        events.append(self._event(ToolCallArgsEvent(tool_call_id=tc_id, delta=_json_compact(args))))
        return events

    def write_tool_result(
        self,
        tool_call_id: str,
        tool_name: str = "",
        observation: Any = None,
        *,
        output: Any = None,
        is_error: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        tc_id = str(tool_call_id or _message_id("tool"))
        name = str(tool_name or self._tool_names.get(tc_id) or "unknown_tool")
        if not self.show_tool_calls:
            return []
        metadata = metadata if isinstance(metadata, dict) else {}
        visible_observation = observation if observation is not None else output
        content = _content_string(visible_observation)
        events = [
            self._event(
                ToolCallResultEvent(
                    message_id=_message_id("tool_result"),
                    tool_call_id=tc_id,
                    content=content,
                    role="tool",
                )
            ),
            self._event(ToolCallEndEvent(tool_call_id=tc_id)),
        ]
        if is_error:
            events.append(
                self.write_custom(
                    "cc_agent.tool_error",
                    {
                        "toolName": name,
                        "toolCallId": tc_id,
                        "observation": content,
                        "error": metadata.get("error") or {"message": content or "Tool call failed"},
                    },
                )[0]
            )
        if name in UI_CARD_TOOL_NAMES:
            events.append(
                self.write_custom(
                    "cc_agent.ui_card",
                    {
                        "toolName": name,
                        "toolCallId": tc_id,
                        "input": metadata.get("input") if metadata.get("input") is not None else self._tool_inputs.get(tc_id),
                        "output": output if output is not None else ({"value": observation} if observation is not None else None),
                        "observation": observation,
                        **({"messageId": metadata["message_id"]} if metadata.get("message_id") else {}),
                    },
                )[0]
            )
        return events

    def write_custom(self, name: str, value: Any) -> list[dict[str, Any]]:
        return [self._event(CustomEvent(name=name, value=value))]

    def write_activity(self, activity_type: str, content: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = content if isinstance(content, dict) else {}
        message_id = str(payload.get("messageId") or payload.get("compressionId") or _message_id("activity"))
        return [
            self._event(
                ActivitySnapshotEvent(
                    message_id=message_id,
                    activity_type=str(activity_type or "activity"),
                    content=payload,
                )
            )
        ]

    def write_run_finished(self, result: Any) -> list[dict[str, Any]]:
        event = self._event(
            RunFinishedEvent(
                thread_id=self.thread_id,
                run_id=self.run_id,
                result=_result_payload(result),
            )
        )
        outcome = self._run_finished_outcome(result)
        if outcome:
            event["outcome"] = outcome
        return [*self.close_reasoning(), *self.close_text(), event]

    def write_run_error(self, message: Any, code: str | None = None) -> list[dict[str, Any]]:
        return [
            *self.close_reasoning(),
            *self.close_text(),
            self._event(
                RunErrorEvent(
                    message=str(message or "Agent run failed"),
                    code=str(code) if code else None,
                )
            ),
        ]

    def close_reasoning(self) -> list[dict[str, Any]]:
        if not self._reasoning_open:
            return []
        message_id = self._reasoning_message_id
        self._reasoning_open = False
        self._reasoning_message_id = ""
        return [
            self._event(ReasoningMessageEndEvent(message_id=message_id)),
            self._event(ReasoningEndEvent(message_id=message_id)),
        ]

    def close_text(self) -> list[dict[str, Any]]:
        if not self._text_open:
            return []
        message_id = self._text_message_id
        self._text_open = False
        self._text_message_id = ""
        return [self._event(TextMessageEndEvent(message_id=message_id))]

    def close_open_messages(self) -> list[dict[str, Any]]:
        return [*self.close_reasoning(), *self.close_text()]

    def _event(self, event: BaseEvent) -> dict[str, Any]:
        return event.model_dump(by_alias=True, exclude_none=True)

    def _run_finished_outcome(self, result: Any) -> dict[str, Any] | None:
        if not isinstance(result, AgentRunResult):
            return None
        metadata = result.execution_metadata if isinstance(result.execution_metadata, dict) else {}
        if metadata.get("finish_reason") != "awaiting_user":
            return None
        question = metadata.get("question")
        if not isinstance(question, dict):
            return None
        tool_call_id = str(question.get("tool_call_id") or question.get("id") or "").strip()
        message = str(question.get("question") or question.get("text") or "").strip()
        if not tool_call_id or not message:
            return None
        interrupt_metadata = _drop_none(
            {
                "purpose": question.get("purpose"),
                "options": question.get("options"),
                "fields": question.get("fields"),
                "multiSelect": question.get("multiSelect"),
                "allowCustomInput": question.get("allowCustomInput"),
                "tool_name": question.get("tool_name"),
            }
        )
        return {
            "type": "interrupt",
            "interrupts": [
                _drop_none(
                    {
                        "id": tool_call_id,
                        "reason": "awaiting_user",
                        "message": message,
                        "toolCallId": tool_call_id,
                        "metadata": interrupt_metadata or None,
                    }
                )
            ],
        }


def _result_payload(result: Any) -> Any:
    if isinstance(result, AgentRunResult):
        return result.to_json_payload()
    if hasattr(result, "to_json_payload"):
        return result.to_json_payload()
    return result


def _non_empty_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _json_compact(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def _content_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return _json_compact(value)


def _message_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
