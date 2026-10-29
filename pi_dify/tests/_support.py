"""Test support: fake Dify session objects and outbox helpers."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pi_agent.runtime import PiAgentRuntime


class FakeModelUse:
    def __init__(self, name: str = "test-model"):
        self.model = name
        self.provider = "fake"
        self.mode = "chat"

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"model": self.model, "provider": self.provider, "mode": self.mode}


class FakeLLM:
    def __init__(self, responses: list[Any]):
        self.responses = deque(responses)
        self.calls: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected model request")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        if kwargs.get("stream"):
            return iter(response)
        return response


class FakeTool:
    def __init__(self, responses: list[Any] | None = None):
        self.responses = deque(responses or [])
        self.calls: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self.responses:
            return [{"type": "text", "message": "tool ok"}]
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class FakeSession:
    def __init__(self, responses: list[Any], tool_responses: list[Any] | None = None):
        self.model = SimpleNamespace(llm=FakeLLM(responses))
        self.tool = FakeTool(tool_responses)


def text_chunks(text: str, usage: dict[str, int] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "delta": {
                "message": {"content": text},
                "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        }
    ]


def tool_chunks(calls: list[dict[str, Any]], *, content: str = "") -> list[dict[str, Any]]:
    return [
        {
            "delta": {
                "message": {
                    "content": content,
                    "tool_calls": [
                        {
                            "index": index,
                            "id": call.get("id") or f"call_{index}",
                            "function": {
                                "name": call["name"],
                                "arguments": call.get("arguments", "{}"),
                            },
                        }
                        for index, call in enumerate(calls)
                    ],
                }
            }
        }
    ]


def nonstream_text(text: str) -> dict[str, Any]:
    return {"message": {"content": text}, "usage": {"prompt_tokens": 5, "completion_tokens": 2}}


def base_parameters(
    *,
    query: str = "hello",
    tools: list[Any] | None = None,
    runtime: dict[str, Any] | None = None,
    state: str = "",
    interaction: dict[str, Any] | None = None,
    conversation_id: str = "conv-1",
    app_skills_yaml: str = "",
) -> dict[str, Any]:
    config = {
        "auto_compact": False,
        "max_model_requests": 8,
        "max_tool_calls": 8,
        "max_wall_seconds": 300,
        "state_max_encoded_bytes": 190_000,
    }
    config.update(runtime or {})
    return {
        "model": FakeModelUse(),
        "query": query,
        "tools": tools or [],
        "conversation_id": conversation_id,
        "user_id": "user-1",
        "app_skills_yaml": app_skills_yaml,
        "agent_state": state,
        "runtime_config": json.dumps(config),
        **({"interaction": json.dumps(interaction)} if interaction else {}),
    }


def run_turn(
    session: FakeSession, parameters: dict[str, Any], *, stop: threading.Event | None = None
) -> list[dict[str, Any]]:
    outbox: list[dict[str, Any]] = []
    runtime = PiAgentRuntime(session)
    asyncio.run(runtime.execute_async(parameters, outbox.append, stop or threading.Event()))
    return outbox


def display_events(outbox: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for item in outbox:
        if item.get("type") == "log":
            payload = (item.get("data") or {}).get("piagent")
            if isinstance(payload, dict):
                events.append(payload)
    return events


def event_types(outbox: list[dict[str, Any]]) -> list[str]:
    return [event.get("type") for event in display_events(outbox)]


def last_state(outbox: list[dict[str, Any]]) -> str:
    values = [item["value"] for item in outbox if item.get("type") == "state"]
    return values[-1] if values else ""


def last_terminal(outbox: list[dict[str, Any]]) -> dict[str, Any]:
    states = [event for event in display_events(outbox) if event.get("type") == "run.state"]
    return states[-1] if states else {}


def answer_text(outbox: list[dict[str, Any]]) -> str:
    texts = [item.get("content") for item in outbox if item.get("type") == "text"]
    return texts[-1] if texts else ""


def prompt_texts(llm: FakeLLM, index: int = -1) -> list[str]:
    call = llm.calls[index]
    return [
        str(getattr(message, "content", "") or "") for message in call.get("prompt_messages") or []
    ]
