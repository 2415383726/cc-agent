---
name: pi-strategy-help
description: Explain how this Pi Strategy plugin requests approval and preserves state. Activate explicitly with /skill:pi-strategy-help.
disable-model-invocation: true
---

# Pi Strategy help

Tool approval is a plain-text interaction. The pending operation is rendered as
text with the tool name and parameters; the user replies with a keyword:
"同意" executes once, "当前会话始终允许" grants the tool for this conversation,
"拒绝" declines. Approval is re-checked against the current tool set, policy
and budget before execution; rejection is reported and the original batch tail
is not replayed.

The Pi session is stored in the Dify `agent_state` variable with the
`pistrategy-state:v1:gzip-base64:` prefix. Only the server-side state is
authoritative; conversations created by the old cc_agent plugin or the sibling
pi_dify plugin cannot be resumed here. If an external write result is unknown,
verify the business result before retrying.
