# Pi Agent v2 — implementation evidence

Date: 2026-10-29. Branch: `feat/pi-agent-v2`.

This document reports what was implemented and actually verified in this
environment. It does **not** claim platform acceptance. Every ticket has working
code and local evidence; tickets that require a real Dify instance, real
providers, real remote MCP services or an arm64 host remain partially verified.

## Environment

| Item | Value |
| --- | --- |
| Host | Linux x86_64 (amd64) |
| Python (plugin tests) | CPython 3.12.14 |
| Node | v24.9.0 |
| Browser used for static replay | system Firefox (headless screenshots) |
| Dify instance | not available |
| arm64 machine | not available |
| Real remote MCP service | not available (fake protocol session only) |

## Verification summary

| Check | Result |
| --- | --- |
| `python -m unittest discover -s pi_dify/tests` | **61 passed** |
| `npm run test` (workbench) | **27 passed** |
| `npm run build` | success, 3 static files, ~396 KB |
| `npm run check:static` | **0 violations** (no external runtime assets / Pi SDK/Node backend markers) |
| Static replay browser render | process, questionnaire and approval screenshots |
| amd64 offline package | built, `--no-index` install, fake-Dify smoke **completed** |
| arm64 offline package | built; wheel resolution for aarch64 **ok**; execution **not run** |

Commands:

```bash
cd pi_dify
/tmp/pi-probe/.venv/bin/python -m unittest discover -s tests

cd ../pi_workbench
npm run test
npm run build
npm run check:static

cd ../pi_dify
python3 scripts/build_offline_package.py --arch amd64
python3 scripts/build_offline_package.py --arch arm64
python3 scripts/verify_offline_package.py dist/pi_dify-0.1.0-offline-linux-amd64.difypkg --arch amd64
python3 scripts/verify_offline_package.py dist/pi_dify-0.1.0-offline-linux-arm64.difypkg --arch arm64 --resolve-only
```

## Package artifacts

| Architecture | File | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| amd64 | `pi_dify-0.1.0-offline-linux-amd64.difypkg` | 26,283,527 | `89f373f35094943c0d58be31aa21dfa50c5572f55e340f65e6c9420650e0f973` |
| arm64 | `pi_dify-0.1.0-offline-linux-arm64.difypkg` | 25,301,257 | `7f90a1456a80f5ac3c25cc148c83708a9473760ce9478a181f9024b8ec490362` |

Both packages contain 72 architecture-appropriate wheels, `VERSION_MANIFEST.json`,
third-party notices/license texts, the plugin source, `requirements.lock.txt` and
the provider/strategy manifests. The packages are build outputs under
`pi_dify/dist/` and are not committed (regenerate with the commands above).

### amd64 evidence

`docs/evidence/amd64-offline.json`:

- install from bundled wheels only (`uv pip install --no-index --find-links wheels`)
- Python 3.12.14, install 0.24 s
- smoke turn: answer `offline ok`, terminal `completed`, one model request, state
  `piagent-state:v1:gzip-base64:` written and read back
- package hash matches the artifact above

This proves dependency closure and basic Pi runtime in an isolated amd64 venv.
It does not prove Dify plugin-runner installation, a real Dify model or a real
Dify tool.

### arm64 evidence

`docs/evidence/arm64-resolution.json`:

- all 72 locked packages resolve for `aarch64-unknown-linux-gnu`
- no actual arm64 execution or arm64 Dify runner evidence

## Frontend evidence

`docs/evidence/workbench-static-report.json` records every static file hash and
0 violations. Screenshots:

- `docs/evidence/screenshots/replay-process.png` — reasoning, tool card, skill
  activation/read, compaction facts, final answer, terminal state.
- `docs/evidence/screenshots/replay-questionnaire.png` — single/multi/text
  questionnaire with required markers, cancel/submit and disabled composer.
- `docs/evidence/screenshots/replay-approval.png` — separate approval card,
  scope selector, not-executed tool state.

The screenshots were taken from the built `dist/` with headless Firefox. The
component tests additionally exercise answer selection, multi-select validation,
submit, duplicate-submit protection, historical answers, approval rejection and
stale-history isolation.

## Ticket matrix

Legend: **core** = code implemented; **local** = fake/contract/local build
verified; **platform** = requires real Dify/provider/architecture and is not
verified here.

