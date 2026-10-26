from __future__ import annotations

from collections.abc import Generator
import json
import logging
from typing import Any
from uuid import uuid4

from dify_plugin.entities.agent import AgentInvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.agent import AgentStrategy

try:  # pragma: no cover - depends on SDK runtime packaging
    from dify_plugin.config.logger_format import plugin_logger_handler
except Exception:  # pragma: no cover
    plugin_logger_handler = None

try:
    from core.profiles import StrategyProfile
    from core.runtime import DifyAgentRuntime, prompt_tool_from_any
except ImportError:  # pragma: no cover - used by local tests/imports
    from cc_agent.core.profiles import StrategyProfile
    from cc_agent.core.runtime import DifyAgentRuntime, prompt_tool_from_any


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if plugin_logger_handler is not None and plugin_logger_handler not in logger.handlers:
    logger.addHandler(plugin_logger_handler)

PLUGIN_DEBUG_VERSION = "0.0.3"


class BaseCCAgentStrategy(AgentStrategy):
    runtime_cls = DifyAgentRuntime
    strategy_profile: StrategyProfile

    def _init_prompt_tools(self, tools):
        prompt_tools = []
        sdk_tools = []
        for tool in tools or []:
            prompt_tool = prompt_tool_from_any(tool)
            if prompt_tool is not None:
                prompt_tools.append(prompt_tool)
            elif isinstance(tool, dict):
                logging.warning("Skipping unsupported dict tool shape in CC Agent: keys=%s", sorted(tool.keys()))
            else:
                sdk_tools.append(tool)
        if sdk_tools:
            prompt_tools.extend(super()._init_prompt_tools(sdk_tools))
        return prompt_tools

    def _invoke(self, parameters: dict[str, Any]) -> Generator[AgentInvokeMessage, None, None]:
        logger.info("cc_agent strategy invoke entered: %s", _parameter_summary(parameters))
        runtime = self.runtime_cls(self, strategy_profile=self.strategy_profile)
        try:
            for event in runtime.run(parameters):
                dispatched = self._dispatch_protocol_event(event)
                if isinstance(dispatched, list):
                    yield from dispatched
                else:
                    yield dispatched
            logger.info("cc_agent strategy invoke completed")
        except Exception as exc:
            logger.exception("cc_agent strategy invoke failed")
            yield self._log(
                "Runtime error",
                {"message": str(exc), "code": "cc_agent_error"},
                is_error=True,
            )
            return

    def _log(self, label: str, data: dict[str, Any], metadata: dict[str, Any] | None = None, is_error: bool = False):
        status = ToolInvokeMessage.LogMessage.LogStatus.ERROR if is_error else ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
        return self.create_log_message(label=label, data=data, metadata=_safe_log_metadata(metadata), status=status)

    def _finish_log(self, label: str, data: dict[str, Any], metadata: dict[str, Any] | None = None, is_error: bool = False):
        started = self.create_log_message(
            label=label,
            data={},
            metadata=_safe_log_metadata(metadata),
            status=ToolInvokeMessage.LogMessage.LogStatus.START,
        )
        status = ToolInvokeMessage.LogMessage.LogStatus.ERROR if is_error else ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
        return [
            started,
            self.finish_log_message(
                started,
                status=status,
                data=data,
                metadata=_safe_log_metadata(metadata),
            ),
        ]

    def _agui_log(self, event: dict[str, Any], is_error: bool = False):
        return self._log(f"AG-UI {event.get('type', 'EVENT')}", event, is_error=is_error)

    def _dispatch_protocol_event(self, event: dict[str, Any]):
        if not isinstance(event, dict):
            return self._log("Runtime event", {"value": str(event)}, is_error=True)
        event_type = event.get("type")
        if event_type == "dify_text":
            return self.create_text_message(str(event.get("content") or ""))
        if event_type == "dify_json":
            return self.create_json_message(event.get("payload") if isinstance(event.get("payload"), dict) else {})
        if event_type == "dify_blob":
            blob = event.get("blob")
            if not isinstance(blob, (bytes, bytearray)):
                return self._log("Blob output error", {"message": "dify_blob missing bytes payload"}, is_error=True)
            meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
            filename = str(meta.get("filename") or meta.get("output_filename") or "generated_file")
            mime_type = str(meta.get("mime_type") or meta.get("mime") or "application/octet-stream")
            return self.create_blob_message(
                blob=bytes(blob),
                meta={"filename": filename, "output_filename": filename, "mime_type": mime_type},
            )
        if event_type == "dify_variable":
            return self.create_variable_message(
                str(event.get("name") or "history"),
                event.get("value") if event.get("value") is not None else "",
            )
        if event_type == "dify_log":
            return self._log(
                str(event.get("label") or "Dify log"),
                event.get("data") if isinstance(event.get("data"), dict) else {"value": event.get("data")},
                metadata=event.get("metadata") if isinstance(event.get("metadata"), dict) else None,
                is_error=bool(event.get("is_error")),
            )
        if event_type == "dify_finish_log":
            return self._finish_log(
                str(event.get("label") or "Dify log"),
                event.get("data") if isinstance(event.get("data"), dict) else {"value": event.get("data")},
                metadata=event.get("metadata") if isinstance(event.get("metadata"), dict) else None,
                is_error=bool(event.get("is_error")),
            )
        return [self._agui_log(event, is_error=event_type == "RUN_ERROR")]


