"""Real OS threads behind the host's gevent monkey patch.

The Dify plugin host calls ``gevent.monkey.patch_all()`` before loading the
plugin, so ``threading.Thread`` no longer starts an OS thread. Everything that
must genuinely run off the hub (the per-run asyncio loop and the blocking Dify
session calls) therefore uses the stdlib ``_thread`` implementation that the
patch saved.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


def stdlib_original(module_name: str, attribute: str) -> Any:
    try:
        from gevent import monkey  # type: ignore[import-not-found]
    except Exception:
        return None
    saved = getattr(monkey, "saved", None)
    if not isinstance(saved, dict):
        return None
    return saved.get(module_name, {}).get(attribute)


def start_real_thread(target: Callable[[], None], name: str = "pi-strategy-thread") -> None:
    """Start ``target`` on a genuine OS thread, never a greenlet."""
    start = stdlib_original("_thread", "start_new_thread")
    if start is None:
        threading.Thread(target=target, name=name, daemon=True).start()
        return
    start(target, ())
