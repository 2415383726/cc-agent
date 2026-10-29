"""Dify AgentStrategy boundary: only this module constructs SDK messages."""

from __future__ import annotations

import json
import logging
import time
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
    from pi_agent.runtime import PiAgentRuntime
except ImportError:  # pragma: no cover - local tests import by package path
    from pi_dify.pi_agent.runtime import PiAgentRuntime  # type: ignore[no-redef]

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if plugin_logger_handler is not None and plugin_logger_handler not in logger.handlers:
    logger.addHandler(plugin_logger_handler)


class PiAgentStrategy(AgentStrategy):
    def _invoke(self, parameters: dict[str, Any]) -> Generator[AgentInvokeMessage, None, None]:
        logger.info("pi_dify strategy invoke entered: %s", _parameter_summary(parameters))
        runtime = PiAgentRuntime(self.session)
        stream = runtime.run(parameters)
        try:
            for message in stream:
                yield self._dispatch(message)
        except Exception:
            # Never leak a traceback or provider text into the Dify stream.
            logger.error("pi_dify strategy failed")
            yield self._log(
                "Pi agent failed",
                {
                    "piagent": {
                        "schema": "piagent.display.v1",
                        "schema_version": 1,
                        "type": "agent_failed",
                        "run_id": f"run_strategy_failed_{uuid4().hex[:12]}",
                        "seq": 10**9,
                        "ts": int(time.time() * 1000),
                        "code": "agent_failed",
                        "stage": "strategy",
                        "message": "The Pi agent run failed.",
                    }
                },
                is_error=True,
            )
            yield self.create_text_message("The Pi agent run failed.")
        finally:
            stream.close()
            logger.info("pi_dify strategy invoke completed")

    def _dispatch(self, message: Any) -> Any:
        if not isinstance(message, dict):
            return self._log("Pi output", {"value": str(message)}, is_error=True)
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
                return self._log("Pi blob error", {"message": "missing bytes"}, is_error=True)
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
                str(message.get("label") or "Pi event"),
                data if isinstance(data, dict) else {"value": data},
                is_error=bool(message.get("is_error")),
            )
        return self._log("Pi output", {"type": str(kind)}, is_error=True)

    def _log(self, label: str, data: dict[str, Any], *, is_error: bool = False) -> Any:
        status = (
            ToolInvokeMessage.LogMessage.LogStatus.ERROR
            if is_error
            else ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
        )
        return self.create_log_message(label=label, data=data, status=status)


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
        "state_present": bool(parameters.get("agent_state") or inputs.get("agent_state")),
        "interaction_present": bool(parameters.get("interaction") or inputs.get("interaction")),
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
