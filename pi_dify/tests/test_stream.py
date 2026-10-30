from __future__ import annotations

import asyncio
import json
import unittest

from _support import FakeModelUse, FakeSession, text_chunks
from pi_agent_core.messages import AssistantMessage, UserMessage
from pi_agent_core.types import LlmContext, StreamOptions

from pi_agent.budget import RunLedger
from pi_agent.config import RuntimeConfig
from pi_agent.stream import DifyModelStream


def build_stream(session: FakeSession, **config: object) -> DifyModelStream:
    runtime = RuntimeConfig.from_value(config)
    return DifyModelStream(
        session=session,
        model_config=FakeModelUse(),
        ledger=RunLedger(runtime, "run"),
        config=runtime,
        model=None,
    )


def consume(
    stream: DifyModelStream, *, signal: object | None = None, system: str = "sys"
) -> tuple[list, AssistantMessage]:
    from pi_agent_core.types import Model

    model = Model(provider="fake", model_id="m")
    context = LlmContext(system_prompt=system, messages=[UserMessage(content="hi")], tools=[])
    collected = []

    async def go():
        event_stream = await stream(model, context, StreamOptions(signal=signal))
        async for event in event_stream:
            collected.append(event)
        return await event_stream.message_result()

    final = asyncio.run(go())
    return collected, final


class StreamModeTests(unittest.TestCase):
    def test_delta_arguments_are_joined_and_executed_once(self) -> None:
        session = FakeSession(
            [
                [
                    {
                        "delta": {
                            "message": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "c1",
                                        "function": {"name": "ec", "arguments": '{"val'},
                                    }
                                ]
                            }
                        }
                    },
                    {
                        "delta": {
                            "message": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"name": "ho", "arguments": 'ue":"x"}'},
                                    }
                                ]
                            }
                        }
                    },
                ]
            ]
        )
        _, final = consume(build_stream(session, tool_stream_mode="delta"))
        calls = [block for block in final.content if block.get("type") == "toolCall"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "echo")
        self.assertEqual(calls[0]["arguments"], {"value": "x"})

    def test_snapshot_arguments_replace_instead_of_append(self) -> None:
        session = FakeSession(
            [
                [
                    {
                        "delta": {
                            "message": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "c1",
                                        "function": {"name": "echo", "arguments": '{"a":1}'},
                                    }
                                ]
                            }
                        }
                    },
                    {
                        "delta": {
                            "message": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "c1",
                                        "function": {"name": "echo", "arguments": '{"b":2}'},
                                    }
                                ]
                            }
                        }
                    },
                ]
            ]
        )
        _, final = consume(build_stream(session, tool_stream_mode="snapshot"))
        calls = [block for block in final.content if block.get("type") == "toolCall"]
        self.assertEqual(calls[0]["arguments"], {"b": 2})

    def test_interleaved_calls_keep_ids(self) -> None:
        session = FakeSession(
            [
                [
                    {
                        "delta": {
                            "message": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "a",
                                        "function": {"name": "first", "arguments": ""},
                                    },
                                    {
                                        "index": 1,
                                        "id": "b",
                                        "function": {"name": "second", "arguments": ""},
                                    },
                                ]
                            }
                        }
                    },
                    {
                        "delta": {
                            "message": {
                                "tool_calls": [
                                    {"index": 1, "function": {"name": "", "arguments": '{"x":1}'}}
                                ]
                            }
                        }
                    },
                ]
            ]
        )
        _, final = consume(build_stream(session))
        calls = [block for block in final.content if block.get("type") == "toolCall"]
        self.assertEqual([call["id"] for call in calls], ["a", "b"])
        self.assertEqual(calls[1]["arguments"], {"x": 1})

    def test_reasoning_field_is_emitted_as_thinking(self) -> None:
        session = FakeSession(
            [[{"delta": {"message": {"reasoning_content": "thinking...", "content": "answer"}}}]]
        )
        events, final = consume(build_stream(session))
        self.assertIn("thinking_delta", [event.type for event in events])
        self.assertEqual(final.content[0]["type"], "thinking")
        self.assertEqual(final.content[1]["text"], "answer")

    def test_bad_json_produces_no_tool_call(self) -> None:
        session = FakeSession(
            [
                [
                    {
                        "delta": {
                            "message": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "c1",
                                        "function": {"name": "echo", "arguments": '{"x":'},
                                    }
                                ]
                            }
                        }
                    }
                ]
            ]
        )
        _, final = consume(build_stream(session))
        self.assertFalse(any(block.get("type") == "toolCall" for block in final.content))
        self.assertIn("Invalid arguments", json.dumps(final.content))

    def test_stream_failure_falls_back_to_nonstream_once(self) -> None:
        session = FakeSession([RuntimeError("bad stream"), {"message": {"content": "fallback ok"}}])
        _, final = consume(build_stream(session, stream_fallback=True))
        self.assertEqual(final.content[0]["text"], "fallback ok")
        self.assertEqual(len(session.model.llm.calls), 2)
        self.assertTrue(session.model.llm.calls[0]["stream"])
        self.assertFalse(session.model.llm.calls[1]["stream"])

    def test_abort_signal_is_cooperative(self) -> None:
        class Signal:
            aborted = True

        session = FakeSession([text_chunks("never")])
        _, final = consume(build_stream(session), signal=Signal())
        self.assertEqual(final.stopReason, "aborted")
        self.assertIn("pi_error:aborted", final.errorMessage)

    def test_dify_content_objects_use_data_field(self) -> None:
        from types import SimpleNamespace

        content = SimpleNamespace(type="text", data="Hello from Dify")
        chunk = SimpleNamespace(
            delta=SimpleNamespace(
                message=SimpleNamespace(content=[content], tool_calls=None, reasoning_content=None),
                usage=None,
            )
        )
        session = FakeSession([[chunk]])
        _, final = consume(build_stream(session))
        self.assertEqual(final.content[0]["text"], "Hello from Dify")

    def test_preflight_rejects_fixed_content_without_model_call(self) -> None:
        session = FakeSession([])
        runtime = RuntimeConfig.from_value({"context_window": 1024, "reserved_output_tokens": 900})
        stream = DifyModelStream(
            session=session,
            model_config=FakeModelUse(),
            ledger=RunLedger(runtime, "run"),
            config=runtime,
            model=None,
        )
        _, final = consume(stream, system="x" * 5_000)
        self.assertEqual(final.stopReason, "error")
        self.assertIn("pi_error:context_", final.errorMessage)


if __name__ == "__main__":
    unittest.main()
