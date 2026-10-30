# Pi Agent Workbench

A static Vue 3 workbench that consumes the `piagent.display.v1` contract carried
by Dify agent logs. It renders real reasoning, message deltas, tool lifecycles,
skill activation/reads, compaction, AskUser questionnaires, approvals, files and
explicit terminal states.

## Development

```bash
npm install
npm run dev        # Vite dev server
npm run test       # Vitest + happy-dom
npm run build      # static dist/
npm run check:static
```

The dev server does not proxy Dify by default. Open **Connection**, set the Dify
API base URL (usually `/v1` behind a same-origin proxy) and an app API key, then
select or start a conversation.

## Static deployment

`npm run build` produces `dist/` with relative asset paths. Host it on any static
web server. It does not run an Agent, Node service, WebSocket service or the
community Pi backend.

Optional `config.json` beside `index.html` supplies non-secret deployment
defaults:

```json
{
  "title": "Support Copilot",
  "baseUrl": "/v1",
  "user": "workbench",
  "inputs": {}
}
```

The app API key is entered at runtime and kept in `sessionStorage` for the tab,
never in `config.json` or the repository. For production, put Dify behind a
same-origin proxy so the key is not exposed to the browser bundle; the current
direct-key mode is a deployment convenience, not a hardened secret store.

The Dify application node must map `query`, `model`, `tools`, `files`,
`instruction`, `app_skills_yaml`, `mcp_servers_config`, `runtime_config`,
`interaction`, `agent_state` and `conversation_id`. The workbench sends
`interaction` inside the configured app inputs; it does not assume arbitrary
inputs reach the plugin.

## Replay

Static scenarios run without Dify or the community backend:

- `/?replay=process` — reasoning, tool, skill activation/read, compaction and a
  final answer.
- `/?replay=questionnaire` — a multi-question AskUser form that pauses and then
  answers locally.
- `/?replay=approval` — a separate approval card and an unknown remote write.

Replay mode is explicitly labelled and never calls a model. It is generated from
the same contract, projection and components as the live stream.

## Dify stream interpretation

`src/dify/transport.ts` reads Dify SSE. `src/dify/controller.ts` unwraps
`agent_log` payloads and finds the display event at any SDK nesting level. It
merges the Dify native final answer without duplicating the Pi answer, discards
stale history responses after conversation switches, and never automatically
re-POSTs after a disconnect. No trusted terminal state is displayed as
unconfirmed/unknown.

## Security

- No HTML output from model text: Markdown is rendered with `html: false`.
- No external fonts, scripts, CDNs or telemetry in the static build.
- The static gate fails on `src=`/`href=`/`url()`/`fetch()` external asset loads
  and on bundled Pi SDK/Node backend markers.
- Credentials are not logged or rendered; tool arguments/results are projected
  and clipped by the plugin before they reach the workbench.

## Attribution

The chat presentation layer is derived from
[spmurrayzzz/leyline](https://github.com/spmurrayzzz/leyline) at commit
`a368c8b7590b88bb138c024b7dd8414b3dcc2a73` (Apache-2.0). See
[NOTICE](NOTICE) and `src/vendor/leyline/LICENSE`. No Leyline Node/Pi backend,
WebSocket service, Electron shell, Git/terminal/MCP workspace or tracing
service is included.

## Limits

- The workbench does not claim full official Pi RPC compatibility.
- History reconstruction depends on Dify retaining agent log data; if only
  query/answer are retained it shows the text history and warns that process
  events are missing.
- When Dify exposes conversation variables, the workbench also reads the saved
  `agent_state` to restore the latest questionnaire, approval and terminal state
  after a refresh. It does not reconstruct missing historical tool traces or
  grant authorization; submitted interactions are validated by the plugin.
  The Dify graph must save the plugin's `agent_state` output back to the
  conversation variable. An unavailable variable endpoint leaves text history
  usable and never triggers an automatic resubmission.
- Stop is best effort and the UI distinguishes requested stop from a trusted
  server terminal state.
