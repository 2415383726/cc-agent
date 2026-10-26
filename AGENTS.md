# AGENTS.md

This file provides guidance to Codex when working with code in this repository.

## Project overview

Three sub-projects live here:

- **`cc_agent/`** — A Dify plugin (Python ≥3.12) implementing the CC Agent strategy. Dual capability modes: `dify_only` (Dify-native state, no external storage) and `minio` (MinIO-backed state, workspace, code execution, skill packages). Internal cognitive tools (Skill, Memory, Task, AskUserQuestion) and Dify-injected external tools.
- **`copilotkit-dify/`** — A Vue 3 + Vite frontend chat UI using CopilotKit and `@ag-ui/client`. Consumes Dify SSE/AG-UI protocol output. Renders tool call lifecycle cards, skill/guard/compression/workspace activity blocks, thinking blocks, and permission interrupts.
- **`cc-haha/`** and **`cheetahclaws/`** — Reference implementations (read-only).

## Build & development

### Python (cc_agent)

```powershell
# Run all tests
python -B -m unittest discover cc_agent\tests

# Run a single test file
python -B -m unittest cc_agent.tests.test_core_core

# Run a single test case
python -B -m unittest cc_agent.tests.test_core_core.HistoryTests.test_history_round_trips_and_removes_orphan_tool_messages

# Format (from cc_agent/ directory, uses uv)
uv run black . -C -l 100
uv run ruff check --fix

# Build offline Dify plugin package
python cc_agent/scripts/build_offline_package.py
```

### Frontend (copilotkit-dify)

```bash
cd copilotkit-dify
npm install
npm run dev        # dev server
npm run build      # production build
npm run preview    # preview production build
npm run test       # run vitest tests
```

## Architecture

### Agent execution flow

```
CCAgentStrategy._invoke(parameters)
  -> AgentRunConfig.from_parameters() → capability_mode, storage JSON, agent_state
  -> RunEnvironment.open() → StateBackend, WorkspaceSession, SkillCatalog, ProtocolRenderer
  -> ToolCatalog.create(capability_mode) → profile-filtered tool schemas
  -> StateBackend.load() → AgentState from Dify variable or MinIO state/current.json
  -> AgentLoop.run()
       -> ContextBudget.prepare() — trim old observations, enforce message limits
       -> PromptBuilder — system prompt + instruction + skills + memory + tasks + history
       -> DifyModelAdapter.invoke() — Dify LLM call with streaming tool-call accumulation
       -> if tool_calls: SerialToolScheduler → ToolGuard → PermissionManager → ToolAdapter
       -> loop until final answer or max_iterations
  -> StateBackend.commit() → persist agent_state (Dify) or state/current.json (MinIO)
  -> ProtocolRenderer → AG-UI or Dify native events
```

### Capability modes

| Mode | State | Workspace | Scripts | Skill management |
|---|---|---|---|---|
| `dify_only` | Encoded `agent_state` in Dify variable | No | No | Bundled + `app_skills_yaml` only |
| `minio` | MinIO `state/current.json` (ignores input `agent_state`) | Yes (MinIO content-addressed) | `run_python`, `SkillRunScript` | Bundled + MinIO 3-layer + `app_skills_yaml` |

Mode is set via `capability_mode` parameter. MinIO config is a single `storage` JSON string parameter with provider, endpoint, bucket, credentials, and `scope.app_id/user_id/conversation_id`.

### Key module roles

#### Core loop

| Module | Role |
|---|---|
| `runtime.py` | Entry point: parses config, opens RunEnvironment, orchestrates loop, commits state |
| `loop.py` | Heart of the agent: model↔tool iteration, finish reasons, context overflow recovery |
| `model_adapter.py` | Dify LLM wrapper: dict↔PromptMessage conversion, streaming accumulator |
| `prompt_builder.py` | Assembles system prompt with instruction/skills/memory/tasks/workspace context |
| `context_budget.py` | Pre-invoke context trimming (observation snip, token estimation, message limit) |
| `compression.py` | LLM-based history summarization with fallback to rule-based |
| `tool_adapter.py` | Executes one tool (internal or Dify external), normalizes result to observation/display/metadata |
| `tool_scheduler.py` | Serial tool execution (V1.5); interface preserved for future concurrency |
| `guards.py` | Tool allowlist/denylist, repeated-call limit, consecutive error limit |
| `result_budget.py` | Truncates large tool observations |
| `messages.py` | Internal data types: ToolCall, AssistantTurn, ToolResult, AgentState, AgentRunResult |
| `history.py` | JSON history load/dump/sanitize (orphan removal, format migration) |
| `config.py` | AgentRunConfig + StorageSettings: capability mode, storage JSON parsing, model features |

#### Architectural ports

| Port | Module | Role |
|---|---|---|
| `StateBackend` | `state_backend.py` | Protocol with `DifyStateBackend` (encoded agent_state) and `MinioStateBackend` (MinIO state/current.json) |
| `ToolCatalog` | `tool_catalog.py` | Profile-filtered tool registration: `dify_only` exposes 14 base tools, `minio` adds 9 advanced tools |
| `SkillCatalog` | `skill_catalog.py` | Merges bundled + app_yaml + MinIO skills by priority; `MinioSkillCatalog` adds install/remove |
| `ProtocolRenderer` | `protocol_renderer.py` | Renders immutable `AgentEvent` objects through AG-UI or Dify native writer |
| `RunEnvironment` | `run_environment.py` | Orchestrates service assembly per run: open workspace → load state → build catalogs → loop → commit → close |

#### Workspace subsystem (`core/workspace/`)

MinIO-backed file storage. Files are content-addressed by SHA256 under `objects/sha256/xx/<digest>`.

