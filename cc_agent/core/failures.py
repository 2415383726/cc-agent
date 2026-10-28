from __future__ import annotations

import re
from typing import Any


class AgentRuntimeFailure(RuntimeError):
    def __init__(self, code: str, stage: str, state_ref: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.stage = stage
        self.state_ref = state_ref


def public_failure_message(code: str) -> str:
    return {
        "config_failed": "Agent configuration could not be loaded.",
        "environment_failed": "Agent execution environment could not be initialized.",
        "state_load_failed": "The saved conversation state could not be loaded.",
        "state_save_failed": "Conversation state could not be saved within the variable limit. This turn is not safely resumable.",
        "context_overflow": "The request could not fit within the model context limit.",
        "interrupt_resume_failed": "The pending user interaction could not be resumed.",
        "missing_final_result": "Agent execution ended without a final result.",
        "model_error": "The model provider could not complete this request.",
        "skill_invocation_forbidden": "This skill does not support user invocation.",
    }.get(code, "Agent execution failed.")


def failure_payload(
    code: str, stage: str, run_id: str, error: Exception | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": "agent_failed",
        "code": code,
        "stage": stage,
        "run_id": run_id,
        "message": public_failure_message(code),
    }
    if error is not None:
        name = type(error).__name__
        payload["error_type"] = (
            name if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", name) else "Exception"
        )
    if isinstance(error, AgentRuntimeFailure) and error.state_ref is not None:
        payload["state_ref"] = error.state_ref
    return payload
