# AGENTS.md

## Project

- `cc_agent/`: Dify Agent Strategy plugin, Python ≥3.12. Conversation state uses the Dify `agent_state` variable. Internal tools handle skills, memory, tasks, and AG-UI user prompts; Dify injects external tools.
- `copilotkit-dify/`: Vue 3 + Vite frontend consuming AG-UI / Dify streams, with tool cards, structured answers, attachments, and permission interrupts.
- `cc-haha/` and `cheetahclaws/`, when present, are read-only reference implementations.

For configuration and the full state flow, read [README.md](README.md). For domain terms and architectural decisions, read [CONTEXT.md](CONTEXT.md) and [docs/adr/](docs/adr/).

## Development

From the repository root:

```bash
python -B -m unittest discover -s cc_agent/tests
python -B -m unittest cc_agent.tests.test_core
python cc_agent/scripts/build_offline_package.py
```

From `cc_agent/`, formatting uses `uv run black . -C -l 100` and `uv run ruff check --fix`.

From `copilotkit-dify/`, use `npm install`, `npm run dev`, `npm run test`, and `npm run build`.

## Runtime boundaries

- Both strategy entries share `core/runtime.py` and `RunEnvironment`: `CC Agent (AG-UI)` emits AG-UI events; `CC Agent (Dify)` emits Dify-native messages. Preserve their separate prompt and tool surfaces.
- `DifyStateBackend` loads and commits encoded `agent_state`; `state_ref` includes Dify conversation metadata and is used by the frontend. `state_summary` is read-only.
- `SkillCatalog` combines bundled and application YAML skills. `SkillRuntime` only reads text resources belonging to a skill; preserve its path checks.
- `ToolCatalog` / `ToolRegistry` register internal, Dify-injected, and configured remote MCP tools. MCP connections and headers belong to one run; see [ADR-0002](docs/adr/0002-runtime-mcp-tools.md). `InternalToolExecutor` owns cognitive tools only.
- File access, code execution, web search, and browsing come from Dify-injected tools or configured remote MCP services. Do not add general local I/O, shell, or stdio MCP execution to the internal tool set.
- `files` supplies safe attachment metadata to the prompt; it does not grant file-content access. Preserve external tool blob/file/image/link output.
- MinIO mode, workspaces, internal script execution, and remote skill management have been removed. There is no mode switch, storage configuration, or compatibility backend to maintain. See [ADR-0001](docs/adr/0001-dify-owned-state.md).

## Invariants

- Every assistant `tool_calls` entry needs a corresponding tool result before the next model call. `sanitize_history()` enforces pairing on load; tool failures still need synthetic results.
- State uses `ccagent-state:v1:gzip-base64:` and auto-compacts to fit Dify conversation variables (about 190KB).
- Preserve context-overflow recovery: compact and retry once, then finish with `context_overflow`.
- Unhandled strategy errors emit `agent_failed` JSON rather than raw tracebacks.
- Configuration secrets must never enter prompts, logs, tool metadata, or final outputs.
- Target Dify compatibility is at least 1.7.0; do not lower it as part of unrelated changes.

## Tests

Tests use `unittest` and `SimpleNamespace` for fake Dify objects. Prefer fakes over importing `dify_plugin` for new core tests; existing strategy contract tests import the real adapter and require the SDK.

- `test_core.py`: history, config, model streaming, tool registry, scheduling, context/result budgets, guards.
- `test_core_enhancements.py`: prompts, compression, tool descriptions, user input, overflow recovery.
- `test_core_architecture_ports.py`: Dify state, tool/skill catalogs, protocol renderer, removed tool boundaries.
- `test_core_strategy_contract.py`: strategy schemas, configuration and log summaries.
- `test_core_agui_runtime.py`, `test_agui_stream.py`, `test_stream_protocol_switch.py`: runtime and protocol contracts.
- `test_state_variable.py`: state codec and compaction.
- Skill, command, permission and app YAML tests live beside these in `cc_agent/tests/`.

For frontend changes, preserve tool-card fallback rendering, attachment handling and conversation-ID recovery in `src/cc-assistant/`. Generic file renderers can also serve Dify-injected tools.
