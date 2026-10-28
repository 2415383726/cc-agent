"""Read-only, synthetic architecture probes; no network or production services."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.loop import AgentLoop
from cc_agent.core.messages import AgentRunResult, AgentState, AssistantTurn, ToolCall, ToolResult
from cc_agent.core.model_adapter import StreamToolCallAccumulator
from cc_agent.core.state_backend import DifyStateBackend
from cc_agent.core.tool_adapter import ToolAdapter
from cc_agent.core.tool_catalog import ToolCatalog
from cc_agent.core.tool_scheduler import SerialToolScheduler, ScheduledToolResult


def show(name, result):
    print(json.dumps({"probe": name, "observed": result}, ensure_ascii=False))


config = AgentRunConfig.from_parameters(
    {"query": "probe", "tool_confirmation_list": ["write"]}
)
show("removed_public_policy_configuration", config.tool_confirmation_list)

acc = StreamToolCallAccumulator()
acc.add_delta(
    [{"index": 0, "id": "call1", "function": {"name": "echo", "arguments": '{"text":'}}]
)
acc.add_delta([{"index": 0, "function": {"arguments": '"hello"}'}}])
show("id_present_only_on_first_chunk", [call.to_history() for call in acc.finalize()])

acc = StreamToolCallAccumulator()
for index, part in enumerate(['{"value":', "1", "1", "}"]):
    acc.add_delta(
        [{"index": 0, "id": "call2", "function": {"name": "echo" if index == 0 else "", "arguments": part}}]
    )
show("repeated_incremental_digit_expected_11", [call.arguments for call in acc.finalize()])

backend = DifyStateBackend(AgentRunConfig(), "probe")
refs = []
for answer in ["A", "B"]:
    result = AgentRunResult(answer=answer, history=[], tasks=[], execution_metadata={})
    backend.commit(result, previous_revision=7)
    refs.append({key: result.state_ref.get(key) for key in ["revision", "persisted"]})
show("two_encodes_with_same_previous_revision", refs)

order = []


class FakeTools:
    def execute(self, call):
        order.append("execute:" + call.id)
        return ToolResult(call.id, call.name, "ok")


for item in SerialToolScheduler(FakeTools()).iter_execute(
    [ToolCall("a", "one"), ToolCall("b", "two")], 1
):
    if isinstance(item, ScheduledToolResult):
        order.append("consume:" + item.tool_call.id)
show("batch_delivery_order", order)

marker = "UNIQUE_WORKFLOW_RULE_482"
state = AgentState(skills=[{"name": "workflow", "kind": "prompt", "body": marker}])
catalog = ToolCatalog.create()


class FakeModel:
    def __init__(self):
        self.calls = []

    def invoke(self, messages, tools, force_final=False):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return AssistantTurn(tool_calls=[ToolCall("load", "Skill", {"name": "workflow"})])
        return AssistantTurn(text="done")


model = FakeModel()
loop = AgentLoop(
    AgentRunConfig(query="do workflow"), state, catalog, model, ToolAdapter(catalog, state)
)
list(loop.run())
show(
    "skill_body_in_second_model_request",
    {
        "copies": sum(str(message.get("content", "")).count(marker) for message in model.calls[1]),
        "roles": [
            message["role"]
            for message in model.calls[1]
            if marker in str(message.get("content", ""))
        ],
    },
)
