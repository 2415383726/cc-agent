"""Run blocking Dify session calls off the run's event loop.

The Dify AgentStrategy session is a synchronous stdio client: ``llm.invoke``
and ``tool.invoke`` block until the daemon answers, and a provider stream blocks
again on every ``next()``. Calling them directly on the run loop means a
stalled provider or tool can never be abandoned — the stop watcher, the wall
clock and ``RunStream.close()`` all wait for an await point that never arrives.

Each call (or each whole model stream) therefore runs on a real OS thread and
hands results over through a GIL-atomic deque/flag. The worker signals the loop
with ``call_soon_threadsafe`` so a chunk is delivered as soon as it arrives;
the loop only re-checks stop/timeout every ``WAIT_SECONDS`` while idle. Timeouts
are enforced on the loop side; a timed-out worker is left to finish on its own
because a blocking stdio read cannot be cancelled safely from another thread.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Any

from .threads import start_real_thread, stdlib_original

WAIT_SECONDS = 0.05
TIMEOUT_MESSAGE = "The Dify session call did not respond in time."
ABORT_MESSAGE = "The run stopped while the session call was outstanding."


class SessionAborted(Exception):
    """The run stopped while a blocking session call was outstanding.

    The call may still complete remotely, so callers must treat the outcome as
    unknown rather than as not executed.
    """


class SessionIO:
    """One bridge per run; calls are issued sequentially by the Pi loop."""

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()

    def _notify(self) -> None:
        """Wake the loop from a worker thread without touching asyncio state."""
        try:
            self._loop.call_soon_threadsafe(self._wake.set)
        except RuntimeError:
            # The run loop is already closed, so no waiter remains.
            pass

    async def _wait_notified(self) -> None:
        """Wait for a worker notification, re-checking conditions periodically."""
        try:
            await asyncio.wait_for(self._wake.wait(), WAIT_SECONDS)
        except TimeoutError:
            pass

    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        timeout: float | None = None,
        label: str = "session",
        abort: Callable[[], bool] | None = None,
    ) -> Any:
        box: dict[str, Any] = {"done": False}

        def target() -> None:
            try:
                box["value"] = func(*args)
            except BaseException as exc:  # re-raised on the loop thread
                box["error"] = exc
            finally:
                box["done"] = True
                self._notify()

        start_real_thread(target, name=f"pi-strategy-{label}")
        return await self._await_box(box, timeout, abort)

    async def iterate(
        self,
        iterator: Any,
        *,
        timeout: float | None = None,
        stop_requested: Callable[[], bool] | None = None,
        abort: Callable[[], bool] | None = None,
    ) -> AsyncIterator[Any]:
        """Consume a blocking provider stream without blocking the loop.

        The whole stream is pumped on one thread; chunks are handed over
        through a deque. One-chunk backpressure is preserved: the pump waits
        for the consumer to ask for the next chunk, so a delta is delivered
        before the provider is asked for more. A stop request ends the pump
        between chunks so the provider is abandoned instead of drained.
        """
        sleep = stdlib_original("time", "sleep") or time.sleep
        buffer: deque[Any] = deque()
        state = {"busy": False, "closed": False}
        box: dict[str, Any] = {"done": False}

        def pump() -> None:
            try:
                for chunk in iterator:
                    # Mark busy before publishing the chunk: otherwise the
                    # consumer could take and acknowledge it first, and the pump
                    # would then wait for an acknowledgement that never comes.
                    state["busy"] = True
                    buffer.append(chunk)
                    self._notify()
                    while state["busy"] and not state["closed"]:
                        sleep(0.001)
                    if state["closed"]:
                        break
                    if stop_requested is not None and stop_requested():
                        break
            except BaseException as exc:  # re-raised on the loop thread
                box["error"] = exc
            finally:
                close = getattr(iterator, "close", None)
                if close is not None:
                    try:
                        close()
                    except Exception:
                        pass
                box["done"] = True
                self._notify()

        start_real_thread(pump, name="pi-strategy-stream")
        deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
        try:
            while True:
                # Clear before inspecting shared state: a notification that
                # arrives after this point stays set and wakes the wait below.
                self._wake.clear()
                if buffer:
                    item = buffer.popleft()
                    yield item
                    state["busy"] = False
                    deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
                    continue
                if box["done"]:
                    if "error" in box:
                        raise box["error"]
                    return
                if abort is not None and abort():
                    raise SessionAborted(ABORT_MESSAGE)
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError(TIMEOUT_MESSAGE)
                await self._wait_notified()
        finally:
            # The consumer left early (stop, error or cancellation): release the
            # pump so it stops after the current provider call returns.
            state["closed"] = True
            state["busy"] = False

    async def _await_box(
        self, box: dict[str, Any], timeout: float | None, abort: Callable[[], bool] | None = None
    ) -> Any:
        deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
        while True:
            self._wake.clear()
            if box["done"]:
                break
            if abort is not None and abort():
                raise SessionAborted(ABORT_MESSAGE)
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(TIMEOUT_MESSAGE)
            await self._wait_notified()
        if "error" in box:
            raise box["error"]
        return box.get("value")
