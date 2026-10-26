# CC Agent

CC Agent 是一个 Dify Agent Strategy 插件，用来在 Dify 生态里提供更完整的通用 agent 能力。它不是纯代码 agent，而是面向日常文件处理、工具调用、技能扩展、长对话状态和可下载产物的 agent capability extension。

项目当前有两个运行模式：

- `dify_only`: 只依赖 Dify 入参/出参。状态通过 encoded `agent_state` 在 Dify workflow 中流转；不启用 workspace、文件工具、脚本执行和用户 skill 管理。
- `minio`: MinIO/S3 是状态、workspace、skills 的权威持久化层。启用文件管理、MinIO skill 包、`run_python`、`SkillRunScript`、用户 skill 安装/删除和产物下载。

## Directory Layout

```text
.
├── cc_agent/                         # Dify plugin
│   ├── manifest.yaml                 # Plugin manifest
│   ├── main.py                       # Dify plugin entry
│   ├── provider/
│   │   └── agent.yaml                # Provider registration
│   ├── strategies/
│   │   ├── base.py                   # Shared AgentStrategy adapter
│   │   ├── cc_agent_agui.py         # AG-UI strategy entry
│   │   ├── cc_agent_dify.py         # Dify-native strategy entry
│   │   ├── cc_agent_agui.yaml       # AG-UI strategy schema
│   │   └── cc_agent_dify.yaml       # Dify-native strategy schema
│   ├── core/                 # Agent runtime implementation
│   ├── skills/                       # Bundled agent skills
│   ├── tests/                        # Python tests
│   └── scripts/                      # Offline package scripts
└── copilotkit-dify/                  # Frontend renderer for AG-UI/Dify output
```

`core` is the shared runtime package used by both Strategy entries.

## Runtime Architecture

The runtime is intentionally lightweight. It uses four thin ports and a single explicit run environment instead of a DI container or generic event bus.

```text
Dify AgentStrategy
  -> AgentRunConfig
  -> RunEnvironment
       -> StateBackend
       -> SkillCatalog
       -> ToolCatalog
       -> ProtocolRenderer
       -> WorkspaceSession      (minio only)
       -> SkillLibrarySession   (minio only)
  -> AgentLoop
  -> commit state/workspace
  -> render final output
```

The four ports are:

| Port | Responsibility |
| --- | --- |
| `StateBackend` | Load and commit agent state. Dify-only uses encoded `agent_state`; MinIO mode reads/writes MinIO state and ignores input `agent_state`. |
| `SkillCatalog` | Merge bundled, app YAML, MinIO agent/app/user skills, then render visible skill context. User skill management requires MinIO. |
| `ToolCatalog` | Centralize visible tools by profile, schema generation, external tool conflict naming and executor-side profile checks. |
| `ProtocolRenderer` | Render the same internal events to AG-UI or Dify native output. Writer state stays inside each renderer. |

## Strategies

The provider exposes two fixed Strategy surfaces:

- `CC Agent (AG-UI)`: emits AG-UI events and enables the bundled `answers-ui` and `answers-charts` skills.
- `CC Agent (Dify)`: emits Dify-native text, JSON, blob and log messages without structured-answer prompting.

`capability_mode` remains independent from this choice. In either Strategy, `create-skill` is bundled only when `capability_mode=minio`.

## Strategy Parameters

Core parameters:

| Parameter | Required | Mode | Description |
| --- | --- | --- | --- |
| `model` | yes | both | Dify model selector with tool-call capability. |
| `tools` | no | both | Dify-injected external tools. |
| `query` | yes | both | Current user input. |
| `instruction` | no | both | App-level behavior, business rules and answer style. |
| `capability_mode` | no | both | `dify_only` or `minio`. Defaults to `dify_only`. |
| `agent_state` | no | dify_only | Encoded state from the previous turn. Ignored in MinIO mode. |
| `storage` | minio only | minio | JSON string with MinIO connection and scope. See the contract below. |
| `files` | no | minio | Dify uploaded files JSON. Imported into MinIO workspace for the current turn. |
| `app_skills_yaml` | no | both | App-level skill definitions. In MinIO mode it is treated as app-level overlay. |
| `runtime_config` | no | both | Optional advanced runtime config JSON. Defaults are suitable for normal setup. |
| `show_tool_calls` | no | both | Whether to emit visible tool activity. |
| `deepseek_thinking_compat` | no | both | Compatibility fallback for DeepSeek thinking mode. |

Runtime config:

```json
{
  "maximum_iterations": 8,
  "max_observation_chars": 8000,
  "max_history_messages": 40,
  "max_total_context_chars": 64000,
  "max_repeated_tool_calls": 3,
  "max_consecutive_tool_errors": 3,
  "state_reset": false
}
```

`runtime_config` can be left empty. Unknown fields are ignored and do not enter prompts or final output.

Removed parameters:

