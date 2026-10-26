from __future__ import annotations

from collections.abc import Generator
import logging
from typing import Any
from uuid import uuid4

from .config import AgentRunConfig
from .compression import DifyHistorySummarizer
from .history import load_history
from .loop import AgentLoop
from .messages import AgentRunResult, AgentState, ToolCall
from .model_adapter import DifyModelAdapter
from .permissions import PermissionManager, apply_permission_decision, permission_decision
from .profiles import StrategyProfile
from .protocol_renderer import ProtocolRenderer
from .run_environment import RunEnvironment, storage_config_from_settings
from .skill_library import SkillLibrarySession, SkillScope
from .skill_runtime import SkillRuntime
from .skills import filter_denied_skills, load_bundled_skills, render_skill
from .state_backend import DifyStateBackend, empty_state_load
from .state_variable import (
    AgentStateBundle,
    bundle_from_parts,
    state_summary,
)
from .tool_adapter import ToolAdapter
from .workspace import (
    HistoryStoreConflict,
    StateStoreConflict,
    WorkspaceSession,
    WorkspaceScope,
    load_history_from_storage,
    load_state_from_storage,
    save_history_to_storage,
    save_state_to_storage,
    state_key,
)

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
    skill_library: Any = None,
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
                        workspace=getattr(state, "workspace", None),
                        skill_library=skill_library or getattr(state, "skill_library", None),
                    )
                except Exception as exc:
                    result_text = f"{name} 执行失败: {exc}"
                return (result_text, skill)
            elif skill.get("kind") == "prompt":
                return ({"skill_args": args}, skill)
            break

    # Skill not found in registry — let LLM handle it
    return None


