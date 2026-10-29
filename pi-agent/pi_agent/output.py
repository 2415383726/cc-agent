"""One-way output projections. Only this module constructs wire protocol messages."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from ag_ui.core import (
    ActivitySnapshotEvent, CustomEvent, ReasoningEndEvent,
    ReasoningMessageContentEvent, ReasoningMessageEndEvent, ReasoningMessageStartEvent,
    ReasoningStartEvent, RunErrorEvent, RunFinishedEvent, RunStartedEvent,
    TextMessageContentEvent, TextMessageEndEvent, TextMessageStartEvent,
    ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent, ToolCallStartEvent,
)

from .events import (
    ActivityChanged, ReasoningDelta, RunEvent, RunFailed, RunStarted, TextDelta,
    ToolCompleted, ToolRequested, TurnEnded,
)


class MessageFactory(Protocol):
    def text(self, value: str) -> Any: ...
    def json(self, value: dict[str, Any]) -> Any: ...
    def log(self, label: str, value: dict[str, Any], *, error: bool = False) -> Any: ...


@dataclass(frozen=True, slots=True)
class OutputContext:
    thread_id: str
    run_id: str
    show_tool_calls: bool = True


class OutputAdapter(Protocol):
    def encode(self, event: RunEvent) -> list[Any]: ...
    def finish(self, payload: dict[str, Any]) -> list[Any]: ...


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _activity_name(kind: str) -> str:
    # Preserve the existing frontend contract without making it a runtime namespace.
    return kind if kind.startswith("cc_agent.") else f"cc_agent.{kind}"


class AgUiOutput:
    def __init__(self, factory: MessageFactory, context: OutputContext):
        self.factory = factory
        self.context = context
        self._text_id: str | None = None
        self._reasoning_id: str | None = None
        self._last_text_id: str | None = None
        self._tool_ids: set[str] = set()

    def _event(self, value: Any) -> Any:
        payload = value.model_dump(by_alias=True, exclude_none=True)
        return self.factory.log(f"AG-UI {payload['type']}", payload,
                                error=payload['type'] == 'RUN_ERROR')

    def _close_reasoning(self) -> list[Any]:
        if self._reasoning_id is None:
            return []
        mid, self._reasoning_id = self._reasoning_id, None
        return [self._event(ReasoningMessageEndEvent(message_id=mid)),
                self._event(ReasoningEndEvent(message_id=mid))]

    def _close(self) -> list[Any]:
        messages = self._close_reasoning()
        if self._text_id is not None:
            messages.append(self._event(TextMessageEndEvent(message_id=self._text_id)))
            self._text_id = None
        return messages

    def encode(self, event: RunEvent) -> list[Any]:
        match event:
            case RunStarted():
                return [self._event(RunStartedEvent(thread_id=self.context.thread_id,
                                                   run_id=self.context.run_id))]
            case TextDelta(text=text) if text:
                messages = self._close_reasoning()
                if self._text_id is None:
                    self._text_id = self._last_text_id = _id("assistant")
                    messages.append(self._event(TextMessageStartEvent(
                        message_id=self._text_id, role="assistant")))
                messages.append(self._event(TextMessageContentEvent(
                    message_id=self._text_id, delta=text)))
                return messages
            case ReasoningDelta(text=text) if text:
                messages: list[Any] = []
                if self._reasoning_id is None:
                    self._reasoning_id = _id("reasoning")
                    messages.extend([self._event(ReasoningStartEvent(message_id=self._reasoning_id)),
                                     self._event(ReasoningMessageStartEvent(
                                         message_id=self._reasoning_id, role="reasoning"))])
                messages.append(self._event(ReasoningMessageContentEvent(
                    message_id=self._reasoning_id, delta=text)))
                return messages
            case TurnEnded():
                return self._close()
            case ToolRequested(call_id=cid, name=name, arguments=args):
                messages = self._close()
                if self.context.show_tool_calls:
                    self._tool_ids.add(cid)
                    messages.extend([self._event(ToolCallStartEvent(
                        tool_call_id=cid, tool_call_name=name, parent_message_id=self._last_text_id)),
                                     self._event(ToolCallArgsEvent(tool_call_id=cid, delta=_json(args)))])
                return messages
            case ToolCompleted(call_id=cid, name=name, observation=observation, is_error=error):
                if not self.context.show_tool_calls:
                    return []
                messages = []
                # A resumed call belongs to an earlier run, but still needs a visible parent.
                if cid not in self._tool_ids:
                    messages.extend(self.encode(ToolRequested(cid, name, {})))
                messages.extend([self._event(ToolCallResultEvent(
                    message_id=_id("tool_result"), tool_call_id=cid, role="tool", content=observation)),
                                 self._event(ToolCallEndEvent(tool_call_id=cid))])
                if error:
                    messages.append(self._event(CustomEvent(name="cc_agent.tool_error", value={
                        "toolName": name, "toolCallId": cid, "observation": observation,
                        "error": {"message": observation}})))
                return messages
            case ActivityChanged(kind=kind, content=content):
                mid = str(content.get("messageId") or content.get("compressionId") or _id("activity"))
                return [self._event(ActivitySnapshotEvent(message_id=mid,
                    activity_type=_activity_name(kind), content=content))]
            case RunFailed(message=message, code=code):
                return [*self._close(), self._event(RunErrorEvent(message=message, code=code))]
        return []

    def finish(self, payload: dict[str, Any]) -> list[Any]:
        messages = self._close()
        event = RunFinishedEvent(thread_id=self.context.thread_id, run_id=self.context.run_id,
                                 result=payload).model_dump(by_alias=True, exclude_none=True)
        metadata = payload.get("execution_metadata") or {}
        question = metadata.get("question") or {}
        if metadata.get("finish_reason") == "awaiting_user" and question:
            event["outcome"] = {"type": "interrupt", "interrupts": [{
                "id": question.get("id") or question.get("tool_call_id"),
                "reason": "awaiting_user", "message": question.get("question") or question.get("text"),
                "toolCallId": question.get("tool_call_id") or question.get("id"),
                "metadata": {key: value for key, value in question.items()
                             if key not in {"id", "question", "text", "tool_call_id"}},
            }]}
        messages.append(self.factory.log("AG-UI RUN_FINISHED", event))
        # Dify's saved answer and legacy clients need the final text channel too.
        if payload.get("answer"):
            messages.append(self.factory.text(str(payload["answer"])))
        return messages


class DifyNativeOutput:
    def __init__(self, factory: MessageFactory, context: OutputContext):
        self.factory = factory
        self.context = context
        self._reasoning = False
        self._text_emitted = False
        self._inputs: dict[str, dict[str, Any]] = {}

    def _close(self) -> list[Any]:
        if not self._reasoning:
            return []
        self._reasoning = False
        return [self.factory.text("</think>")]

    def encode(self, event: RunEvent) -> list[Any]:
        match event:
            case RunStarted():
                return [self.factory.log("Run started", {
                    "threadId": self.context.thread_id, "runId": self.context.run_id})]
            case TextDelta(text=text) if text:
                self._text_emitted = True
                return [*self._close(), self.factory.text(text)]
            case ReasoningDelta(text=text) if text:
                prefix = "" if self._reasoning else "<think>"
                self._reasoning = True
                # Provider content must not be able to close the reasoning wrapper.
                return [self.factory.text(prefix + text.replace("</think>", "&lt;/think&gt;"))]
            case TurnEnded():
                return self._close()
            case ToolRequested(call_id=cid, arguments=args):
                self._inputs[cid] = args
                return self._close()
            case ToolCompleted(call_id=cid, name=name, observation=observation, is_error=error):
                if not self.context.show_tool_calls:
                    return []
                title = "工具执行失败" if error else "工具执行完成"
                card = (f"<details><summary>{title} · {html.escape(name)}</summary>"
                        f"<pre>{html.escape(_json(self._inputs.get(cid, {})))}</pre>"
                        f"<pre>{html.escape(observation[:8000])}</pre></details>")
                return [*self._close(), self.factory.text(card)]
            case ActivityChanged(kind=kind, content=content):
                return [self.factory.log(_activity_name(kind), {
                    "activityType": _activity_name(kind), "content": content})]
            case RunFailed(message=message, code=code):
                return [*self._close(), self.factory.log("Run error", {
                    "message": message, "code": code}, error=True),
                    self.factory.text(f"Agent run failed: {message}")]
        return []

    def finish(self, payload: dict[str, Any]) -> list[Any]:
        messages = self._close()
        if payload.get("answer") and not self._text_emitted:
            messages.append(self.factory.text(str(payload["answer"])))
        messages.append(self.factory.log("Run finished", payload))
        return messages
