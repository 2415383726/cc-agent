# AGENTS.md

## Project

- `cc_agent/`: Dify Agent Strategy plugin, Python ≥3.12. Conversation state uses the Dify `agent_state` variable. Internal tools handle skills, tasks, and AG-UI user prompts; Dify injects external tools.
- `copilotkit-dify/`: Vue 3 + Vite frontend consuming AG-UI / Dify streams, with tool cards, structured answers, attachments, and permission interrupts.
- `pi_dify/`: independent v2 Pi Harness Dify Agent Strategy plugin (Python 3.12). Pins `pi-agent-core-lc`/`pi-agent-harness-lc` 0.6.0 and uses `piagent-state:v1:gzip-base64:`; it does not import old `cc_agent` state or loops.
- `pi_workbench/`: static Vue 3 workbench for the `piagent.display.v1` contract, extracted from the pinned Leyline commit. No Node/Pi runtime backend.
- `cc-haha/` and `cheetahclaws/`, when present, are read-only reference implementations.

For configuration and the full state flow, read [README.md](README.md). For domain terms and architectural decisions, read [CONTEXT.md](CONTEXT.md) and [docs/adr/](docs/adr/).

## Development

From the repository root:

```bash
python -B -m unittest discover -s cc_agent/tests
python -B -m unittest cc_agent.tests.test_core
python cc_agent/scripts/build_offline_package.py
python -B -m unittest discover -s pi_dify/tests
python pi_dify/scripts/build_offline_package.py --arch amd64
```

From `pi_workbench/`, use `npm install`, `npm run dev`, `npm run test`, `npm run build`, and `npm run check:static`.

From `cc_agent/`, formatting uses `uv run black . -C -l 100` and `uv run ruff check --fix`.

From `copilotkit-dify/`, use `npm install`, `npm run dev`, `npm run test`, and `npm run build`.

## Runtime boundaries

- Both strategy entries share `core/runtime.py` and `RunEnvironment`: `CC Agent (AG-UI)` emits AG-UI events; `CC Agent (Dify)` emits Dify-native messages. Preserve their separate prompt and tool surfaces.
- `DifyStateBackend` loads and commits encoded `agent_state`; `state_ref` includes Dify conversation metadata and is used by the frontend. `state_summary` is read-only.
- `ModelRequests` owns request preparation, context budgets and the single overflow retry for normal, continuation and final turns.
- `UserInterrupts` owns confirmation and resume; approval never bypasses scheduler policy checks. Existing v1 pending interrupts remain resumable.
- `SkillCatalog` selects bundled/application skills, restores visible active skills and activates slash/model requests. `SkillRuntime` only reads text resources belonging to a skill; preserve its path checks.
- `ToolCatalog` registers internal, Dify-injected, and configured remote MCP tools. MCP connections and headers belong to one run; see [ADR-0002](docs/adr/0002-runtime-mcp-tools.md). `InternalToolExecutor` owns cognitive tools only.
- File access, code execution, web search, and browsing come from Dify-injected tools or configured remote MCP services. Do not add general local I/O, shell, or stdio MCP execution to the internal tool set.
- `files` supplies safe attachment metadata to the prompt; it does not grant file-content access. Preserve Dify tool repeated-halves and semantic JSON deduplication. Do not add a second forwarding path for Dify tool artifacts. Forward direct MCP blobs after ordinary and resumed execution.
- MinIO mode, workspaces, internal script execution, and remote skill management have been removed. There is no mode switch, storage configuration, or compatibility backend to maintain. See [ADR-0001](docs/adr/0001-dify-owned-state.md).

- Memory tools and the two demo commands were removed; retain Tasks. Ignore old `memory` state and omit it on save. See [ADR-0003](docs/adr/0003-agent-feature-scope.md).
- Frontend `runStream.ts` owns native/fallback interpretation; `conversationCoordinator.ts` owns thread mapping, history tickets and stale-result rules. Keep SDK binding in the shell thin.

- `pi_dify/pi_agent/harness.py` is the only AgentHarness 0.6.0 adapter subclass; it adds only the stop predicate and resume turn seams. Do not copy the Pi loop, patch dependency source, or add a second model/tool scheduler.
- `pi_dify/pi_agent/stream.py` is the only Dify model boundary for Pi. Complete arguments only; `tool_stream_mode` is explicit; keep the one-overflow-compaction retry and never replay completed tools.
- `pi_dify/pi_agent/state.py` is the only Pi cross-turn authority. Keep the size-limited codec, pending/leaf/tool pairing on trim, and state-before-terminal ordering. `state_ref` must not claim platform persistence.
- AskUser and approval are distinct pending interactions in `pi_agent/interaction.py`; both stop the batch deterministically and resume from a validated next-turn `interaction`. A questionnaire answer is not a tool authorization.
- `pi_workbench/src/dify/controller.ts` owns Dify send/stop/history/stale-result rules; `src/projection/transcript.ts` owns display reduction. Replay must use the same contract and components, not a second renderer.

## Invariants

- Every assistant `tool_calls` entry needs a corresponding tool result before the next model call. `sanitize_history()` enforces pairing on load; tool failures still need synthetic results.
- State uses `ccagent-state:v1:gzip-base64:` and auto-compacts to fit Dify conversation variables (about 190KB).
- Preserve context-overflow recovery: compact and retry once, then finish with `context_overflow`.
- Unhandled strategy errors emit `agent_failed` JSON rather than raw tracebacks.
- Configuration secrets must never enter prompts, logs, tool metadata, or final outputs.
- Target Dify compatibility is at least 1.7.0; do not lower it as part of unrelated changes.

## Tests

Tests use `unittest` and `SimpleNamespace` for fake Dify objects. Prefer fakes over importing `dify_plugin` for new core tests; existing strategy contract tests import the real adapter and require the SDK.

- `test_core.py`: history, config, model streaming, tool catalog, scheduling, context/result budgets, guards.
- `test_core_enhancements.py`: prompts, compression, tool descriptions, user input, overflow recovery.
- `test_core_architecture_ports.py`: Dify state, tool/skill catalogs, protocol renderer, removed tool boundaries.
- `test_core_strategy_contract.py`: strategy schemas, configuration and log summaries.
- `test_core_agui_runtime.py`, `test_agui_stream.py`, `test_stream_protocol_switch.py`: runtime and protocol contracts.
- `test_state_variable.py`: state codec and compaction.
- `test_architecture_lifecycle.py`: pruning, saved snapshot summaries, policy-aware resume, request recovery and skill lifecycle.
- Skill, command, permission and app YAML tests live beside these in `cc_agent/tests/`.
- `pi_dify/tests/test_runtime.py`: Pi text/tool/AskUser/approval/budget/overflow flows with fakes.
- `pi_dify/tests/test_state.py`, `test_stream.py`, `test_skills*.py`, `test_interaction.py`, `test_mcp.py`, `test_strategy.py`: codec/trimming, stream modes, skills, interactions, MCP lifecycle and manifest contracts.
- `pi_workbench/tests/`: contract validation, projection/merge, history, controller stale/stop rules, forms and static replay.

For frontend changes, preserve tool-card fallback rendering, attachment handling and conversation-ID recovery in `src/cc-assistant/`. Generic file renderers can also serve Dify-injected tools.
