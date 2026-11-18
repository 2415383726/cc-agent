"""Direct contract tests for the blocking-call bridge."""

from __future__ import annotations

import asyncio
import threading
import time
import unittest

from _support import ROOT  # noqa: F401 - ensures the package root is on sys.path

from pi_strategy.session_io import SessionAborted, SessionIO
from pi_strategy.threads import stdlib_original

SLEEP = stdlib_original("time", "sleep") or time.sleep


class SessionIOTests(unittest.TestCase):
    def test_call_returns_value_and_reraises(self) -> None:
        async def scenario() -> None:
            io = SessionIO()
            self.assertEqual(await io.call(lambda: 42, timeout=1.0), 42)

            def boom() -> None:
                raise ValueError("boom")

            with self.assertRaises(ValueError):
                await io.call(boom, timeout=1.0)

        asyncio.run(scenario())

    def test_iterate_preserves_order(self) -> None:
        async def scenario() -> None:
            io = SessionIO()
            seen = []
            async for chunk in io.iterate(iter([1, 2, 3]), timeout=1.0):
                seen.append(chunk)
            self.assertEqual(seen, [1, 2, 3])

        asyncio.run(scenario())

    def test_many_chunks_complete_without_stalling(self) -> None:
        """A fast provider must not be throttled by the handover loop.

        The old 10ms polling path needed ~5s for 500 chunks; notification-driven
        handover keeps this well under a second and would deadlock if the
        busy/append ordering regressed.
        """

        async def scenario() -> None:
            io = SessionIO()
            started = time.monotonic()
            seen = []
            async for chunk in io.iterate(iter(range(500)), timeout=5.0):
                seen.append(chunk)
            self.assertEqual(seen, list(range(500)))
            self.assertLess(time.monotonic() - started, 3.0)

        asyncio.run(scenario())

    def test_iterate_aborts_promptly_while_the_provider_blocks(self) -> None:
        def slow():
            yield 1
            SLEEP(2.0)
            yield 2

        async def scenario() -> None:
            io = SessionIO()
            stop = threading.Event()
            started = time.monotonic()
            with self.assertRaises(SessionAborted):
                async for chunk in io.iterate(slow(), abort=stop.is_set):
                    self.assertEqual(chunk, 1)
                    stop.set()
            self.assertLess(time.monotonic() - started, 1.0)

        asyncio.run(scenario())

    def test_iterate_stop_request_ends_the_pump_between_chunks(self) -> None:
        def many():
            for index in range(100):
                yield index

        async def scenario() -> None:
            io = SessionIO()
            stop = threading.Event()
            seen = []
            async for chunk in io.iterate(many(), stop_requested=stop.is_set):
                seen.append(chunk)
                if chunk == 2:
                    stop.set()
            self.assertEqual(seen, [0, 1, 2])

        asyncio.run(scenario())

    def test_call_times_out(self) -> None:
        def slow() -> int:
            SLEEP(1.0)
            return 1

        async def scenario() -> None:
            io = SessionIO()
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                await io.call(slow, timeout=0.1)
            self.assertLess(time.monotonic() - started, 1.0)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
