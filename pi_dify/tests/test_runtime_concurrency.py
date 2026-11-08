from __future__ import annotations

import threading
import time
import unittest

from _support import FakeSession, base_parameters

from pi_agent.runtime import RunStream


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

    def test_close_stops_a_pending_run_without_blocking(self) -> None:
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
        from pi_agent.runtime import _start_worker_thread

        _start_worker_thread(stream._target)  # noqa: SLF001
        time.sleep(0.05)
        started = time.monotonic()
        stream.close()
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 5.0)
        self.assertTrue(stream._finished)  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
