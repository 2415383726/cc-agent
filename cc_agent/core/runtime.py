from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any
from uuid import uuid4

from .compression import DifyHistorySummarizer, compression_activity
from .config import AgentRunConfig
from .failures import AgentRuntimeFailure, failure_payload
from .interrupts import UserInterrupts
from .loop import AgentLoop
from .messages import AgentRunResult, AgentState
from .model_adapter import DifyModelAdapter
from .profiles import StrategyProfile
from .protocol_renderer import ProtocolRenderer
from .run_environment import RunEnvironment
from .skill_runtime import SkillRuntime
from .state_backend import DifyStateBackend, empty_state_load
from .tool_adapter import ToolAdapter

try:  # pragma: no cover - only present under Dify plugin runtime
    from dify_plugin.config.logger_format import plugin_logger_handler
except Exception:  # pragma: no cover
    plugin_logger_handler = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if plugin_logger_handler is not None and plugin_logger_handler not in logger.handlers:
    logger.addHandler(plugin_logger_handler)

try:  # pragma: no cover - exercised inside Dify runtime
    from dify_plugin.entities.tool import PromptMessageTool, ToolSelector
except Exception:  # pragma: no cover
    PromptMessageTool = None
    ToolSelector = None


def _dispatch_slash_command(
    query: str,
    state: AgentState,
    config: AgentRunConfig,
    all_skills: list[dict[str, Any]],
    summarizer: Any = None,
    state_id: str = "",
    compression_id: str = "",
) -> tuple[Any, dict[str, Any]] | None:
    """Parse /name args from query and dispatch to matching local skill.

    Returns (result_text, skill_def) for local skills, None otherwise.
    """
    text = str(query or "").strip()
    if not text.startswith("/"):
        return None
    parts = text[1:].split(maxsplit=1)
    if not parts or not parts[0].strip():  # guard: bare "/" or "/ "
        return None
    name = parts[0].strip().lower()
    args = parts[1] if len(parts) > 1 else ""

    for skill in all_skills:
        skill_name = str(skill.get("name") or "").lower()
        if skill_name == name:
            if skill.get("kind") == "local":
                handler = skill.get("handler")
                if not callable(handler):
                    return None
                try:
                    result_text = handler(
                        state,
                        args,
                        config=config,
                        summarizer=summarizer,
                        all_skills=all_skills,
                        state_id=state_id,
                        compression_id=compression_id,
                    )
                except Exception as exc:
                    result_text = f"{name} 执行失败: {exc}"
                return (result_text, skill)
            elif skill.get("kind") == "prompt":
                return ({"skill_args": args}, skill)
            break

    # Skill not found in registry — let LLM handle it
    return None


