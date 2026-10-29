---
name: pi-agent-help
description: Explain how this Pi Agent workbench asks questions, requests approval and preserves state. Activate explicitly with /skill:pi-agent-help.
disable-model-invocation: true
---

# Pi Agent help

Use `ask_user` for information questions. The assistant pauses after the tool
result; the workbench shows a form and the next Dify turn submits a structured
`interaction` with question IDs and answers. A questionnaire never authorizes a
tool.

Tool approval is a separate interaction. The pending operation includes the
original call ID, tool and parameters. Approval is re-checked against the
current tool set, policy and budget before execution; rejection is reported and
the original batch tail is not replayed.

The Pi session is stored in the Dify `agent_state` variable with the
`piagent-state:v1:gzip-base64:` prefix. Only the server-side state is
authoritative; browser caches are drafts. If an external write result is
unknown, verify the business result before retrying.
