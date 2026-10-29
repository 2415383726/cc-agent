from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from types import SimpleNamespace


class ModelUse:
    model = "offline-smoke"
    provider = "fake"
    mode = "chat"

    def model_dump(self, mode: str = "json") -> dict:
        return {"model": self.model, "provider": self.provider, "mode": self.mode}


class LLM:
    def invoke(self, **kwargs):
        if kwargs.get("stream"):
            return iter(
                [
                    {
                        "delta": {
                            "message": {"content": "offline ok"},
                            "usage": {
                                "prompt_tokens": 3,
                                "completion_tokens": 2,
                                "total_tokens": 5,
                            },
                        }
                    }
                ]
            )
        return {"message": {"content": "offline ok"}}


class Tool:
    def invoke(self, **kwargs):
        return [{"type": "text", "message": "tool ok"}]


class Session:
    model = SimpleNamespace(llm=LLM())
    tool = Tool()


def main() -> int:
    from pi_agent.runtime import PiAgentRuntime

    outbox = []
    params = {
        "model": ModelUse(),
        "query": "offline smoke",
        "tools": [],
        "conversation_id": "offline-conv",
        "user_id": "offline-user",
        "runtime_config": json.dumps({"auto_compact": False, "max_model_requests": 4}),
    }
    asyncio.run(PiAgentRuntime(Session()).execute_async(params, outbox.append, threading.Event()))
    state = next((item["value"] for item in outbox if item.get("type") == "state"), "")
    texts = [item.get("content") for item in outbox if item.get("type") == "text"]
    terminal = None
    for item in outbox:
        if item.get("type") == "log":
            payload = (item.get("data") or {}).get("piagent") or {}
            if payload.get("type") == "run.state":
                terminal = payload
    print(
        json.dumps(
            {
                "answer": texts[-1] if texts else "",
                "state_prefix": state[:24],
                "state_bytes": len(state),
                "terminal_status": (terminal or {}).get("status"),
                "model_requests": ((terminal or {}).get("stats") or {}).get("model_requests"),
            }
        )
    )
    return (
        0
        if state.startswith("piagent-state:v1:")
        and terminal
        and terminal.get("status") == "completed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
