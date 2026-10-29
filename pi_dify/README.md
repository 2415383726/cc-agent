# Pi Agent for Dify

`pi_dify` is a new, independent Dify Agent Strategy plugin built on the
community Python packages `pi-agent-core-lc==0.6.0` and
`pi-agent-harness-lc==0.6.0`. Dify supplies the current model and authorized
tools; the host owns budgets, skills, cross-turn state, interactions and the
platform output.

The old `cc_agent/` plugin, its sessions and its frontend remain independent.
This plugin starts new sessions and does not import old `ccagent-state` values.

## Status

Core implementation and local verification are complete. Real Dify 1.15.0 /
1.7.0 SSE penetration, a real provider matrix and arm64 execution have **not**
been verified in this environment. See [v2 implementation evidence](../docs/evidence/v2-implementation.md)
for the exact pass/pending matrix. Do not read this README as production
acceptance.

## Architecture

```
Dify AgentStrategy
  └─ PiAgentRuntime (one worker thread + one event loop per request)
       ├─ PiHarness (pinned 0.6.0) + Pi core loop
       ├─ DifyModelStream  → current Dify model only
       ├─ ToolRuntime      → Dify tools, remote MCP, internal ask/skill tools
       ├─ RunLedger        → one budget for models, tools, retries, summaries
       ├─ piagent-state:v1:gzip-base64: (Dify agent_state)
       └─ DisplayEvents    → Dify LOG JSON + final Dify text + state variable
```

`pi_agent/harness.py` is the only adapter subclass. It adds the two seams the
0.6.0 harness does not expose (`should_stop_after_turn` wiring and a resume turn
seeded with a custom message); it does not copy the loop or monkeypatch the
package.

## Dify node mapping

The application node must explicitly map these parameters:

| Parameter | Purpose |
| --- | --- |
| `model` | Current Dify model (model-selector). Required. |
| `query` | Current user text. Required. |
| `tools` | Dify-injected tools available for this run. |
| `files` | Attachment metadata JSON (metadata only, not file content). |
| `instruction` | Application instruction. |
| `app_skills_yaml` | Application skill definitions/resources. |
| `mcp_servers_config` | Remote MCP servers (already-resolved headers). |
| `runtime_config` | Budgets, stream mode, compaction, approval policy. |
| `interaction` | Structured answer, approval decision or cancellation. |
| `agent_state` | Dify conversation variable; the only cross-turn authority. |
| `conversation_id`, `user_id`, `app_id` | Session identity and isolation. |

Dify does not automatically pass arbitrary web inputs to the strategy; map them
in the node. The workbench sends `interaction` as a JSON string inside the
configured app inputs.

### Interaction payloads

Questionnaire answer:

```json
{
  "type": "ask_user",
  "pending_id": "qst_...",
  "answers": {"order": "o1", "reasons": ["o1", "o3"], "notes": "text"}
}
```

Approval:

```json
{
  "type": "approval",
  "pending_id": "apv_...",
  "decision": "approve",
  "scope": "once"
}
```

Cancel either pending interaction:

```json
{"type": "cancel", "pending_id": "qst_..."}
```

Answers are validated against the current `agent_state` pending. Wrong,
missing, expired, duplicate or already-consumed answers never execute a tool or
call the model; they return a readable rejection and the current waiting
projection. An approval decision is additionally checked against the original
session tool call (name and full arguments) and the current tool source, so a
tampered or rebuilt pending cannot execute a different operation.

## State

`agent_state` uses `piagent-state:v1:gzip-base64:`. The bundle contains the Pi
session entries/leaf, active skills, session grants, pending interaction,
consumption records and run statistics. Decode and decompress are size-limited;
unknown prefixes/versions, dangling parents, cycles and unpaired tool calls are
rejected. The approximate 190KB encoded boundary is enforced; storage trimming
keeps the pending group, leaf and tool pairing.

State is emitted **before** the terminal Dify log. A save failure emits
`state_save_failed`, keeps the previous encoded state instead of writing an
empty snapshot, and never reports a normal completion. `run.state` includes a
read-only `state_summary` describing the actually encoded snapshot.
`state_ref` says `encoded`/`failed`; `platform_persisted` remains `null` because
the SDK output is not proof of a Dify variable write.

## Skills

```yaml
skills:
  - name: refund-policy
    description: Refund rules for support agents
    requires_tools: [lookup_order]
    content: |
      Refunds require an unused item inside 30 days.
    resources:
      guide.md: |
        Step one: verify the order date.
```

Skills are discovered from `skills/*/SKILL.md` when builtin skills are shipped
(no builtin skill is bundled by default) and from `app_skills_yaml`. They are
checked for eligibility against the current tool set, activated by the user
(`/skill:name ...`) or the model (`activate_skill`), and read through bounded,
paged `read_skill_resource` calls. Paths outside the skill are rejected. On a
later turn, revoked/ineligible skill bodies are withheld from the model
projection, including user-activated skill messages.

## Runtime configuration

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
  "approval_mode": "configured",
  "approval_tools": ["delete_record"],
  "approval_timeout_seconds": 0,
  "mcp_tools_exclude": [],
  "state_max_encoded_bytes": 190000,
  "thinking_tags": false
}
```

`tool_stream_mode` must be `delta` or `snapshot` explicitly. A tool is executed
only after complete argument validation. Fixed prompt content over the context
window is rejected without a useless summarization; history overflow compacts
and retries once with a continuation message, preserving the current user
request and every completed tool result without replaying a tool.

`thinking_tags` defaults to `false`: only provider reasoning fields are shown as
reasoning. Set it to `true` only for providers that emit literal `<think>` tags.
`approval_timeout_seconds` defaults to 0 (no expiry); a positive value makes an
approval expire and be rejected before execution.

## Offline package

```bash
python3 scripts/download_offline_wheels.py --arch amd64 --arch arm64
python3 scripts/build_offline_package.py --arch amd64
python3 scripts/build_offline_package.py --arch arm64
python3 scripts/verify_offline_package.py dist/pi_dify-0.1.0-offline-linux-amd64.difypkg --arch amd64
python3 scripts/verify_offline_package.py dist/pi_dify-0.1.0-offline-linux-arm64.difypkg --arch arm64 --resolve-only
```

Each package contains `wheels/` for exactly one architecture,
`requirements.lock.txt`, `VERSION_MANIFEST.json`, third-party notices and
license texts. The amd64 verification installs with `--no-index` from only the
bundled wheels and runs a fake-Dify text turn. The arm64 verification only
resolves the wheel set on this host; it is not execution evidence.

## Tests

From this directory:

```bash
python -m unittest discover -s tests
uvx black . -C -l 100 --exclude '/(.venv|wheels|dist)/'
uvx ruff check pi_agent tests strategies provider
```

The suite uses `unittest`, fake Dify sessions and the real pinned Pi packages.
It covers state round-trips/trimming, streaming modes, tool pairing, AskUser,
approvals, budgets, compaction/overflow recovery, skills, MCP lifecycle and
strategy configuration. It does not replace Dify platform or provider evidence.

## Known limits

- No exactly-once guarantee across crashes; unknown write outcomes are preserved
  and must be verified before retrying.
- Stop is cooperative. A synchronous Dify SDK call already in progress may
  finish after a client disconnect.
- `revision` is a delivery fact, not an atomic concurrency lock.
- The workbench is a separate static build; a `.difypkg` does not host it.