class DifyAgentRuntime:
    def __init__(self, strategy: Any, strategy_profile: StrategyProfile | None = None):
        self.strategy = strategy
        self.strategy_profile = strategy_profile

    def run(
        self, parameters: dict[str, Any], writer: Any = None
    ) -> Generator[dict[str, Any], None, None]:
        """Yield protocol payloads. AG-UI events are raw dicts; Dify-native events use dify_* types."""
        logger.info(
            "cc_agent runtime run started: parameter_keys=%s",
            sorted(str(key) for key in parameters.keys()),
        )
        try:
            config = AgentRunConfig.from_parameters(
                parameters, strategy_profile=self.strategy_profile
            )
        except Exception as exc:
            run_id = _run_id_from_parameters(parameters)
            fallback_writer = _make_writer(
                (
                    self.strategy_profile.output_protocol
                    if self.strategy_profile is not None
                    else "agui"
                ),
                thread_id=_conversation_id_from_parameters(parameters) or "default",
                run_id=run_id,
            )
            yield from self._failure_events(
                fallback_writer, "config_failed", "configuration", run_id, exc
            )
            return
        logger.info(
            "cc_agent runtime config parsed: output_protocol=%s query_len=%s",
            config.output_protocol,
            len(str(config.query or "")),
        )
        thread_id = (
            _conversation_id_from_parameters(parameters)
            or _get(self.strategy.session, "conversation_id")
            or "default"
        )
        run_id = _run_id_from_parameters(parameters)
        writer = writer or _make_writer(
            config.output_protocol,
            thread_id=str(thread_id),
            run_id=run_id,
            show_tool_calls=config.show_tool_calls,
        )
        conversation_id = (
            _conversation_id_from_parameters(parameters)
            or str(_get(self.strategy.session, "conversation_id") or "").strip()
        )
        state_id = conversation_id
        env: RunEnvironment | None = None

        try:
            for event in writer.write_run_started():
                yield event
            try:
                env = RunEnvironment.open(
                    config=config,
                    parameters=parameters,
                    strategy=self.strategy,
                    thread_id=str(thread_id),
                    run_id=run_id,
                    state_id=state_id,
                    renderer=writer if isinstance(writer, ProtocolRenderer) else None,
                )
            except Exception as exc:
                yield from self._failure_events(
                    writer, "environment_failed", "environment", run_id, exc
                )
                return
            reset_effective = config.state_reset or _is_reset_query(config.query)
            if reset_effective and not config.state_reset:
                config.state_reset = True
            assert env is not None
            loaded = env.load_state()
            if loaded.get("storage_error") and not config.state_reset:
                yield from self._failure_events(writer, "state_load_failed", "state_load", run_id)
                return
            logger.info(
                "cc_agent state loaded: conversation_id=%s state_id=%s loaded_from=%s history_count=%s has_pending_interrupt=%s storage_error=%s",
                conversation_id,
                state_id,
                loaded.get("loaded_from"),
                len(getattr(loaded.get("history_state"), "messages", []) or []),
                bool(
                    isinstance(loaded.get("last_execution_metadata"), dict)
                    and loaded.get("last_execution_metadata", {}).get("finish_reason")
                    == "awaiting_user"
                ),
                bool(loaded.get("storage_error")),
            )
            history_state = loaded["history_state"]
            assert env.skill_catalog is not None
            prompt_skills = env.skill_catalog.list_visible()
            local_skills = env.skill_catalog.local_skills
            if env.skill_catalog.warnings:
                logger.warning(
                    "cc_agent app skills skipped: count=%s warnings=%s",
                    len(env.skill_catalog.warnings),
                    env.skill_catalog.warnings,
                )
            logger.info(
                "cc_agent prompt skills loaded: total=%s skill_warnings=%s",
                len(prompt_skills),
                len(env.skill_catalog.warnings),
            )
            skill_runtime = SkillRuntime(config.max_observation_chars)
            active_skills = env.skill_catalog.restore_active(loaded.get("active_skills") or [])
            state = AgentState(
                history=history_state.messages,
                summary=history_state.summary,
                history_version=history_state.version,
                skills=prompt_skills,
                tasks=loaded["tasks"],
                permissions=loaded.get("permissions") or {},
                active_skills=active_skills,
            )
            summarizer = DifyHistorySummarizer(self.strategy.session, config.model_for("flash"))
            all_skills = prompt_skills + local_skills
            manual_compression_id = ""
            if _slash_command_name(config.query) == "compact":
                manual_compression_id = f"compression:manual:{run_id}"
                yield from writer.write_activity(
                    "cc_agent.compression",
                    compression_activity("started", "manual", manual_compression_id),
                )
            slash_result = _dispatch_slash_command(
                config.query,
                state,
                config,
                all_skills,
                summarizer=summarizer,
                state_id=state_id,
                compression_id=manual_compression_id,
            )
            if slash_result is not None:
                command_payload, skill_def = slash_result
                if skill_def.get("kind") == "prompt":
                    skill_args_text = (
                        str(command_payload.get("skill_args") or "")
                        if isinstance(command_payload, dict)
                        else ""
                    )
                    try:
                        injected = env.skill_catalog.activate(
                            state,
                            str(skill_def.get("name") or ""),
                            skill_args_text,
                            invocation="user",
                        )
                    except PermissionError:
                        raise AgentRuntimeFailure(
                            "skill_invocation_forbidden", "skill_activation"
                        ) from None
                    state.history.append(
                        {
                            "role": "user",
                            "content": injected,
                            "metadata": {
                                "internal": True,
                                "source": "slash_skill",
                                "skill_name": skill_def.get("name"),
                            },
                        }
                    )
                    config.query = skill_args_text or config.query
                    slash_result = None
                else:
                    pass
            if slash_result is not None:
                command_payload, skill_def = slash_result
                result_text = (
                    command_payload
                    if isinstance(command_payload, str)
                    else str(command_payload.get("text") or "")
                )
                command_events = (
                    command_payload.get("events") if isinstance(command_payload, dict) else []
                )
                for event in command_events or []:
                    yield from _command_activity_events(writer, event)
                if result_text:
                    yield from writer.write_text_delta(result_text)
                result = AgentRunResult(
                    answer=result_text,
                    history=state.history,
                    tasks=state.tasks,
                    permissions=state.permissions,
                    active_skills=state.active_skills,
                    execution_metadata={
                        "finish_reason": "command",
                        "command": skill_def["name"],
                        "kind": skill_def.get("kind"),
                        "reset_effective": skill_def.get("name") == "reset" or reset_effective,
                    },
                    events=[],
                    summary=state.summary,
                    history_schema_version=state.history_version,
                )
                for event in self._persist_result(
                    result,
                    config=config,
                    state_id=state_id,
                    loaded_from=loaded["loaded_from"],
                    previous_revision=loaded["previous_revision"],
                    initial_storage_error=loaded["storage_error"],
                ):
                    yield event
                yield from writer.write_run_finished(result)
                if result.encoded_agent_state:
                    yield {
                        "type": "dify_variable",
                        "name": "agent_state",
                        "value": result.encoded_agent_state,
                    }
                    yield {"type": "dify_json", "payload": result.to_json_payload()}
                elif result.state_ref is not None:
                    yield {"type": "dify_json", "payload": result.to_json_payload()}
                return

            external_tools = config.tools or []
            external_prompt_tools = self._init_external_prompt_tools(external_tools)
            tool_catalog = env.build_tool_catalog(
                external_tools=external_tools, external_prompt_tools=external_prompt_tools
            )
            registry = tool_catalog
            model_adapter = DifyModelAdapter(
                session=self.strategy.session,
                model_config=config.model_for("think"),
                stream=config.stream,
                deepseek_thinking_compat=config.deepseek_thinking_compat,
                keep_dify_history=config.use_dify_history,
            )
            tool_adapter = ToolAdapter(
                registry=tool_catalog,
                state=state,
                session=self.strategy.session,
                skill_runtime=skill_runtime,
                mcp_provider=env.mcp_provider,
            )
            interrupts = UserInterrupts(
                state=state, confirmation_tools=set(config.tool_confirmation_list or [])
            )
            if not config.user_prompt_response:
                config.user_prompt_response = interrupts.response_from_query(
                    config.query, loaded["last_execution_metadata"]
                )
            loop = AgentLoop(
                config=config,
                state=state,
                registry=registry,
                model_adapter=model_adapter,
                tool_adapter=tool_adapter,
                summarizer=summarizer,
                include_user_query=True,
                writer=writer,
                interrupts=interrupts,
            )
            if config.user_prompt_response:
                logger.info(
                    "cc_agent interrupt resume requested: conversation_id=%s state_id=%s response_keys=%s last_finish_reason=%s",
                    conversation_id,
                    state_id,
                    sorted(str(key) for key in config.user_prompt_response.keys()),
                    (
                        loaded["last_execution_metadata"].get("finish_reason")
                        if isinstance(loaded["last_execution_metadata"], dict)
                        else None
                    ),
                )
                resumed = interrupts.resume(
                    config,
                    loaded["last_execution_metadata"],
                    execute=lambda call: loop.scheduler.execute([call], 0)[0].result,
                )
                resume_error = resumed.error
                if resume_error:
                    yield from self._failure_events(
                        writer, "interrupt_resume_failed", "interrupt_resume", run_id
                    )
                    return
                yield from interrupts.decision_activities(writer)
                if resumed.result is not None:
                    yield from loop.render_tool_result(resumed.result)
                loop.include_user_query = False

            final_result: AgentRunResult | None = None
            for event in loop.run():
                if isinstance(event, dict):
                    yield event
            final_result = final_result or getattr(loop, "final_result", None)
            if final_result is None:
                yield from self._failure_events(
                    writer, "missing_final_result", "model_loop", run_id
                )
                return
            final_result.execution_metadata["run_id"] = run_id
            for event in self._persist_result(
                final_result,
                config=config,
                state_id=state_id,
                loaded_from=loaded["loaded_from"],
                previous_revision=loaded["previous_revision"],
                initial_storage_error=loaded["storage_error"],
            ):
                yield event
            yield from writer.write_run_finished(final_result)
            if config.output_protocol == "agui" and final_result.answer:
                yield {"type": "dify_text", "content": final_result.answer}
            if final_result.answer:
                yield {
                    "type": "dify_finish_log",
                    "label": "Final answer",
                    "data": {
                        "kind": "cc_agent.final_answer",
                        "answer": final_result.answer,
                        "finish_reason": final_result.execution_metadata.get("finish_reason"),
                    },
                }
            yield {"type": "dify_variable", "name": "answer", "value": final_result.answer or ""}
            if final_result.encoded_agent_state:
                yield {
                    "type": "dify_variable",
                    "name": "agent_state",
                    "value": final_result.encoded_agent_state,
                }
                yield {"type": "dify_json", "payload": final_result.to_output_payload()}
            elif final_result.state_ref is not None:
                yield {"type": "dify_json", "payload": final_result.to_output_payload()}
        except Exception as exc:  # noqa: BLE001 - Runtime boundary; never log raw provider errors.
            code = exc.code if isinstance(exc, AgentRuntimeFailure) else "runtime_failed"
            stage = exc.stage if isinstance(exc, AgentRuntimeFailure) else "runtime"
            yield from self._failure_events(writer, code, stage, run_id, exc)
        finally:
            if env is not None:
                env.close()

    @staticmethod
    def _failure_events(
        writer: Any, code: str, stage: str, run_id: str, error: Exception | None = None
    ):
        payload = failure_payload(code, stage, run_id, error)
        logger.error(
            "cc_agent failed: code=%s stage=%s run_id=%s error_type=%s",
            code,
            stage,
            run_id,
            payload.get("error_type", ""),
        )
        yield from writer.write_run_error(payload["message"], code=code)
        yield {"type": "dify_json", "payload": payload}

    def _init_external_prompt_tools(self, tools: list[Any]) -> list[Any]:
        if not tools:
            return []
        prompt_tools = []
        sdk_tools = []
        for tool in tools:
            prompt_tool = prompt_tool_from_any(tool)
            if prompt_tool is not None:
                prompt_tools.append(prompt_tool)
            elif isinstance(tool, dict):
                logging.warning(
                    "Skipping unsupported dict tool shape: keys=%s", sorted(tool.keys())
                )
            else:
                sdk_tools.append(tool)
        init_prompt_tools = getattr(self.strategy, "_init_prompt_tools", None)
        if init_prompt_tools and sdk_tools:
            prompt_tools.extend(init_prompt_tools(sdk_tools))
        return prompt_tools

    def _persist_result(
        self,
        result: AgentRunResult,
        config: AgentRunConfig,
        state_id: str,
        loaded_from: str,
        previous_revision: int,
        initial_storage_error: str | None,
    ) -> list[dict[str, Any]]:
        DifyStateBackend(config, state_id=state_id).commit(
            result, expected_revision=previous_revision
        )
        state_ref = result.state_ref if isinstance(result.state_ref, dict) else {}
        state_ref["loaded_from"] = loaded_from
        state_ref["storage_error"] = _join_errors(
            initial_storage_error, state_ref.get("storage_error")
        )
        result.state_ref = state_ref
        if not state_ref.get("persisted"):
            raise AgentRuntimeFailure("state_save_failed", "state_save", state_ref)
        logger.info(
            "cc_agent result persisted: conversation_id=%s backend=%s persisted=%s loaded_from=%s answer_chars=%s history_count=%s finish_reason=%s encoded_bytes=%s payload_bytes=%s storage_error=%s storage_warning=%s",
            state_id,
            state_ref.get("backend"),
            state_ref.get("persisted"),
            loaded_from,
            len(str(result.answer or "")),
            len(result.history or []),
            result.execution_metadata.get("finish_reason"),
            state_ref.get("encoded_bytes", 0),
            state_ref.get("payload_bytes", 0),
            state_ref.get("storage_error") or "",
            state_ref.get("storage_warning") or "",
        )
        if not result.encoded_agent_state:
            return []
        return []


