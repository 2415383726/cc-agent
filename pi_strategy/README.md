# Pi Strategy for Dify (native output)

`pi_strategy` is an independent Dify Agent Strategy plugin forked from
`pi_dify`. It keeps the same pinned runtime — `pi-agent-core-lc==0.6.0` and
`pi-agent-harness-lc==0.6.0` — and the same hard boundaries (single Dify model
boundary, single cross-turn state authority, single harness adapter, single
overflow-compaction retry), but replaces the `piagent.display.v1` contract
with **Dify-native output**: the built-in Dify chat UI is the only consumer and
no custom frontend exists.

UX parity target is the retired `CC Agent (Dify)` mode of `cc_agent/`:
reasoning streams wrapped in `<think>` tags, tool results render as HTML tool
cards (params + result, clipped), host activities and terminal facts go to
`<details>` logs, artifacts to blob messages, state to the `agent_state`
variable, and one final JSON payload carries the terminal run state. The two
engines can swap inside one Dify application without the user noticing.

Split rationale and boundaries: [ADR-0011](../docs/adr/0011-pi-strategy-native-split.md).
The sibling `pi_dify/` (display contract + pi_chat workbench) and the frozen
`cc_agent/` stay independent; no code or state is shared between them.

## Architecture

```
Dify AgentStrategy
  └─ PiStrategyRuntime (one worker thread + one event loop per request)
       ├─ PiHarness (pinned 0.6.0) + Pi core loop
       ├─ DifyModelStream  → current Dify model only
       ├─ ToolRuntime      → Dify tools, remote MCP, internal skill tools
       ├─ SessionIO        → blocking Dify calls on real OS threads, abortable
       ├─ RunLedger        → one budget for models, tools, retries, summaries
       ├─ pistrategy-state:v1:gzip-base64: (Dify agent_state)
       └─ NativeEvents + NativeObserver → text / tool cards / logs / blob / state / JSON
```

`pi_strategy/harness.py` is the only adapter subclass (stop predicate + resume
seam only). `stream.py` is the only Dify model boundary; `state.py` is the only
cross-turn authority; `native.py` owns the message kinds, redaction, clipping
and terminal payloads; `observer.py` renders Pi harness events into them.

## Differences from pi_dify

- **No display contract**: `contract.py`/`observer.py` of pi_dify are replaced
  by `native.py` + a rewritten `observer.py`. There is no `data.piagent` log
  envelope, no event sequence envelope, and no workbench to rebuild events.
- **No approval interaction**: tools execute immediately when the model calls
  them. There is no pending approval, no `interaction` parameter, no keyword
  reply, no session grants and no consumption bookkeeping. The removed
  `approval_mode`/`approval_tools`/`approval_timeout_seconds` keys are ignored
  and there is no `ask_user` questionnaire tool.
- **New state prefix**: `pistrategy-state:v1:gzip-base64:`. Foreign prefixes
  (`ccagent-state`, `piagent-state`) are rejected by the codec and by tests.
  Old conversations cannot be migrated across engines.
- **No Tasks tool and no `visualize` card tool**: the remaining feature set
  mirrors pi_dify minus those; porting cc_agent's Tasks is a deliberate future
  enhancement, not part of the split.
- **Finalize shape** (cc_agent parity): state variable → feedback text (only
  for non-completed outcomes; completed answers were already streamed) →
  "Run finished"/"Run error" log → "Final answer" log + `answer` variable →
  one JSON terminal payload.

## Dify node mapping

The application node must explicitly map these parameters:

| Parameter | Purpose |
| --- | --- |
| `model` | Current Dify model (model-selector). Required. |
| `query` | Current user text. |
| `tools` | Dify-injected tools available for this run. |
| `files` | Attachment metadata JSON (metadata only, not file content). |
| `instruction` | Application instruction. |
| `app_skills_yaml` | Application skill definitions/resources. |
| `mcp_servers_config` | Remote MCP servers (already-resolved headers). |
| `runtime_config` | Budgets, stream mode, compaction, timeouts. |
| `agent_state` | Dify conversation variable; the only cross-turn authority. |
| `conversation_id`, `user_id`, `app_id` | Session identity and isolation. |

There is no `interaction` parameter; do not map one.

## State

`agent_state` uses `pistrategy-state:v1:gzip-base64:`. The bundle contains the
Pi session entries/leaf, active skills and run statistics. Decode and
decompress are size-limited; unknown prefixes/versions, dangling parents,
cycles and unpaired tool calls are rejected. The approximate 190KB encoded
boundary is enforced; storage trimming keeps the leaf and tool pairing, and a
last-resort pass clips old tool, assistant and oversized user bodies (including
one huge pasted message) so the state still saves.

