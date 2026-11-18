from __future__ import annotations

import threading
import time
import unittest

from _support import FakeSession, base_parameters

from pi_strategy.runtime import RunStream


class _SlowRuntime:
    """Fake runtime: each run emits its own tag before and after an await."""

    async def execute_async(self, parameters, emit, stop, *, run_id: str = "") -> None:
        emit({"type": "text", "content": f"start:{parameters['tag']}"})
        # A real await yields the loop, which is what made concurrent runs share
        # asyncio's running-loop state under the host's gevent patch.
        for _ in range(10):
            await _sleep(0.01)
        emit({"type": "text", "content": f"end:{parameters['tag']}"})


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def _drain(stream: RunStream) -> list[str]:
    return [item["content"] for item in stream if isinstance(item, dict)]


class ConcurrentRunStreamTests(unittest.TestCase):
    def test_two_runs_overlap_and_keep_their_own_items(self) -> None:
        first = RunStream(_SlowRuntime(), {"tag": "a"})  # type: ignore[arg-type]
        second = RunStream(_SlowRuntime(), {"tag": "b"})  # type: ignore[arg-type]
        first_items = _drain(first)
        second_items = _drain(second)
        self.assertEqual(first_items, ["start:a", "end:a"])
        self.assertEqual(second_items, ["start:b", "end:b"])

    def test_runs_started_before_the_first_finishes_both_complete(self) -> None:
        """The reported bug: a second turn while the first was still streaming."""

        slow = RunStream(_SlowRuntime(), {"tag": "slow"})  # type: ignore[arg-type]
        fast = RunStream(_SlowRuntime(), {"tag": "fast"})  # type: ignore[arg-type]
        results: dict[str, list[str]] = {}

        def consume(name: str, stream: RunStream) -> None:
            results[name] = _drain(stream)

        slow_thread = threading.Thread(target=consume, args=("slow", slow))
        fast_thread = threading.Thread(target=consume, args=("fast", fast))
        slow_thread.start()
        time.sleep(0.02)
        fast_thread.start()
        slow_thread.join(10)
        fast_thread.join(10)
        self.assertEqual(results.get("slow"), ["start:slow", "end:slow"])
        self.assertEqual(results.get("fast"), ["start:fast", "end:fast"])

    def test_close_stops_an_inflight_run_without_blocking(self) -> None:
        session = FakeSession([base_parameters(query="hi")])
        self.assertIsNotNone(session)

        class _BlockingRuntime:
            def __init__(self) -> None:
                self.released = threading.Event()

            async def execute_async(self, parameters, emit, stop, *, run_id: str = "") -> None:
                while not stop.is_set():
                    await _sleep(0.01)
                emit({"type": "text", "content": "stopped"})

        stream = RunStream(_BlockingRuntime(), {})  # type: ignore[arg-type]
        stream._started = True  # noqa: SLF001 - start the worker without iterating
        from pi_strategy.runtime import _start_worker_thread

        _start_worker_thread(stream._target)  # noqa: SLF001
        time.sleep(0.05)
        started = time.monotonic()
        stream.close()
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 5.0)
        self.assertTrue(stream._finished)  # noqa: SLF001


class HostStopCancellationTests(unittest.TestCase):
    """A host stop cancels the running task (live-verified on Dify): the run
    must still finalize as ``stopped`` with state saved, not crash through the
    BaseException path with ``agent_failed`` and no state."""

    def test_cancelled_run_finalizes_as_stopped_with_state(self) -> None:
        import asyncio

        from _support import base_parameters, json_payloads, last_state

        from pi_strategy.runtime import PiStrategyRuntime
        from pi_strategy.state import decode_state

        session = FakeSession([base_parameters(query="hi")])
        self.assertIsNotNone(session)
        outbox: list[dict] = []
        runtime = PiStrategyRuntime(session)
        cancelled = threading.Event()

        async def scenario() -> None:
            task = asyncio.current_task()
            if task is None:  # pragma: no cover - a task always exists here
                raise RuntimeError("no current task")

            def emit_and_cancel(item: dict) -> None:
                outbox.append(item)
                if (
                    not cancelled.is_set()
                    and item.get("type") == "log"
                    and item.get("label") == "Run started"
                ):
                    cancelled.set()
                    task.cancel()

            await runtime.execute_async(
                base_parameters(query="hi"), emit_and_cancel, threading.Event()
            )

        asyncio.run(scenario())
        self.assertTrue(cancelled.is_set())
        payloads = json_payloads(outbox)
        self.assertTrue(payloads)
        self.assertEqual(payloads[-1]["status"], "stopped")
        # The stop is not reported as a failure and state is saved.
        failed = [item for item in outbox if item.get("type") == "log" and item.get("is_error")]
        self.assertEqual(failed, [])
        saved = last_state(outbox)
        self.assertTrue(saved.startswith("pistrategy-state:v1:gzip-base64:"))
        loaded = decode_state(saved)
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.state.last_status, "stopped")


class RunIdentityTests(unittest.TestCase):
    def test_run_stream_id_is_the_reported_run_id(self) -> None:
        from _support import base_parameters, text_chunks

        from pi_strategy.runtime import PiStrategyRuntime

        session = FakeSession([text_chunks("hi")])
        stream = RunStream(PiStrategyRuntime(session), base_parameters())
        outbox = [item for item in stream]
        payloads = [item["payload"] for item in outbox if item.get("type") == "json"]
        self.assertTrue(stream.run_id.startswith("run_"))
        self.assertEqual(payloads[-1]["stats"]["run_id"], stream.run_id)


class BlockedSessionCallTests(unittest.TestCase):
    """A blocked Dify session call must not pin the run.

    The tool/llm invocations are synchronous stdio round-trips bridged through
    SessionIO; a stop abandons the call, finalizes as ``stopped`` and still
    saves state instead of hanging until the tool timeout.
    """

    def test_stop_abandons_a_blocked_tool_call(self) -> None:
        from _support import base_parameters, last_state, last_terminal, run_turn, tool_chunks

        from pi_strategy.state import decode_state
        from pi_strategy.threads import stdlib_original

        allocate = stdlib_original("_thread", "allocate_lock")
        gate = allocate() if allocate is not None else threading.Lock()
        gate.acquire()

        class BlockingTool:
            def invoke(self, **_kwargs):
                gate.acquire()
                return [{"type": "text", "message": "late"}]

        session = FakeSession([tool_chunks([{"name": "write"}])])
        session.tool = BlockingTool()
        stop = threading.Event()
        timer = threading.Timer(0.2, stop.set)
        timer.start()
        started = time.monotonic()
        try:
            outbox = run_turn(
                session,
                base_parameters(
                    query="write",
                    tools=[{"name": "write", "parameters": {"type": "object", "properties": {}}}],
                    runtime={"max_model_requests": 2, "tool_timeout_seconds": 60},
                ),
                stop=stop,
            )
        finally:
            gate.release()
            timer.cancel()
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(last_terminal(outbox)["status"], "stopped")
        self.assertNotIn("late", str(outbox))
        loaded = decode_state(last_state(outbox))
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.state.last_status, "stopped")


if __name__ == "__main__":
    unittest.main()