def _extract_dify_history(config: AgentRunConfig) -> list[dict[str, Any]]:
    """Extract history_prompt_messages from the Dify model config."""
    model = getattr(config, "model", None) or getattr(config, "_raw_model", None)
    if model is None:
        return []
    raw = _get(model, "history_prompt_messages")
    if not isinstance(raw, list) or not raw:
        return []
    messages: list[dict[str, Any]] = []
    for msg in raw:
        role = _dify_role(msg)
        content = _get(msg, "content") or ""
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text") or part.get("data") or ""))
            content = "\n".join(parts)
        if role and str(content or "").strip():
            messages.append({"role": role, "content": str(content)})
    logger.info("cc_agent dify history extracted: count=%s", len(messages))
    return messages


def _dify_role(msg: Any) -> str:
    role_map = {"user": "user", "assistant": "assistant", "system": "system", "tool": "tool"}
    raw = str(_get(msg, "role") or "").lower()
    return role_map.get(raw, "")


def prompt_tool_from_any(tool: Any) -> Any | None:
    if PromptMessageTool is not None and isinstance(tool, PromptMessageTool):
        return tool
    if isinstance(tool, dict):
        prompt_tool = _prompt_tool_from_prompt_schema(tool)
        if prompt_tool is not None:
            return prompt_tool
    selector = _as_tool_selector(tool)
    if selector is not None:
        return _prompt_tool_from_selector(selector)
    if isinstance(tool, dict):
        return _prompt_tool_from_entity_dict(tool)
    return None