- `history`, `memory`, `tasks`, `skills`: replaced by `agent_state`.
- `workspace_enabled`, `skills_enabled`: replaced by `capability_mode`.
- `app_id`, `user_id`, `conversation_id`, flat `minio_*` parameters: replaced by `storage`.
- `workspace_scope_id`: removed. It is not part of the storage scope or object paths.
- `think_model`, `flash_model`, `multimodal_model`: removed; CC Agent uses the single `model`.
- flat loop/budget fields: replaced by `runtime_config`.
- `tool_allowlist`, `tool_denylist`, `tool_confirmation_list`, `skill_package_max_bytes`: removed from public strategy parameters.
- `output_protocol`, `skill_denylist`, `user_skill_scripts_enabled`: removed from the public schema; protocol and bundled skill visibility are fixed by the selected Strategy.

## Storage JSON Contract

`storage` is the only MinIO configuration entry. It is passed as a JSON string when `capability_mode=minio`.

Standard format:

```json
{
  "provider": "minio",
  "endpoint": "http://localhost:19000",
  "bucket": "cc-agent",
  "access_key": "minioadmin",
  "secret_key": "minioadmin123",
  "secure": false,
  "public_download_base_url": "",
  "presign_expiry_seconds": 3600,
  "ttl_days": 30,
  "scope": {
    "app_id": "app-dev",
    "user_id": "user-dev",
    "conversation_id": "conversation-dev"
  }
}
```

Required fields in MinIO mode:

| Field | Description |
| --- | --- |
| `provider` | Must be `minio`. If omitted, `minio` is assumed. |
| `endpoint` | MinIO/S3 endpoint. Include scheme, for example `http://localhost:19000`. |
| `bucket` | Bucket name used by CC Agent. |
| `access_key` | MinIO access key. Configuration only; never exposed to prompt or final JSON. |
| `secret_key` | MinIO secret key. Configuration only; never exposed to prompt or final JSON. |
| `scope.app_id` | Application scope id. |
| `scope.user_id` | User scope id. |
| `scope.conversation_id` | Conversation scope id. |

Optional fields:

| Field | Default | Description |
| --- | --- | --- |
| `secure` | `false` | Whether to use HTTPS semantics for the MinIO client. |
| `public_download_base_url` | empty | Optional public gateway base for downloads. Empty means presigned MinIO URLs are used. |
| `presign_expiry_seconds` | `3600` | Download URL expiry. |
| `ttl_days` | `30` | Workspace retention hint used by workspace metadata and cleanup policy. |

Accepted but non-standard aliases:

- `accessKey` for `access_key`
- `secretKey` for `secret_key`
- `publicDownloadBaseUrl` or `download_base_url` for `public_download_base_url`
- `presignExpirySeconds` for `presign_expiry_seconds`
- `ttlDays` for `ttl_days`
- `scope.appId`, `scope.userId`, `scope.conversationId`

Use the standard snake_case fields for new workflows.

### Dify Template Example

In Dify, `storage` is a string parameter, so pass a serialized JSON object. Example:

```json
{"provider":"minio","endpoint":"http://localhost:19000","bucket":"cc-agent","access_key":"minioadmin","secret_key":"minioadmin123","secure":false,"presign_expiry_seconds":3600,"ttl_days":30,"scope":{"app_id":"{{app.id}}","user_id":"{{user.id}}","conversation_id":"{{conversation.id}}"}}
```

If your workflow does not expose those exact template variables, map them to stable equivalents. The only rule is that the same app/user/conversation tuple must be passed on every turn of the same conversation.

### MinIO Object Scope

All MinIO state and workspace paths are scoped by:

```text
scope.app_id / scope.user_id / scope.conversation_id
```

There is no `workspace_scope_id`.

Conceptual layout:

```text
{app_id}/users/{user_id}/conversations/{conversation_id}/workspace/manifest.json
{app_id}/users/{user_id}/conversations/{conversation_id}/workspace/lock.json
{app_id}/users/{user_id}/conversations/{conversation_id}/state/agent_state.json
{app_id}/users/{user_id}/skills/{skill_id}/...
{app_id}/skills/{skill_id}/...
_cc_agent/skills/agent/{skill_id}/...
objects/sha256/{first2}/{sha256}
```

The exact internal file names may evolve, but the scope contract must not.

## Mode Behavior

### `dify_only`

Use this mode when you want a deployable Dify-only strategy without external storage.

Enabled:

- Dify-injected external tools
- bundled agent skills
- `app_skills_yaml`
- memory/task tools
- `AskUserQuestion`
- encoded `agent_state`
- AG-UI or Dify native output

Disabled:

- workspace and file tools
- `run_python`
- `SkillRunScript`
- `SkillInstall` / `SkillRemove`
- MinIO skill packages
- downloadable workspace artifacts

State flow:

1. Workflow passes previous final `agent_state` into the next run.
2. Runtime decodes `ccagent-state:v1:gzip-base64:...`.
3. Runtime returns a new `agent_state` plus a readable `state_summary`.

### `minio`

Use this mode when you want persistent workspace, uploaded files, downloadable artifacts, skill packages and code execution.

Enabled:

- all Dify-only features
- file import from Dify uploads
- `list_files`, `inspect_file`, `read_file`, `write_file`
- `run_python`
- `SkillRunScript`
- `SkillInstall`, `SkillRemove`
- MinIO-backed state/workspace/skills
- workspace activity payloads with `download_url`