def _thread_id(parameters: dict[str, Any]) -> str:
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
    return str(
        parameters.get("conversation_id")
        or parameters.get("thread_id")
        or inputs.get("conversation_id")
        or inputs.get("thread_id")
        or parameters.get("state_id")
        or inputs.get("state_id")
        or "default"
    )


def _run_id(parameters: dict[str, Any]) -> str:
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
    return str(parameters.get("run_id") or inputs.get("run_id") or f"run_{uuid4().hex}")


def _safe_log_metadata(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    allowed = {"started_at", "finished_at", "elapsed_time", "total_price", "total_tokens", "provider", "currency"}
    return {key: value for key, value in (metadata or {}).items() if key in allowed}


def _parameter_summary(parameters: dict[str, Any]) -> dict[str, Any]:
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
    tools = parameters.get("tools") if isinstance(parameters.get("tools"), list) else []
    model = parameters.get("model")
    return {
        "debug_version": PLUGIN_DEBUG_VERSION,
        "keys": sorted(str(key) for key in parameters.keys()),
        "input_keys": sorted(str(key) for key in inputs.keys()),
        "has_model": bool(parameters.get("model")),
        "has_query": bool(str(parameters.get("query") or "").strip()),
        "query_len": len(str(parameters.get("query") or "")),
        "tools_count": len(tools),
        "files_count": _count_items(parameters.get("files") or inputs.get("files")),
        "agent_state_present": bool(parameters.get("agent_state") or inputs.get("agent_state")),
        "state_id": parameters.get("state_id"),
        "input_state_id": inputs.get("state_id"),
        "runtime_config_summary": _runtime_config_summary(parameters.get("runtime_config") or inputs.get("runtime_config")),
        "deepseek_thinking_compat": parameters.get("deepseek_thinking_compat"),
        "input_deepseek_thinking_compat": inputs.get("deepseek_thinking_compat"),
        "app_skills_yaml_present": bool(str(parameters.get("app_skills_yaml") or "").strip()),
        "input_app_skills_yaml_present": bool(str(inputs.get("app_skills_yaml") or "").strip()),
        "app_skills_yaml_len": len(str(parameters.get("app_skills_yaml") or "")),
        "input_app_skills_yaml_len": len(str(inputs.get("app_skills_yaml") or "")),
        "model_history_prompt_count": _count_items(_get(model, "history_prompt_messages")),
    }


def _count_items(value: Any) -> int:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return 1
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return 1
        if isinstance(value, dict):
            value = value.get("files") or value.get("data") or []
    try:
        return len(value or [])
    except TypeError:
        return 0


def _runtime_config_summary(value: Any) -> dict[str, Any]:
    if not value:
        return {"present": False}
    try:
        payload = json.loads(str(value)) if not isinstance(value, dict) else value
        if isinstance(payload, str):
            payload = json.loads(payload)
    except Exception:
        return {"present": True, "valid": False}
    if not isinstance(payload, dict):
        return {"present": True, "valid": False}
    return {"present": True, "valid": True, "keys": sorted(str(key) for key in payload.keys())}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