def _load_state(config: AgentRunConfig) -> dict[str, Any]:
    return DifyStateBackend(config, state_id="").load().to_runtime_dict()


def _load_state_from_history_variable(config: AgentRunConfig) -> dict[str, Any]:
    return _load_state(config)


def _empty_loaded_state(loaded_from: str = "temporary") -> dict[str, Any]:
    return empty_state_load(loaded_from).to_runtime_dict()


def _prompt_tool_from_selector(selector: Any) -> Any | None:
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for name, parameter in (_get(selector, "tool_parameters") or {}).items():
        parameter_type = _enum_value(_get(parameter, "type")) or "string"
        parameters["properties"][name] = {
            "type": parameter_type,
            "description": str(_get(parameter, "description") or ""),
        }
        options = _get(parameter, "options")
        if options:
            parameters["properties"][name]["enum"] = [
                _enum_value(_get(option, "value")) for option in options
            ]
        if bool(_get(parameter, "required")):
            parameters["required"].append(name)
    payload = {
        "name": str(_get(selector, "tool_name") or _get(selector, "name") or ""),
        "description": str(
            _get(selector, "tool_description") or _get(selector, "description") or ""
        ),
        "parameters": parameters,
    }
    if not payload["name"]:
        return None
    return _make_prompt_tool(payload)