| Module | Role |
|---|---|
| `storage_client.py` | MinIO client: get/put JSON, upload/download files, presigned GET URLs |
| `manifest.py` | `WorkspaceFile` and `WorkspaceManifest` — file metadata with versioned manifest |
| `session.py` | `WorkspaceSession` — open/commit/close lifecycle, Dify file import, CRUD, materialize |
| `lock.py` | `WorkspaceLock` — distributed lock via MinIO JSON lease |
| `state_store.py` | Persist/load `AgentStateBundle` to/from MinIO |
| `history_store.py` | Legacy history persistence to MinIO |
| `materializer.py` | Text/binary detection, JSON/CSV inspection, text reading with truncation |
| `execution_runtime.py` | Subprocess execution (Python, bash, PowerShell, Node) with timeout and artifact collection |

#### Agent output

| Module | Role |
|---|---|
| `agui_stream.py` | `AgUiStreamWriter` — AG-UI protocol events for copilotkit-dify frontend |
| `dify_stream_writer.py` | `DifyNativeWriter` — Dify-native log/text/json/blob messages |
| `model_stream.py` | Streaming data types: `TextDelta`, `ThinkingDelta`, `AssistantTurnCompleted` |

#### Skills system

| Module | Role |
|---|---|
| `builtin_skills.py` | Built-in local skills (slash commands): /help, /status, /context, /cost, /compact |
| `skill_registry.py` | Loads skills from `skills/*/SKILL.md` files with frontmatter parsing |
| `skill_runtime.py` | Executes skill scripts (Python, Node, bash, PowerShell) with artifact collection |
| `skill_library.py` | Skill package management with MinIO storage, layered scoping (agent/app/user) |
| `app_skills.py` | Parse and validate YAML-defined app-level skills |
| `skills.py` | In-memory skill loading from JSON with metadata |

#### State persistence

| Module | Role |
|---|---|
| `state_variable.py` | `AgentStateBundle`, gzip+base64 codec (`ccagent-state:v1:gzip-base64:`), `state_summary()` |
| `permissions.py` | `PermissionManager` — tool allowlist scoped to conversation |
| `python_runtime.py` | Thin wrapper delegating Python execution to `WorkspaceExecutionRuntime` |

### State contract

- **`agent_state`** — `ccagent-state:v1:gzip-base64:<data>` encoded blob containing `AgentStateBundle` (history, memory, tasks, permissions, active_skills, last_execution_metadata)
- **`state_summary`** — read-only subset: history_count, memory_count, task_count, awaiting_user, last_finish_reason
- **`storage`** — JSON string with MinIO provider, endpoint, bucket, credentials, and `scope.app_id/user_id/conversation_id`

MinIO mode final outputs `state_ref` (pointer to MinIO) + `state_summary`. Dify-only mode outputs `agent_state` (encoded) + `state_summary`.

### Error handling

- **Context overflow**: reactive compact then retry once; fails → `finish_reason=context_overflow`
- **Tool errors**: synthetic observation generated, maintains tool-call/tool-result pairing invariant
- **MinIO config failure**: `run_error` on startup, no fallback to dify_only
- **Workspace lock conflict**: `finish_reason=workspace_locked`
- **Runtime MinIO unreachable**: synthetic tool error, loop continues
- **Commit failure**: `state_commit_failed` or `workspace_commit_failed`
- Strategy-level unhandled exceptions emit `agent_failed` JSON (not raw tracebacks)

## Test file conventions

Core tests:
- `test_core_core.py` — history, config, streaming accumulator, tool registry, serial scheduler, context budget, result budget, guards
- `test_core_enhancements.py` — prompt builder, compression, error classifier, events, Dify memory injection, AskUserQuestion, context overflow
- `test_core_commands.py` — built-in slash commands
- `test_core_builtin_skills.py` — built-in skills behavior
- `test_core_skill_registry.py` — SKILL.md loading and parsing
- `test_core_skill_library.py` — skill package management
- `test_core_app_skills.py` — YAML app skill parsing
- `test_core_strategy_contract.py` — strategy-level contract tests

Architecture ports:
- `test_core_architecture_ports.py` — StateBackend, ToolCatalog, SkillCatalog, ProtocolRenderer

Workspace & execution:
- `test_core_workspace.py` — MinIO workspace session, file CRUD, manifest, lock
- `test_core_execution_runtime.py` — subprocess execution (Python/bash), artifact collection
- `test_core_permissions.py` — tool permission allow/deny decisions

Streaming & AG-UI:
- `test_agui_stream.py` — AG-UI stream writer event production
- `test_agui_translator.py` — AG-UI translator event mapping
- `test_stream_protocol_switch.py` — streaming protocol selection, Dify native rendering
- `test_core_agui_runtime.py` — AG-UI runtime integration
- `test_state_variable.py` — gzip+base64 state encoding/decoding with compaction

Tests use `unittest` with `SimpleNamespace` for mock Dify SDK objects. Do not import `dify_plugin` in tests — use fake objects instead.

## Important constraints

- Do **not** add local file I/O, shell, web search, or browser tools to internal tools — these must be Dify-injected.
- Every assistant `tool_calls` entry must have a corresponding `tool` result message before the next model call. `sanitize_history()` enforces this on load.
- The plugin targets `minimum_dify_version: 1.7.0`.
- Frontend tool renderers in copilotkit-dify are registered in `src/components/tool-cards/`; unrecognized tools fall back to `DefaultToolCallCard.vue`.
- Workspace storage (MinIO) is optional — set `capability_mode=minio` and provide valid `storage` JSON.
- History state variable encoding uses `ccagent-state:v1:gzip-base64:` prefix. It auto-compacts to fit within Dify conversation variable size limits (~190KB max).
- Secrets (access_key, secret_key) must never appear in prompt, logs, tool metadata, or final JSON output.
