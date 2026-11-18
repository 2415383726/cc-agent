"""Dify AgentStrategy boundary: only this module constructs SDK messages."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any
from uuid import uuid4

from dify_plugin.entities.agent import AgentInvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.agent import AgentStrategy

try:  # pragma: no cover - SDK runtime packaging
    from dify_plugin.config.logger_format import plugin_logger_handler
except Exception:  # pragma: no cover
    plugin_logger_handler = None

try:
    from pi_strategy.runtime import PiStrategyRuntime
except ImportError:  # pragma: no cover - local tests import by package path
    from pi_strategy.pi_strategy.runtime import PiStrategyRuntime  # type: ignore[no-redef]

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if plugin_logger_handler is not None and plugin_logger_handler not in logger.handlers:
    logger.addHandler(plugin_logger_handler)

# Runtime diagnostics must reach the same daemon-visible channel as the strategy
# logger; a bare getLogger().exception() would go to stderr and vanish.
runtime_logger = logging.getLogger("pi_strategy.runtime")
runtime_logger.setLevel(logging.INFO)
if plugin_logger_handler is not None and plugin_logger_handler not in runtime_logger.handlers:
    runtime_logger.addHandler(plugin_logger_handler)


class PiStrategyNativeStrategy(AgentStrategy):
    def _invoke(self, parameters: dict[str, Any]) -> Generator[AgentInvokeMessage, None, None]:
        logger.info("pi_strategy strategy invoke entered: %s", _parameter_summary(parameters))
        runtime = PiStrategyRuntime(self.session)
        stream = runtime.run(parameters)
        emitted_state = False
        try:
            for message in stream:
                if isinstance(message, dict) and message.get("type") == "state":
                    emitted_state = True
                yield self._dispatch(message)
        except Exception:
            # Never leak a traceback or provider text into the Dify stream.
            logger.exception("pi_strategy strategy failed")
            yield self._dispatch(_strategy_failure_log())
            yield self.create_text_message("The Pi agent run failed.")
        finally:
            stream.close()
        if not emitted_state:
            # Runs that fail before building a request never emit state; re-emit
            # the incoming value so the Dify variable-assigner node still finds
            # the agent_state output and the conversation value stays stable.
            yield self.create_variable_message(
                "agent_state", str(parameters.get("agent_state") or "")
            )
        logger.info("pi_strategy strategy invoke completed")

    def _dispatch(self, message: Any) -> Any:
        if not isinstance(message, dict):
            return self._log("Pi Strategy output", {"value": str(message)}, is_error=True)
        kind = message.get("type")
        if kind == "text":
            return self.create_text_message(str(message.get("content") or ""))
        if kind == "state":
            return self.create_variable_message(
                str(message.get("name") or "agent_state"),
                message.get("value") if message.get("value") is not None else "",
            )
        if kind == "blob":
            blob = message.get("blob")
            meta = message.get("meta") if isinstance(message.get("meta"), dict) else {}
            if not isinstance(blob, (bytes, bytearray)):
                return self._log("Artifact error", {"message": "missing bytes"}, is_error=True)
            filename = str(meta.get("filename") or "artifact")
            return self.create_blob_message(
                blob=bytes(blob),
                meta={
                    "filename": filename,
                    "output_filename": filename,
                    "mime_type": str(meta.get("mime_type") or "application/octet-stream"),
                },
            )
        if kind == "json":
            payload = message.get("payload")
            return self.create_json_message(payload if isinstance(payload, dict) else {})
        if kind == "log":
            data = message.get("data")
            return self._log(
                str(message.get("label") or "Log"),
                data if isinstance(data, dict) else {"value": data},
                is_error=bool(message.get("is_error")),
            )
        return self._log("Pi Strategy output", {"type": str(kind)}, is_error=True)

    def _log(self, label: str, data: dict[str, Any], *, is_error: bool = False) -> Any:
        status = (
            ToolInvokeMessage.LogMessage.LogStatus.ERROR
            if is_error
            else ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
        )
        return self.create_log_message(label=label, data=data, status=status)


def _strategy_failure_log() -> dict[str, Any]:
    """Native log for strategy-level crashes, in the run error shape."""
    return {
        "type": "log",
        "label": "Run error",
        "data": {
            "raw": {
                "code": "agent_failed",
                "stage": "strategy",
                "run_id": f"run_strategy_failed_{uuid4().hex[:12]}",
                "message": "The Pi agent run failed.",
            }
        },
        "is_error": True,
    }


def _files_kind(value: Any) -> str:
    """Shape of the files parameter, for diagnosing host-side casting."""
    if value in (None, ""):
        return "empty"
    if isinstance(value, list):
        head = value[0] if value else None
        return f"list[{type(head).__name__}]{repr(head)[:80]}"
    return f"{type(value).__name__}:{repr(value)[:80]}"


def _parameter_summary(parameters: dict[str, Any]) -> dict[str, Any]:
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
    tools = parameters.get("tools") if isinstance(parameters.get("tools"), list) else []
    runtime_config = parameters.get("runtime_config") or inputs.get("runtime_config")
    return {
        "keys": sorted(str(key) for key in parameters),
        "input_keys": sorted(str(key) for key in inputs),
        "has_model": bool(parameters.get("model")),
        "query_len": len(str(parameters.get("query") or "")),
        "tools_count": len(tools),
        "files_present": bool(parameters.get("files") or inputs.get("files")),
        "files_kind": _files_kind(parameters.get("files") or inputs.get("files")),
        "state_present": bool(parameters.get("agent_state") or inputs.get("agent_state")),
        "skills_present": bool(parameters.get("app_skills_yaml") or inputs.get("app_skills_yaml")),
        "mcp_present": bool(
            parameters.get("mcp_servers_config") or inputs.get("mcp_servers_config")
        ),
        "runtime_config_keys": _config_keys(runtime_config),
        "conversation_id_present": bool(
            parameters.get("conversation_id") or inputs.get("conversation_id")
        ),
    }


def _config_keys(value: Any) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return ["<invalid>"]
    return sorted(str(key) for key in payload) if isinstance(payload, dict) else ["<invalid>"]