def _prompt_tool_from_prompt_schema(tool: dict[str, Any]) -> Any | None:
    name = str(tool.get("name") or "")
    parameters = tool.get("parameters")
    if not name or not isinstance(parameters, dict):
        return None
    if parameters.get("type") != "object" and "properties" not in parameters:
        return None
    return _make_prompt_tool(
        {
            "name": name,
            "description": str(tool.get("description") or ""),
            "parameters": {
                "type": "object",
                "properties": parameters.get("properties") or {},
                "required": parameters.get("required") or [],
                **{
                    key: value
                    for key, value in parameters.items()
                    if key not in {"type", "properties", "required"}
                },
            },
        }
    )


def _prompt_tool_from_entity_dict(tool: dict[str, Any]) -> Any | None:
    identity_candidate = tool.get("identity")
    identity = identity_candidate if isinstance(identity_candidate, dict) else {}
    name = str(identity.get("name") or tool.get("tool_name") or tool.get("name") or "")
    if not name:
        return None
    description = tool.get("description") or {}
    if isinstance(description, dict):
        description_text = str(
            description.get("llm")
            or description.get("text")
            or description.get("description")
            or ""
        )
    else:
        description_text = str(description or "")
    if not description_text:
        description_text = str(tool.get("tool_description") or "")
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    raw_parameters = tool.get("parameters") or []
    if isinstance(raw_parameters, dict):
        raw_parameters = raw_parameters.get("parameters") or raw_parameters.get("properties") or []
    for parameter in raw_parameters if isinstance(raw_parameters, list) else []:
        property_name, property_schema, required = _parameter_schema(parameter)
        if not property_name or property_schema is None:
            continue
        parameters["properties"][property_name] = property_schema
        if required:
            parameters["required"].append(property_name)
    return _make_prompt_tool(
        {"name": name, "description": description_text, "parameters": parameters}
    )