| Ticket | Core | Local evidence | Platform gap |
| --- | --- | --- | --- |
| 01 Vue extraction/replay | yes | static build, 27 tests, three browser screenshots, Leyline NOTICE/license | none material; full third-party asset audit is limited to declared dependencies |
| 02 Dify stream penetration | yes | transport/controller/reducer tests with mocked Dify SSE, history extraction, final-answer merge | real Dify agent-log nesting and history retention not tested |
| 03 Pi Q&A + cross-turn | yes | real pinned Pi 0.6.0 harness, 61 tests, two-turn state round-trips, isolated worker thread | real Dify SDK context / provider identity not tested |
| 04 dual-arch offline bootstrap | yes | amd64 offline install+smoke; arm64 resolution | arm64 execution and Dify installer offline behavior not tested |
| 05 Dify tools/cards/attachments | yes | fake Dify tools, pairing, repeated-halves/JSON dedupe, artifacts, generic card | real Dify tool response shapes and blob forwarding not tested |
| 06 model stream compatibility | yes | delta/snapshot/interleaved/bad JSON/reasoning/non-stream fallback tests | real provider chunk samples not collected |
| 07 state/history recovery | yes | codec, 190KB trimming, pending-group retention, corrupt/oversized rejection, stale history test | real Dify variable read-back/history logs not tested |
| 08 skills lifecycle | yes | discovery/eligibility/activation/resource paging/traversal tests, UI cards | real application YAML and Dify history activity not tested |
| 09 remote MCP identity/artifacts | yes | per-run sessions, app-only filter, timeout/unknown, one-time blob delivery, isolation test | no real remote MCP server; headers/identity only fake-tested |
| 10 budgets/guards/stats | yes | model/tool/time/token ledger, duplicate and consecutive-error guards, split reported/estimated usage | real provider usage matrix not tested |
| 11 compaction/overflow | yes | Pi compaction events in UI; single overflow recovery test with summarization and no tool replay | real provider overflow and long-context behavior not tested |
| 12 AskUser round-trip | yes | deterministic gate, zero tail execution, cross-turn answer, duplicate/expired/invalid checks, cancel, UI form | real Dify input mapping and refresh evidence not tested |
| 13 approval/policy re-check | yes | separate approval pending, scope grant, reject/approve, current tool/budget re-check, single result replacement | real Dify policy/permission context not tested |
| 14 MCP resume/unknown | yes | remote pending has no connection/secrets, current-run reconnect path, unknown write preservation, one-time artifacts | no real remote unknown-side-effect service |
| 15 stop/failure/security | yes | cooperative abort signal, safe `agent_failed` JSON, secret redaction, stop API wiring, state-save failure test | real Dify stop/disconnect propagation not tested |
| 16 compatibility/static release | yes | manifest minimum 1.7.0, 1.15.0 target documented, explicit node mapping, static report, old plugin untouched | real 1.7.0/1.15.0 runs not performed |
| 17 amd64 acceptance | partial | offline package + fake Dify smoke only | no target Dify, no controlled real model/tools, no full V01–V19 business run |
| 18 arm64 acceptance | partial | package + aarch64 wheel resolution only | no arm64 execution, Dify runner or business evidence |

## Gaps and risks (explicit)

1. **No Dify instance in this environment.** The code follows the plugin SDK
   contract and the existing `cc_agent/` adapter patterns, but the real
   AgentStrategy SDK context, `agent_log` SSE envelope, conversation-variable
   write semantics and history retention remain unverified.
2. **No real provider matrix.** Streaming modes are driven by controlled fake
   chunks; real Dify provider chunk shapes (including usage placement and
   reasoning fields) still need capture.
3. **No arm64 execution.** Only aarch64 dependency resolution was checked.
4. **Offline installer assumption.** Packages include wheels and a lock file,
   but Dify's plugin runner must install from the bundled wheel directory for a
   fully network-isolated install. Verify in the target Dify version.
5. **Stop is cooperative.** A synchronous provider SDK call already in flight
   may not be interruptible; the UI distinguishes requested stop from a trusted
   terminal state.
6. **No exactly-once.** Unknown write outcomes are preserved with a business
   reference and require verification; there is no cross-crash exactly-once
   promise.
7. **History process reconstruction** relies on Dify keeping agent log data
   (`agent_thoughts` or nested data). If it does not, the workbench shows text
   history and warns that process events are missing.