State is emitted **before** the terminal output. A save failure emits
`state_save_failed`, keeps the previous encoded state instead of writing an
empty snapshot, and never reports a normal completion. The terminal JSON
payload includes a read-only `state_summary` and a `state_ref` that says
`encoded`/`failed`; `platform_persisted` remains `null` because the SDK output
is not proof of a Dify variable write.

## Skills

Skills are discovered from `skills/*/SKILL.md` (this package ships the opt-in
`pi-strategy-help` builtin, hidden from the model) and from `app_skills_yaml`.
They are
checked for eligibility against the current tool set, activated by the user
(`/skill:name ...`) or the model (`activate_skill`), and read through bounded,
paged `read_skill_resource` calls. Paths outside the skill are rejected. On a
later turn, revoked/ineligible skill bodies are withheld from the model
projection, including user-activated skill messages.

## Runtime configuration

Identical to pi_dify minus the display contract settings:

```json
{
  "max_model_requests": 24,
  "max_tool_calls": 32,
  "max_wall_seconds": 300,
  "context_window": 128000,
  "reserved_output_tokens": 8192,
  "tool_stream_mode": "delta",
  "stream_mode": "stream",
  "stream_fallback": true,
  "auto_compact": true,
  "mcp_tools_exclude": [],
  "state_max_encoded_bytes": 190000,
  "tool_timeout_seconds": 120,
  "model_timeout_seconds": 180,
  "thinking_tags": true
}
```

`tool_stream_mode` must be `delta` or `snapshot` explicitly. Fixed prompt
content over the context window is rejected without a useless summarization;
history overflow compacts and retries once with a continuation message,
preserving the current user request and every completed tool result without
replaying a tool. `thinking_tags` defaults to `true`. `tool_timeout_seconds`
and `model_timeout_seconds` bound the bridged Dify session calls (per tool call
and per model request/stream chunk); `0` disables the bound.

## Offline package

```bash
python3 scripts/download_offline_wheels.py --arch amd64 --arch arm64
python3 scripts/build_offline_package.py --arch amd64
python3 scripts/build_offline_package.py --arch arm64
python3 scripts/verify_offline_package.py dist/pi_strategy-0.2.1-offline-linux-amd64.difypkg --arch amd64
python3 scripts/verify_offline_package.py dist/pi_strategy-0.2.1-offline-linux-arm64.difypkg --arch arm64 --resolve-only
```

Each package contains `wheels/` for exactly one architecture,
`requirements.lock.txt`, `VERSION_MANIFEST.json`, third-party notices and
license texts. Packaging invariants, verification (including arm64 execution
under qemu) and air-gapped deployment live in
[../docs/packaging.md](../docs/packaging.md).

Upgrading on a Dify host: installing the same `plugin_id` fails with
"already installed" — uninstall first (the uninstall API needs the
`plugin_installation_id`), install the new package, then update the Agent
node's `plugin_unique_identifier` in the workflow draft and republish;
otherwise the app keeps serving the previous unpacked copy.

## Tests

From this directory:

```bash
python -m unittest discover -s tests
uvx black . -C -l 100 --exclude '/(.venv|wheels|dist)/'
uvx ruff check pi_strategy tests strategies provider
```

The suite uses `unittest`, fake Dify sessions and the real pinned Pi packages.
It covers state round-trips/trimming (including oversized user messages) and
foreign-prefix rejection, streaming modes, tool pairing and native tool cards,
budgets, compaction/overflow recovery, skills, MCP lifecycle/fail-soft/call
classification, blocked-call stop handling and strategy configuration. It does
not replace Dify platform or provider evidence.

## Known limits

- No exactly-once guarantee across crashes; unknown write outcomes are preserved
  and must be verified before retrying.
- Stop is cooperative. A synchronous Dify SDK call already in progress is
  abandoned by the run (state is saved, status `stopped`) but the underlying
  stdio call may still complete remotely; its outcome is reported as unknown.
  A worker blocked in the SDK cannot be killed from Python, so one stuck call
  may keep an OS thread alive until the provider answers.
- `revision` is a delivery fact, not an atomic concurrency lock.
- Dify may run two turns of one conversation concurrently; the state revision
  then reflects the last write, not a serialized history.
- HTML tool cards depend on the deployed Dify UI's markdown/HTML rendering;
  verify on the target Dify version.