def _parameter_schema(parameter: Any) -> tuple[str, dict[str, Any] | None, bool]:
    name = str(_get(parameter, "name") or "")
    if not name:
        return "", None, False
    form = _enum_value(_get(parameter, "form")).lower()
    if form and form != "llm":
        return "", None, False
    parameter_type = _enum_value(_get(parameter, "type")).lower() or "string"
    if parameter_type in {"file", "files"}:
        return "", None, False
    input_schema = _get(parameter, "input_schema")
    if isinstance(input_schema, dict):
        schema = dict(input_schema)
    else:
        if parameter_type in {
            "select",
            "secret-input",
            "secret_input",
            "dynamic-select",
            "dynamic_select",
        }:
            parameter_type = "string"
        schema = {
            "type": parameter_type,
            "description": str(
                _get(parameter, "llm_description") or _get(parameter, "description") or ""
            ),
        }
    options = _get(parameter, "options")
    if options:
        enum_values = [_enum_value(_get(option, "value", option)) for option in options]
        enum_values = [value for value in enum_values if value]
        if enum_values:
            schema["enum"] = enum_values
    return name, schema, bool(_get(parameter, "required"))


def _make_prompt_tool(payload: dict[str, Any]) -> Any:
    if PromptMessageTool is None:
        return payload
    return PromptMessageTool(**payload)


def _as_tool_selector(tool: Any) -> Any | None:
    if ToolSelector is not None and isinstance(tool, ToolSelector):
        return tool
    if not isinstance(tool, dict):
        return None
    if "tool_name" not in tool or "tool_parameters" not in tool:
        return None
    if ToolSelector is None:
        return tool
    try:
        return ToolSelector.model_validate(tool)
    except Exception:
        return tool


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _join_errors(*errors: str | None) -> str | None:
    messages = [str(error) for error in errors if error]
    if not messages:
        return None
    return "; ".join(dict.fromkeys(messages))


def _count_items(value: Any) -> int:
    try:
        return len(value or [])
    except TypeError:
        return 0


def _is_reset_query(query: Any) -> bool:
    return str(query or "").strip().lower() == "/reset"


def _slash_command_name(query: Any) -> str:
    text = str(query or "").strip()
    if not text.startswith("/"):
        return ""
    parts = text[1:].split(maxsplit=1)
    return parts[0].strip().lower() if parts else ""


def _preview(value: Any, limit: int = 120) -> str:
    text = str(value or "").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _conversation_id_from_parameters(parameters: dict[str, Any]) -> str:
    inputs_candidate = parameters.get("inputs")
    inputs = inputs_candidate if isinstance(inputs_candidate, dict) else {}
    return str(parameters.get("conversation_id") or inputs.get("conversation_id") or "").strip()


def _run_id_from_parameters(parameters: dict[str, Any]) -> str:
    inputs_candidate = parameters.get("inputs")
    inputs = inputs_candidate if isinstance(inputs_candidate, dict) else {}
    return str(parameters.get("run_id") or inputs.get("run_id") or f"run_{uuid4().hex}")


def _make_writer(
    output_protocol: str, thread_id: str, run_id: str, show_tool_calls: bool = True
) -> Any:
    return ProtocolRenderer(
        output_protocol, thread_id=thread_id, run_id=run_id, show_tool_calls=show_tool_calls
    )


def _command_activity_events(writer: Any, event: Any) -> list[dict[str, Any]]:
    if isinstance(event, dict):
        activity_type = event.get("activity_type")
        activity = event.get("activity")
        if activity_type and isinstance(activity, dict):
            return writer.write_activity(str(activity_type), activity)
        if event.get("type") == "activity" and event.get("activityType"):
            return writer.write_activity(
                str(event.get("activityType")),
                event.get("content") if isinstance(event.get("content"), dict) else {},
            )
        return [event]
    operations = getattr(event, "operations", None)
    if operations is not None:
        return writer.write_activity("a2ui-surface", {"a2ui_operations": operations})
    return []


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
