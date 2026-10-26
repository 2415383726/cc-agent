from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AgentRunConfig, StorageSettings
from .profiles import RuntimeProfile
from .protocol_renderer import ProtocolRenderer
from .skill_catalog import SkillCatalog, build_skill_catalog
from .skill_library import SkillScope
from .state_backend import DifyStateBackend, MinioStateBackend, StateBackend, StateLoad
from .tool_catalog import ToolCatalog
from .workspace import StorageConfig, WorkspaceScope


@dataclass(slots=True)
class RunEnvironment:
    config: AgentRunConfig
    profile: RuntimeProfile
    parameters: dict[str, Any]
    strategy: Any
    thread_id: str
    run_id: str
    state_id: str
    renderer: ProtocolRenderer
    workspace: Any | None = None
    skill_library: Any | None = None
    skill_catalog: SkillCatalog | None = None
    state_backend: StateBackend | None = None
    loaded_state: StateLoad | None = None
    tool_catalog: ToolCatalog | None = None

    @classmethod
    def open(
        cls,
        *,
        config: AgentRunConfig,
        parameters: dict[str, Any],
        strategy: Any,
        thread_id: str,
        run_id: str,
        state_id: str,
        renderer: ProtocolRenderer | None = None,
        workspace_session_cls: Any,
        skill_library_cls: Any,
    ) -> "RunEnvironment":
        renderer = renderer or ProtocolRenderer(
            config.output_protocol,
            thread_id=thread_id,
            run_id=run_id,
            show_tool_calls=config.show_tool_calls,
        )
        env = cls(
            config=config,
            profile=config.profile,
            parameters=parameters,
            strategy=strategy,
            thread_id=thread_id,
            run_id=run_id,
            state_id=state_id,
            renderer=renderer,
        )
        if config.workspace_requested:
            storage_config = storage_config_from_settings(config.storage)
            missing = config.storage.missing_required() or storage_config.missing_required()
            if missing:
                raise ValueError(f"MinIO workspace config missing: {', '.join(missing)}")
            scope = WorkspaceScope(
                app_id=config.storage.scope.app_id,
                user_id=config.storage.scope.user_id,
                conversation_id=config.storage.scope.conversation_id,
                run_id=run_id,
            )
            env.workspace = workspace_session_cls(
                config=storage_config,
                scope=scope,
                dify_files=config.files or [],
            ).open()
            env.skill_library = env._open_skill_library(skill_library_cls, storage_config)
            env.state_backend = MinioStateBackend(env.workspace, state_id=scope.conversation_id)
            config.use_dify_history = False
        else:
            env.state_backend = DifyStateBackend(config, state_id=state_id)
        env.skill_catalog = build_skill_catalog(config=config, skill_library=env.skill_library)
        return env

    def load_state(self) -> dict[str, Any]:
        assert self.state_backend is not None
        self.loaded_state = self.state_backend.load()
        if self.config.workspace_requested:
            self.config.use_dify_history = False
        return self.loaded_state.to_runtime_dict()

    def build_tool_catalog(self, *, external_tools: list[Any], external_prompt_tools: list[Any]) -> ToolCatalog:
        self.tool_catalog = ToolCatalog.create(
            capability_mode=self.config.capability_mode,
            external_tools=external_tools,
            external_prompt_tools=external_prompt_tools,
            output_protocol=self.config.output_protocol,
        )
        return self.tool_catalog

    def close(self) -> None:
        if self.skill_catalog is not None:
            self.skill_catalog.close()
        elif self.skill_library is not None:
            self.skill_library.close()
        if self.workspace is not None:
            self.workspace.close()

    def _open_skill_library(self, skill_library_cls: Any, storage_config: StorageConfig) -> Any | None:
        shared_storage = getattr(self.workspace, "storage", None) if self.workspace is not None else None
        if self.workspace is not None and shared_storage is None:
            return None
        if shared_storage is not None and not hasattr(shared_storage, "list_objects"):
            return None
        return skill_library_cls(
            config=storage_config,
            scope=SkillScope(
                app_id=self.config.storage.scope.app_id,
                user_id=self.config.storage.scope.user_id,
            ),
            storage=shared_storage,
            workspace=self.workspace,
            max_package_bytes=self.config.skill_package_max_bytes,
        ).open()


def storage_config_from_settings(settings: StorageSettings) -> StorageConfig:
    return StorageConfig(
        enabled=True,
        endpoint=settings.endpoint,
        bucket=settings.bucket,
        access_key=settings.access_key,
        secret_key=settings.secret_key,
        secure=settings.secure,
        public_download_base_url=settings.public_download_base_url,
        presign_expiry_seconds=settings.presign_expiry_seconds,
        ttl_days=settings.ttl_days,
    )
