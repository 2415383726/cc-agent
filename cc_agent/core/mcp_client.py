from __future__ import annotations

import logging
import traceback
from contextlib import AsyncExitStack, ExitStack, asynccontextmanager, contextmanager
from datetime import timedelta
from threading import RLock
from typing import Any, Self

import anyio
import httpx
from anyio.from_thread import BlockingPortal, BlockingPortalProvider
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from .mcp_config import McpRedactor, McpServerConfig

# Dify patches threading with gevent. Reuse the event loop, never sessions or credentials.
_portals = BlockingPortalProvider()
_portal_lock = RLock()


@contextmanager
def _borrow_portal():
    # Serialize the last lease's shutdown with the next lease's startup under gevent.
    with _portal_lock:
        portal = _portals.__enter__()
    try:
        yield portal
    finally:
        with _portal_lock:
            _portals.__exit__(None, None, None)


class SdkMcpSession:
    """Keep SDK async context managers on one task while the agent runs synchronously."""

    def __init__(self, server: McpServerConfig):
        self.server = server
        self._stack = ExitStack()
        self._portal: BlockingPortal | None = None
        self._session: ClientSession | None = None

    def __enter__(self) -> Self:
        try:
            redaction_filter = _CredentialFilter(McpRedactor([self.server]))
            names = {
                "httpx",
                "mcp.client.sse",
                "mcp.client.streamable_http",
                "mcp.shared.session",
                "mcp.client.session",
            }
            names.update(
                name
                for name in list(logging.Logger.manager.loggerDict)
                if name.startswith(("httpcore.", "mcp."))
            )
            for name in names:
                logger = logging.getLogger(name)
                logger.addFilter(redaction_filter)
                self._stack.callback(logger.removeFilter, redaction_filter)
            self._portal = self._stack.enter_context(_borrow_portal())
            self._session = self._stack.enter_context(
                self._portal.wrap_async_context_manager(self._connect())
            )
        except BaseException:
            self._stack.close()
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stack.close()
        self._session = None
        self._portal = None

    @asynccontextmanager
    async def _connect(self):
        async with AsyncExitStack() as stack:
            if self.server.transport == "sse":
                transport = sse_client(
                    self.server.url,
                    headers=self.server.headers,
                    timeout=self.server.timeout,
                    sse_read_timeout=self.server.sse_read_timeout,
                    httpx_client_factory=self._http_client,
                )
            else:
                client = await stack.enter_async_context(
                    self._http_client(
                        headers=self.server.headers,
                        timeout=httpx.Timeout(
                            self.server.timeout, read=self.server.sse_read_timeout
                        ),
                    )
                )
                transport = streamable_http_client(self.server.url, http_client=client)
            streams = await stack.enter_async_context(transport)
            async with ClientSession(
                streams[0], streams[1], read_timeout_seconds=timedelta(seconds=self.server.timeout)
            ) as session:
                with anyio.fail_after(self.server.timeout):
                    await session.initialize()
                yield session

    def _http_client(self, headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
        origin = httpx.URL(self.server.url)

        async def check_origin(request: httpx.Request) -> None:
            target = request.url
            if (target.scheme, target.host, target.port) != (
                origin.scheme,
                origin.host,
                origin.port,
            ):
                raise ValueError(
                    "MCP redirects and SSE endpoints must stay on the configured origin."
                )

        return httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=True,
            event_hooks={"request": [check_origin]},
        )

    def list_tools(self, cursor: str | None = None) -> dict[str, Any]:
        assert self._portal is not None and self._session is not None
        result = self._portal.call(self._session.list_tools, cursor)
        return result.model_dump(by_alias=True, exclude_none=True)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self._portal is not None and self._session is not None
        result = self._portal.call(
            self._session.call_tool, name, arguments, timedelta(seconds=self.server.timeout)
        )
        return result.model_dump(by_alias=True, exclude_none=True)


class _CredentialFilter(logging.Filter):
    def __init__(self, redactor: McpRedactor):
        super().__init__()
        self.redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + "".join(traceback.format_exception(*record.exc_info))
        record.msg = self.redactor.text(message)
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True