State flow:

1. Runtime validates `storage`.
2. Runtime loads state from MinIO and ignores input `agent_state`.
3. Runtime imports current-turn Dify files into the MinIO workspace.
4. Runtime commits state, workspace manifest and generated artifacts back to MinIO.
5. Final output returns `state_ref` and `state_summary`, not encoded state.

Configuration errors fail the run. Runtime MinIO/tool failures are returned as structured errors where possible.

## Agent State

The state bundle contains:

```json
{
  "revision": 1,
  "history": {},
  "summary": "",
  "memory": [],
  "tasks": [],
  "permissions": {},
  "active_skills": [],
  "last_execution_metadata": {}
}
```

Dify-only encoded prefix:

```text
ccagent-state:v1:gzip-base64:
```

Old `ccagent:v3:gzip-base64:` values are intentionally not part of the new contract.

`state_summary` is read-only metadata for workflows and UI. It is useful for checks such as memory count, task count and active skill names, but it is not a recovery source.

## Skills

Skill sources by mode:

| Mode | Sources |
| --- | --- |
| `dify_only` | bundled agent skills + `app_skills_yaml` |
| `minio` | bundled agent skills + MinIO agent/app/user packages + `app_skills_yaml` overlay |

Merge priority:

```text
bundled agent > MinIO agent > MinIO app > app_skills_yaml > MinIO user
```

User skill management is only available in MinIO mode. In Dify-only mode, install/remove returns:

```text
Skill management requires MinIO storage
```

MinIO skill package layout:

```text
skill.json
files/SKILL.md
files/README.md
files/references/**
files/assets/**
files/scripts/**
```

`skill.json` minimal format:

```json
{
  "id": "spreadsheet",
  "name": "spreadsheet",
  "display_name": "Spreadsheet",
  "layer": "user",
  "version": 1,
  "status": "active",
  "description": "Analyze CSV and Excel files.",
  "updated_at": "2026-06-22T00:00:00Z"
}
```

`id` and `name` must match `[A-Za-z0-9_-]{1,64}`.

## Tools By Mode

Always available, subject to allowlist/denylist:

- `SkillList`
- `Skill`
- `MemoryList`
- `MemorySearch`
- `MemorySave`
- `MemoryDelete`
- `TaskCreate`
- `TaskUpdate`
- `TaskGet`
- `TaskList`
- `AskUserQuestion`
- Dify-injected external tools

MinIO-only tools:

- `list_files`
- `inspect_file`
- `read_file`
- `write_file`
- `run_python`
- `SkillReadResource`
- `SkillRunScript`
- `SkillInstall`
- `SkillRemove`

There is no generic bash/full shell tool. Python execution is constrained to the current workspace and writes artifacts through the workspace outputs flow.

## Output Protocols

CC Agent exposes output style as two separate Strategy entries:

- `CC Agent (AG-UI)` always emits AG-UI stream events.
- `CC Agent (Dify)` always emits Dify-native text, JSON, blob and log messages.

The protocol is no longer a runtime parameter, so a saved node cannot accidentally drift to the wrong frontend contract.

Workspace activity event name:

```text
cc_agent.workspace
```

Workspace files exposed to the frontend only include:

```json
{
  "id": "file-id",
  "name": "report.xlsx",
  "size": 12345,
  "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "status": "ready",
  "download_url": "https://...",
  "expires_at": "2026-06-22T12:00:00Z"
}
```

Internal references such as MinIO object keys, `workspace://...` and `dify-file://...` must not be shown to users.

## Development

Python tests:

```powershell
python -B -m unittest discover cc_agent\tests
```

Frontend tests:

```powershell
cd copilotkit-dify
npm run test
```

Build offline Dify package:

```powershell
python cc_agent\scripts\build_offline_package.py
```

Useful smoke tests:

- Dify-only: run two turns and pass final `agent_state` from turn one into turn two.
- MinIO: upload CSV, ask the agent to generate XLSX with `run_python`, confirm `list_files` shows the artifact and the `download_url` works.

## Current Boundaries

In scope:

- Dify-native tool-call loop
- dual mode capability profile
- encoded state for Dify-only
- MinIO-backed state/workspace/skills
- workspace file tools
- Python runner
- skill package install/remove in user layer
- AG-UI and Dify native output
- offline Linux amd64/arm64 package build

Out of scope for now:

- generic bash/full shell
- arbitrary package installation at runtime
- browser automation inside the agent runtime
- subagents/forked skills
- user-configurable shell hooks
- OS-level seccomp/container isolation beyond the hosting Dify/plugin sandbox

## Security Notes

- `access_key` and `secret_key` are configuration only. They must not enter prompts, logs, tool metadata, final JSON or frontend payloads.
- MinIO mode must fail on missing required storage fields instead of silently falling back to Dify-only.
- Tool visibility is enforced twice: at schema registration time and again before execution.
- Generated artifacts are collected from the workspace outputs directory, not arbitrary filesystem paths.
