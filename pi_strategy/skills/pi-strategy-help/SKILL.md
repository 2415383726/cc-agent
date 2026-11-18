---
name: pi-strategy-help
description: Explain how this Pi Strategy plugin executes tools and preserves state. Activate explicitly with /skill:pi-strategy-help.
disable-model-invocation: true
---

# Pi Strategy help

Tools execute immediately when the model calls them. There is no approval
step, no confirmation keyword and no pending interaction: a call is checked
against the current tool set and budget, then run (or reported as not executed
when the budget or the stop signal blocks it).

The Pi session is stored in the Dify `agent_state` variable with the
`pistrategy-state:v1:gzip-base64:` prefix. Only the server-side state is
authoritative; conversations created by the old cc_agent plugin or the sibling
pi_dify plugin cannot be resumed here. If an external write result is unknown,
verify the business result before retrying.