def _merge_prompt_skills(
    bundled_skills: list[dict[str, Any]],
    minio_skills: list[dict[str, Any]],
    warnings: Any = None,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill in bundled_skills:
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        merged.append(skill)
        seen.add(name.lower())
    for skill in minio_skills:
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        if name.lower() in seen:
            if isinstance(warnings, list):
                warnings.append(
                    {
                        "path": str(skill.get("path") or skill.get("source") or name),
                        "reason": f"skill name conflicts with bundled skill: {name}",
                    }
                )
            continue
        merged.append(skill)
        seen.add(name.lower())
    return merged


class DifyAgentRuntime:
    def __init__(self, strategy: Any, strategy_profile: StrategyProfile | None = None):
        self.strategy = strategy
        self.strategy_profile = strategy_profile

    def run(self, parameters: dict[str, Any], writer: Any = None) -> Generator[dict[str, Any], None, None]:
        """Yield protocol payloads. AG-UI events are raw dicts; Dify-native events use dify_* types."""
        logger.info("cc_agent runtime run started: parameter_keys=%s", sorted(str(key) for key in parameters.keys()))
        try:
            config = AgentRunConfig.from_parameters(
                parameters,
                strategy_profile=self.strategy_profile,
            )
        except Exception as exc:
            fallback_writer = _make_writer(
                self.strategy_profile.output_protocol if self.strategy_profile is not None else "agui",
                thread_id=_conversation_id_from_parameters(parameters) or "default",
                run_id=_run_id_from_parameters(parameters),
            )
            yield from fallback_writer.write_run_error(str(exc), code="config_failed")
            return
        logger.info(
            "cc_agent runtime config parsed: output_protocol=%s query_len=%s",
            config.output_protocol,
            len(str(config.query or "")),
        )
        thread_id = _conversation_id_from_parameters(parameters) or _get(self.strategy.session, "conversation_id") or "default"
        run_id = _run_id_from_parameters(parameters)
        writer = writer or _make_writer(
            config.output_protocol,
            thread_id=str(thread_id),
            run_id=run_id,
            show_tool_calls=config.show_tool_calls,
        )
        conversation_id = _conversation_id_from_parameters(parameters) or str(_get(self.strategy.session, "conversation_id") or "").strip()
        state_id = config.storage.scope.conversation_id if config.workspace_requested else conversation_id
        workspace: WorkspaceSession | None = None
        skill_library: SkillLibrarySession | None = None
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
                    workspace_session_cls=WorkspaceSession,
                    skill_library_cls=SkillLibrarySession,
                )
                workspace = env.workspace
                skill_library = env.skill_library
            except Exception as exc:
                yield from writer.write_run_error(str(exc), code="workspace_config_failed")
                return
            if workspace is not None and workspace.imported_files:
                yield from writer.write_activity(
                    "cc_agent.uploaded_files",
                    {"message": "Files imported to workspace.", "files": workspace.imported_files},
                )
            reset_effective = config.state_reset or _is_reset_query(config.query)
            if reset_effective and not config.state_reset:
                config.state_reset = True
            assert env is not None
            loaded = env.load_state()
            if loaded.get("storage_error") and not config.state_reset:
                yield from writer.write_run_error(str(loaded["storage_error"]), code="state_load_failed")
                return
            logger.info(
                "cc_agent state loaded: conversation_id=%s state_id=%s loaded_from=%s history_count=%s has_pending_interrupt=%s storage_error=%s",
                conversation_id,
                state_id,
                loaded.get("loaded_from"),
                len(getattr(loaded.get("history_state"), "messages", []) or []),
                bool(
                    isinstance(loaded.get("last_execution_metadata"), dict)
                    and loaded.get("last_execution_metadata", {}).get("finish_reason") == "awaiting_user"
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
            skill_runtime = SkillRuntime(
                workspace_root=workspace.outputs_dir if workspace is not None else None,
                max_output_chars=config.max_observation_chars,
                workspace=workspace,
            )
            visible_skill_names = {
                str(skill.get("name") or "").strip().casefold()
                for skill in prompt_skills
                if str(skill.get("name") or "").strip()
            }
            bundled_skill_names = {
                str(skill.get("name") or "").strip().casefold()
                for skill in load_bundled_skills()
                if str(skill.get("name") or "").strip()
            }
            active_skills = [
                skill
                for skill in filter_denied_skills(
                    loaded.get("active_skills") or [],
                    config.skill_denylist,
                )
                if isinstance(skill, dict)
                and (
                    str(skill.get("name") or "").strip().casefold() not in bundled_skill_names
                    or str(skill.get("name") or "").strip().casefold() in visible_skill_names
                )
            ]
            state = AgentState(
                history=history_state.messages,
                summary=history_state.summary,
                history_version=history_state.version,
                skills=prompt_skills,
                memory=loaded["memory"],
                tasks=loaded["tasks"],
                permissions=loaded.get("permissions") or {},
                active_skills=active_skills,
                workspace=workspace,
                skill_library=skill_library,
            )
            summarizer = DifyHistorySummarizer(self.strategy.session, config.model_for("flash"))
            all_skills = prompt_skills + local_skills
            manual_compression_id = ""
            if _slash_command_name(config.query) == "compact":
                manual_compression_id = f"compression:manual:{run_id}"
                yield from writer.write_activity(
                    "cc_agent.compression",
                    _compression_activity("started", "manual", manual_compression_id),
                )
            slash_result = _dispatch_slash_command(
                config.query, state, config, all_skills,
                summarizer=summarizer, state_id=state_id, compression_id=manual_compression_id,
                skill_library=skill_library,
            )
            if slash_result is not None:
                command_payload, skill_def = slash_result
                if skill_def.get("kind") == "prompt":
                    skill_args_text = str(command_payload.get("skill_args") or "") if isinstance(command_payload, dict) else ""
                    injected = _prompt_skill_user_message(skill_def, skill_args_text, skill_runtime)
                    state.history.append(
                        {
                            "role": "user",
                            "content": injected,
                            "metadata": {"internal": True, "source": "slash_skill", "skill_name": skill_def.get("name")},
                        }
                    )
                    state.active_skills = [
                        item for item in state.active_skills if item.get("name") != skill_def.get("name")
                    ][-7:] + [{"name": str(skill_def.get("name") or ""), "summary": injected[:5000]}]
                    config.query = skill_args_text or config.query
                    slash_result = None
                else:
                    pass
            if slash_result is not None:
                command_payload, skill_def = slash_result
                result_text = command_payload if isinstance(command_payload, str) else str(command_payload.get("text") or "")
                command_events = command_payload.get("events") if isinstance(command_payload, dict) else []
                for event in command_events or []:
                    yield from _command_activity_events(writer, event)
                if result_text:
                    yield from writer.write_text_delta(result_text)
                result = AgentRunResult(
                    answer=result_text,
                    history=state.history,
                    memory=state.memory,
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
                yield from self._commit_workspace_result(
                    result,
                    workspace,
                    writer,
                    state_expected_revision=loaded.get("state_storage_revision"),
                    state_backend=env.state_backend if env is not None else None,
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
                    yield {"type": "dify_variable", "name": "agent_state", "value": result.encoded_agent_state}
                    yield {"type": "dify_json", "payload": result.to_json_payload()}
                elif result.state_ref is not None:
                    yield {"type": "dify_json", "payload": result.to_json_payload()}
                return

            external_tools = config.tools or []
            external_prompt_tools = self._init_external_prompt_tools(external_tools)
            tool_catalog = env.build_tool_catalog(
                external_tools=external_tools,
                external_prompt_tools=external_prompt_tools,
            )
            registry = tool_catalog.registry
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
                workspace=workspace,
                skill_library=skill_library,
                user_skill_scripts_enabled=config.user_skill_scripts_enabled,
                capability_mode=config.capability_mode,
                skill_denylist=config.skill_denylist,
            )
            permission_manager = PermissionManager(
                state=state,
                external_tool_names=set(tool_catalog.names_by_kind("external")),
                always_ask_tools=set(config.tool_confirmation_list or []),
            )
            if not config.user_prompt_response:
                config.user_prompt_response = _implicit_user_prompt_response(
                    config.query,
                    loaded["last_execution_metadata"],
                )
            include_user_query = True
            if config.user_prompt_response:
                logger.info(
                    "cc_agent interrupt resume requested: conversation_id=%s state_id=%s response_keys=%s last_finish_reason=%s",
                    conversation_id,
                    state_id,
                    sorted(str(key) for key in config.user_prompt_response.keys()),
                    loaded["last_execution_metadata"].get("finish_reason") if isinstance(loaded["last_execution_metadata"], dict) else None,
                )
                resume_error = _resume_interrupted_tool_result(
                    state=state,
                    config=config,
                    last_execution_metadata=loaded["last_execution_metadata"],
                    tool_adapter=tool_adapter,
                )
                if resume_error:
                    logger.warning(
                        "cc_agent interrupt resume failed: conversation_id=%s state_id=%s error=%s",
                        conversation_id,
                        state_id,
                        resume_error,
                    )
                    yield from writer.write_run_error(resume_error, code="interrupt_resume_failed")
                    return
                yield from _permission_decision_activities(writer, state.history)
                include_user_query = False

            loop = AgentLoop(
                config=config,
                state=state,
                registry=registry,
                model_adapter=model_adapter,
                tool_adapter=tool_adapter,
                summarizer=summarizer,
                include_user_query=include_user_query,
                writer=writer,
                permission_manager=permission_manager,
            )
            final_result: AgentRunResult | None = None
            for event in loop.run():
                if isinstance(event, dict):
                    yield event
            final_result = final_result or getattr(loop, "final_result", None)
            if final_result is None:
                yield from writer.write_run_error("Agent loop finished without a final result", code="missing_final_result")
                return
            yield from self._commit_workspace_result(
                final_result,
                workspace,
                writer,
                state_expected_revision=loaded.get("state_storage_revision"),
                state_backend=env.state_backend if env is not None else None,
            )
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
                yield {"type": "dify_variable", "name": "agent_state", "value": final_result.encoded_agent_state}
                yield {"type": "dify_json", "payload": final_result.to_output_payload()}
            elif final_result.state_ref is not None:
                yield {"type": "dify_json", "payload": final_result.to_output_payload()}
        except Exception as exc:
            logger.exception("cc_agent runtime run failed")
            for event in writer.write_run_error(str(exc), code="runtime_agui_error"):
                yield event
        finally:
            if skill_library is not None:
                pass
            if env is not None:
                env.close()
                workspace = None
                skill_library = None
            if workspace is not None:
                workspace.close()

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
                logging.warning("Skipping unsupported dict tool shape: keys=%s", sorted(tool.keys()))
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
        bundle = _bundle_from_result(result, revision=previous_revision)
        if config.workspace_requested:
            result.state_summary = result.state_summary or state_summary(bundle)
            result.emit_inline_state = False
            result.encoded_agent_state = ""
            result.encoded_history = ""
            if result.state_ref is None:
                result.state_ref = {
                    "state_id": state_id,
                    "conversation_id": state_id,
                    "backend": "minio",
                    "revision": previous_revision,
                    "loaded_from": loaded_from,
                    "persisted": False,
                    "storage_error": initial_storage_error,
                }
            return []

        DifyStateBackend(config, state_id=state_id).commit(result, expected_revision=previous_revision)
        state_ref = result.state_ref if isinstance(result.state_ref, dict) else {}
        state_ref["loaded_from"] = loaded_from
        state_ref["storage_error"] = _join_errors(initial_storage_error, state_ref.get("storage_error"))
        result.state_ref = state_ref
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

    def _open_workspace(
        self,
        config: AgentRunConfig,
        parameters: dict[str, Any],
        conversation_id: str,
        run_id: str,
    ) -> WorkspaceSession | None:
        if not config.workspace_requested:
            return None
        storage_config = storage_config_from_settings(config.storage)
        missing = storage_config.missing_required()
        if missing:
            raise ValueError(f"MinIO workspace config missing: {', '.join(missing)}")
        scope = WorkspaceScope(
            app_id=config.storage.scope.app_id,
            user_id=config.storage.scope.user_id,
            conversation_id=config.storage.scope.conversation_id or conversation_id or "default",
            run_id=run_id,
        )
        return WorkspaceSession(
            config=storage_config,
            scope=scope,
            dify_files=config.files or [],
        ).open()

    def _open_skill_library(
        self,
        config: AgentRunConfig,
        parameters: dict[str, Any],
        workspace: WorkspaceSession | None,
    ) -> SkillLibrarySession | None:
        if not config.workspace_requested:
            return None
        storage_config = storage_config_from_settings(config.storage)
        missing = storage_config.missing_required()
        if missing:
            logger.info("cc_agent skill library disabled because MinIO config is missing: %s", missing)
            return None
        shared_storage = getattr(workspace, "storage", None) if workspace is not None else None
        if workspace is not None and shared_storage is None:
            logger.info("cc_agent skill library disabled because workspace storage is unavailable")
            return None
        if shared_storage is not None and not hasattr(shared_storage, "list_objects"):
            logger.info("cc_agent skill library disabled because storage does not support prefix listing")
            return None
        scope = SkillScope(
            app_id=config.storage.scope.app_id,
            user_id=config.storage.scope.user_id,
        )
        return SkillLibrarySession(
            config=storage_config,
            scope=scope,
            storage=shared_storage,
            workspace=workspace,
            max_package_bytes=config.skill_package_max_bytes,
        ).open()

    def _commit_workspace_result(
        self,
        result: AgentRunResult,
        workspace: WorkspaceSession | None,
        writer: Any,
        state_expected_revision: int | None = None,
        state_backend: Any | None = None,
    ) -> list[dict[str, Any]]:
        if workspace is None:
            return []
        workspace.commit()
        scope = getattr(workspace, "scope", None)
        workspace_prefix = str(getattr(scope, "workspace_prefix", "") or "")
        workspace_conversation_id = str(getattr(scope, "conversation_id", "") or "")
        # Save complete agent state to MinIO. The legacy history object is also written
        # for older smoke tests and manual inspection, but state/current.json is the
        # authoritative MinIO state record.
        state_committed = False
        storage = getattr(workspace, "storage", None)
        if storage is None or not workspace_prefix:
            if isinstance(result.execution_metadata, dict):
                result.execution_metadata["state_commit_error"] = "workspace storage unavailable"
        else:
            try:
                if state_backend is not None:
                    state_backend.commit(result, expected_revision=state_expected_revision)
                    state_committed = True
                else:
                    saved_state = save_state_to_storage(
                        storage,
                        workspace.scope.workspace_prefix,
                        _bundle_from_result(result, revision=0),
                        expected_revision=state_expected_revision,
                    )
                    state_committed = True
                    revision = int(saved_state.get("revision") or (state_expected_revision or 0))
                    result.state_summary = saved_state.get("state_summary") or state_summary(_bundle_from_result(result, revision=revision))
                    result.state_ref = {
                        "state_id": workspace_conversation_id,
                        "conversation_id": workspace_conversation_id,
                        "storage_key": state_key(workspace_prefix) if workspace_prefix else "",
                        "backend": "minio",
                        "revision": revision,
                        "persisted": True,
                        "storage_error": None,
                        "storage_version": 1,
                    }
            except StateStoreConflict:
                raise
            except Exception as exc:
                logger.warning("cc_agent workspace state save failed: %s", exc)
                if isinstance(result.execution_metadata, dict):
                    result.execution_metadata["state_commit_error"] = str(exc)
            try:
                save_history_to_storage(
                    storage,
                    workspace.scope.workspace_prefix,
                    messages=result.history,
                    summary=result.summary or "",
                    version=result.history_schema_version,
                    expected_revision=None,
                )
            except HistoryStoreConflict:
                raise
            except Exception as exc:
                logger.warning("cc_agent workspace legacy history save failed: %s", exc)
        if not state_committed:
            revision = int(state_expected_revision or 0)
            result.state_summary = result.state_summary or state_summary(_bundle_from_result(result, revision=revision))
            result.state_ref = result.state_ref or {
                "state_id": workspace_conversation_id,
                "conversation_id": workspace_conversation_id,
                "storage_key": state_key(workspace_prefix) if workspace_prefix else "",
                "backend": "minio",
                "revision": revision,
                "persisted": False,
                "storage_error": result.execution_metadata.get("state_commit_error"),
                "storage_version": 1,
            }
        activity = workspace.activity_payload()
        files = activity.get("files") if isinstance(activity, dict) else []
        if isinstance(result.execution_metadata, dict):
            result.execution_metadata["workspace"] = {
                "files": files if isinstance(files, list) else [],
            }
        if not files:
            return []
        return writer.write_activity("cc_agent.workspace", activity)


def _upgrade_state_from_workspace(
    loaded: dict[str, Any],
    workspace: WorkspaceSession | None,
    config: AgentRunConfig,
) -> None:
    """Load complete state from MinIO workspace storage in MinIO mode."""
    if not config.workspace_requested:
        return
    if config.state_reset:
        config.use_dify_history = False
        return
    if workspace is None:
        config.use_dify_history = False
        return
    try:
        stored_state = load_state_from_storage(workspace.storage, workspace.scope.workspace_prefix)
    except Exception:
        stored_state = None
    if stored_state is not None:
        loaded["history_state"] = load_history(stored_state.history)
        loaded["memory"] = stored_state.memory
        loaded["tasks"] = stored_state.tasks
        loaded["permissions"] = stored_state.permissions
        loaded["active_skills"] = stored_state.active_skills
        loaded["last_execution_metadata"] = stored_state.last_execution_metadata
        loaded["loaded_from"] = "minio_workspace"
        loaded["state_storage_revision"] = int(stored_state.revision or 0)
        loaded["previous_revision"] = int(stored_state.revision or 0)
        config.use_dify_history = False
        return
    try:
        stored_history = load_history_from_storage(workspace.storage, workspace.scope.workspace_prefix)
    except Exception:
        stored_history = None
    if isinstance(stored_history, dict) and stored_history.get("messages"):
        loaded["history_state"] = load_history(stored_history)
        loaded["loaded_from"] = "minio_workspace_legacy_history"
        loaded["state_storage_revision"] = 0
        loaded["previous_revision"] = 0
    config.use_dify_history = False


def _upgrade_history_from_workspace(
    loaded: dict[str, Any],
    workspace: WorkspaceSession | None,
    config: AgentRunConfig,
) -> None:
    """Load history from MinIO workspace storage; fall back to Dify model history."""
    if config.state_reset:
        return
    # 1. MinIO workspace history — preferred
    if workspace is not None:
        try:
            stored = load_history_from_storage(
                workspace.storage, workspace.scope.workspace_prefix
            )
        except Exception:
            stored = None
        if isinstance(stored, dict) and stored.get("messages"):
            loaded["history_state"] = load_history(stored)
            loaded["loaded_from"] = "minio_workspace"
            loaded["history_storage_revision"] = int(stored.get("revision") or 0)
            loaded["previous_revision"] = int(stored.get("revision") or 0)
            config.use_dify_history = False
            return
    # 2. Fallback: Dify model.history_prompt_messages
    dify_messages = _extract_dify_history(config)
    if dify_messages:
        loaded["history_state"] = load_history({"messages": dify_messages, "summary": "", "version": 1})
        loaded["loaded_from"] = "dify_model"
        config.use_dify_history = True


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
    if config.workspace_requested:
        loaded_state = empty_state_load("minio_workspace").to_runtime_dict()
        loaded_state["loaded_from"] = "minio_workspace"
        loaded_state["state_storage_revision"] = 0
        config.use_dify_history = False
        return loaded_state
    return DifyStateBackend(config, state_id="").load().to_runtime_dict()


def _load_state_from_history_variable(config: AgentRunConfig) -> dict[str, Any]:
    return _load_state(config)


def _empty_loaded_state(loaded_from: str = "temporary") -> dict[str, Any]:
    return empty_state_load(loaded_from).to_runtime_dict()


def _prompt_skill_user_message(skill_def: dict[str, Any], raw_args: str, skill_runtime: SkillRuntime) -> str:
    argv = _split_args(raw_args)
    args: dict[str, Any] = {"_raw": raw_args, "_argv": argv}
    for index, value in enumerate(argv, start=1):
        args[str(index)] = value
    rendered = render_skill([skill_def], str(skill_def.get("name") or ""), args)
    return f"[Skill: {skill_def.get('name')}]\n{rendered}"


def _split_args(raw_args: str) -> list[str]:
    try:
        import shlex

        return shlex.split(raw_args)
    except Exception:
        return [part for part in str(raw_args or "").split() if part]


def _resume_interrupted_tool_result(
    state: AgentState,
    config: AgentRunConfig,
    last_execution_metadata: dict[str, Any],
    tool_adapter: ToolAdapter,
) -> str | None:
    if not isinstance(last_execution_metadata, dict) or last_execution_metadata.get("finish_reason") != "awaiting_user":
        return "No awaiting user interrupt is available to resume"
    question = last_execution_metadata.get("question")
    if not isinstance(question, dict):
        return "Awaiting user interrupt is missing question metadata"
    expected_tool_call_id = str(question.get("tool_call_id") or question.get("id") or "").strip()
    if not expected_tool_call_id:
        return "Awaiting user interrupt is missing tool_call_id"

    response = config.user_prompt_response if isinstance(config.user_prompt_response, dict) else {}
    answer = str(response.get("answer") or "").strip()
    if not answer:
        return "User prompt response answer is empty"
    prompt_id = str(response.get("promptId") or response.get("prompt_id") or "").strip()
    if prompt_id and prompt_id != expected_tool_call_id:
        return "User prompt response does not match the pending interrupt"

    matches = [
        message
        for message in state.history
        if message.get("role") == "tool" and str(message.get("tool_call_id") or "").strip() == expected_tool_call_id
    ]
    if len(matches) != 1:
        return "Could not find exactly one pending tool result for the interrupt"

    tool_message = matches[0]
    metadata = dict(tool_message.get("metadata") or {})
    pending_tool_execution = metadata.get("pending_tool_execution")
    safe_response = _safe_user_prompt_response(response)
    if isinstance(pending_tool_execution, dict):
        metadata["original_content_before_resume"] = str(tool_message.get("content") or "")
        metadata["resumed_user_prompt_response"] = safe_response
        metadata["requires_user_input"] = False
        permission_required = bool(metadata.get("permission_required"))
        if permission_required:
            decision = apply_permission_decision(state, response, metadata)
            metadata["permission_decision"] = decision
            approved = decision in {"allow_once", "allow_conversation"}
        else:
            approved = _is_confirmation_approved(response)
        metadata["confirmation_approved"] = approved
        if approved:
            executed = tool_adapter.execute(
                ToolCall(
                    id=expected_tool_call_id,
                    name=str(pending_tool_execution.get("name") or tool_message.get("name") or ""),
                    arguments=dict(pending_tool_execution.get("arguments") or {}),
                    raw_arguments=str(pending_tool_execution.get("raw_arguments") or ""),
                )
            )
            tool_message.update(executed.to_history())
            tool_metadata = dict(tool_message.get("metadata") or {})
            tool_metadata.update(metadata)
            tool_metadata.update(executed.metadata or {})
            tool_metadata["confirmation_approved"] = True
            tool_metadata["requires_user_input"] = False
            tool_message["metadata"] = tool_metadata
        else:
            metadata["confirmation_denied"] = True
            tool_message["content"] = f"Tool execution cancelled by user: {tool_message.get('name') or pending_tool_execution.get('name') or 'unknown_tool'}"
            tool_message["metadata"] = metadata
            tool_message["is_error"] = True
        config.user_prompt_response = None
        return None

    metadata["original_content_before_resume"] = str(tool_message.get("content") or "")
    metadata["resumed_user_prompt_response"] = safe_response
    metadata["requires_user_input"] = False
    tool_message["metadata"] = metadata
    tool_message["content"] = f"User answered: {answer}"
    config.user_prompt_response = None
    return None


def _implicit_user_prompt_response(query: Any, last_execution_metadata: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(last_execution_metadata, dict) or last_execution_metadata.get("finish_reason") != "awaiting_user":
        return None
    question = last_execution_metadata.get("question")
    if not isinstance(question, dict):
        return None
    tool_call_id = str(question.get("tool_call_id") or question.get("id") or "").strip()
    answer = str(query or "").strip()
    if not tool_call_id or not answer:
        return None

    purpose = str(question.get("purpose") or "").strip()
    options = question.get("options") if isinstance(question.get("options"), list) else []
    selected_value = _matching_option_value(answer, options)
    selected_label = _matching_option_label(selected_value, options)
    if not selected_value and purpose == "permission":
        selected_value = _permission_alias_value(answer)
        selected_label = selected_value

    response: dict[str, Any] = {
        "promptId": tool_call_id,
        "answer": answer,
    }
    if purpose:
        response["purpose"] = purpose
    if question.get("question") or question.get("text"):
        response["question"] = question.get("question") or question.get("text")
    if selected_value:
        response["selectedValues"] = [selected_value]
        response["selectedLabels"] = [selected_label or selected_value]
    else:
        response["customInput"] = answer
    return response


def _matching_option_value(answer: str, options: list[Any]) -> str:
    normalized_answer = _normalize_choice(answer)
    for option in options:
        if not isinstance(option, dict):
            continue
        value = str(option.get("value") or "").strip()
        label = str(option.get("label") or option.get("text") or "").strip()
        description = str(option.get("description") or "").strip()
        candidates = [value, label, description]
        if any(_normalize_choice(candidate) == normalized_answer for candidate in candidates if candidate):
            return value or label
    return ""


def _matching_option_label(value: str, options: list[Any]) -> str:
    if not value:
        return ""
    for option in options:
        if not isinstance(option, dict):
            continue
        if str(option.get("value") or "").strip() == value:
            return str(option.get("label") or value)
    return value


def _permission_alias_value(answer: str) -> str:
    normalized = _normalize_choice(answer)
    aliases = {
        "allow_conversation": {
            "allow_conversation",
            "always_allow",
            "always allow",
            "allow always",
            "allow in conversation",
            "always allow in this conversation",
            "当前会话始终允许",
        },
        "allow_once": {
            "allow_once",
            "approve",
            "allow",
            "continue",
            "confirm",
            "yes",
            "y",
            "true",
            "允许一次",
            "继续执行",
            "允许",
        },
        "deny": {
            "deny",
            "reject",
            "cancel",
            "stop",
            "no",
            "n",
            "false",
            "拒绝",
            "取消",
            "停止",
        },
    }
    for value, candidates in aliases.items():
        if normalized in {_normalize_choice(candidate) for candidate in candidates}:
            return value
    return ""


def _normalize_choice(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_user_prompt_response(response: dict[str, Any]) -> dict[str, Any]:
    allowed = {"promptId", "prompt_id", "purpose", "question", "selectedLabels", "selectedValues", "customInput", "answer", "values"}
    return {key: value for key, value in response.items() if key in allowed and value is not None}


def _is_confirmation_approved(response: dict[str, Any]) -> bool:
    values = []
    for key in ("selectedValues", "selected_values", "selectedLabels", "selected_labels"):
        raw = response.get(key)
        if isinstance(raw, list):
            values.extend(str(item).strip().lower() for item in raw if str(item).strip())
    for key in ("answer", "customInput"):
        raw = response.get(key)
        if raw:
            values.append(str(raw).strip().lower())
    approved_values = {"approve", "allow", "allow_once", "allow_conversation", "continue", "confirm", "yes", "y", "true", "继续执行", "允许"}
    denied_values = {"deny", "reject", "cancel", "stop", "no", "n", "false", "取消", "拒绝", "停止"}
    if any(value in approved_values for value in values):
        return True
    if any(value in denied_values for value in values):
        return False
    return False


def _prompt_tool_from_selector(selector: Any) -> Any | None:
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    for name, parameter in (_get(selector, "tool_parameters") or {}).items():
        parameter_type = _enum_value(_get(parameter, "type")) or "string"
        parameters["properties"][name] = {
            "type": parameter_type,
            "description": str(_get(parameter, "description") or ""),
        }
        options = _get(parameter, "options")
        if options:
            parameters["properties"][name]["enum"] = [_enum_value(_get(option, "value")) for option in options]
        if bool(_get(parameter, "required")):
            parameters["required"].append(name)
    payload = {
        "name": str(_get(selector, "tool_name") or _get(selector, "name") or ""),
        "description": str(_get(selector, "tool_description") or _get(selector, "description") or ""),
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
                **{key: value for key, value in parameters.items() if key not in {"type", "properties", "required"}},
            },
        }
    )


def _prompt_tool_from_entity_dict(tool: dict[str, Any]) -> Any | None:
    identity = tool.get("identity") if isinstance(tool.get("identity"), dict) else {}
    name = str(identity.get("name") or tool.get("tool_name") or tool.get("name") or "")
    if not name:
        return None
    description = tool.get("description") or {}
    if isinstance(description, dict):
        description_text = str(description.get("llm") or description.get("text") or description.get("description") or "")
    else:
        description_text = str(description or "")
    if not description_text:
        description_text = str(tool.get("tool_description") or "")
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
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
    return _make_prompt_tool({"name": name, "description": description_text, "parameters": parameters})


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
        if parameter_type in {"select", "secret-input", "secret_input", "dynamic-select", "dynamic_select"}:
            parameter_type = "string"
        schema = {
            "type": parameter_type,
            "description": str(_get(parameter, "llm_description") or _get(parameter, "description") or ""),
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


def _bundle_from_result(result: AgentRunResult, revision: int = 0) -> AgentStateBundle:
    return bundle_from_parts(
        revision=revision,
        history={
            "messages": result.history,
            "summary": result.summary or "",
            "version": result.history_schema_version,
        },
        memory=result.memory,
        tasks=result.tasks,
        permissions=result.permissions,
        active_skills=result.active_skills,
        last_execution_metadata=result.execution_metadata,
    )


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
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
    return str(parameters.get("conversation_id") or inputs.get("conversation_id") or "").strip()


def _run_id_from_parameters(parameters: dict[str, Any]) -> str:
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
    return str(parameters.get("run_id") or inputs.get("run_id") or f"run_{uuid4().hex}")


def _app_id_from_parameters(parameters: dict[str, Any], strategy: Any) -> str:
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
    session = _get(strategy, "session")
    candidates = [
        parameters.get("app_id"),
        inputs.get("app_id"),
        _get(session, "app_id"),
        _get(_get(strategy, "runtime"), "app_id"),
    ]
    return _first_non_empty(candidates) or "default"


def _user_id_from_parameters(parameters: dict[str, Any], strategy: Any) -> str:
    inputs = parameters.get("inputs") if isinstance(parameters.get("inputs"), dict) else {}
    session = _get(strategy, "session")
    candidates = [
        parameters.get("user"),
        parameters.get("user_id"),
        inputs.get("user"),
        inputs.get("user_id"),
        _get(session, "user_id"),
        _get(session, "user"),
        _get(_get(strategy, "runtime"), "user_id"),
    ]
    return _first_non_empty(candidates) or "default"


def _first_non_empty(values: list[Any]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _make_writer(output_protocol: str, thread_id: str, run_id: str, show_tool_calls: bool = True) -> Any:
    return ProtocolRenderer(
        output_protocol,
        thread_id=thread_id,
        run_id=run_id,
        show_tool_calls=show_tool_calls,
    )


def _command_activity_events(writer: Any, event: Any) -> list[dict[str, Any]]:
    if isinstance(event, dict):
        activity_type = event.get("activity_type")
        activity = event.get("activity")
        if activity_type and isinstance(activity, dict):
            return writer.write_activity(str(activity_type), activity)
        if event.get("type") == "activity" and event.get("activityType"):
            return writer.write_activity(str(event.get("activityType")), event.get("content") if isinstance(event.get("content"), dict) else {})
        return [event]
    operations = getattr(event, "operations", None)
    if operations is not None:
        return writer.write_activity("a2ui-surface", {"a2ui_operations": operations})
    return []


def _permission_decision_activities(writer: Any, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for message in history:
        if message.get("role") != "tool":
            continue
        metadata = message.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("permission_decision_activity_emitted"):
            continue
        decision = metadata.get("permission_decision")
        if decision not in {"allow_once", "allow_conversation", "deny"}:
            continue
        request = metadata.get("permission_request") if isinstance(metadata.get("permission_request"), dict) else {}
        script_key = str(request.get("skill_script_key") or "")
        skill_name, script_name = _split_script_key(script_key)
        events.extend(
            writer.write_activity(
                "cc_agent.permission_decision",
                _drop_none(
                    {
                        "toolName": request.get("tool_name") or message.get("name"),
                        "skillName": skill_name,
                        "scriptName": script_name,
                        "decision": decision,
                        "scope": "conversation" if decision == "allow_conversation" else "once",
                    }
                ),
            )
        )
        metadata["permission_decision_activity_emitted"] = True
        message["metadata"] = metadata
    return events


def _split_script_key(value: str) -> tuple[str, str]:
    if "/" not in value:
        return "", ""
    skill_name, script_name = value.split("/", 1)
    return skill_name, script_name


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _compression_activity(
    status: str,
    trigger: str,
    compression_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload.update(
        {
            "status": status,
            "trigger": trigger,
            "compressionId": compression_id,
            "messageId": compression_id,
        }
    )
    return payload
