"""Per-run remote MCP connections: current identity, bounded tools, full cleanup."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from .config import RuntimeConfig
from .errors import PiError

try:  # pragma: no cover - remote MCP transport is a runtime dependency
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamable_http_client
except Exception:  # pragma: no cover
    ClientSession = None
    sse_client = None
    streamable_http_client = None


@dataclass(slots=True)
class McpServer:
    name: str
    url: str
    transport: str = "sse"
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    timeout: float = 50.0
    sse_read_timeout: float = 50.0


@dataclass(slots=True)
class McpTool:
    server: str
    name: str
    exposed_name: str
    description: str
    parameters: dict[str, Any]
    annotations: dict[str, Any] = field(default_factory=dict)


class McpRuntime:
    """One runtime per Dify request. Connections never cross runs."""

    def __init__(self, servers: list[McpServer], config: RuntimeConfig):
        self.servers = servers
        self.config = config
        self._stack = AsyncExitStack()
        self._sessions: dict[str, Any] = {}
        self._tools: dict[str, McpTool] = {}
        self._opened = False

    async def open(self) -> None:
        if self._opened or not self.servers:
            return
        if ClientSession is None:
            raise PiError(
                code="invalid_configuration",
                stage="mcp",
                message="Remote MCP support is unavailable in this installation.",
            )
        self._opened = True
        for server in self.servers:
            await self._connect(server)

    async def _connect(self, server: McpServer) -> None:
        if server.transport == "sse":
            read, write = await self._stack.enter_async_context(
                sse_client(
                    server.url,
                    headers=server.headers,
                    timeout=server.timeout,
                    sse_read_timeout=server.sse_read_timeout,
                )
            )
        else:
            read, write, _get_session_id = await self._stack.enter_async_context(
                streamable_http_client(
                    server.url,
                    headers=server.headers,
                    timeout=server.timeout,
                    sse_read_timeout=server.sse_read_timeout,
                )
            )
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=server.timeout)
        self._sessions[server.name] = session
        listing = await asyncio.wait_for(session.list_tools(), timeout=server.timeout)
        for tool in getattr(listing, "tools", []) or []:
            name = str(getattr(tool, "name", "") or "")
            if not name or _is_app_only(tool):
                continue
            if name in getattr(self.config, "mcp_tools_exclude", ()):
                continue
            annotations = getattr(tool, "annotations", None)
            hint_payload = (
                annotations.model_dump(exclude_none=True)
                if hasattr(annotations, "model_dump")
                else dict(annotations or {})
            )
            exposed = name
            if exposed in self._tools:
                exposed = f"mcp__{_sanitize(server.name)}__{name}"
            self._tools[exposed] = McpTool(
                server=server.name,
                name=name,
                exposed_name=exposed,
                description=str(getattr(tool, "description", "") or ""),
                parameters=getattr(tool, "inputSchema", None)
                or {"type": "object", "properties": {}},
                annotations=hint_payload,
            )

    def tools(self) -> list[McpTool]:
        return list(self._tools.values())

    def has(self, exposed_name: str) -> bool:
        return exposed_name in self._tools

    async def call(self, exposed_name: str, arguments: dict[str, Any]) -> Any:
        tool = self._tools.get(exposed_name)
        if tool is None:
            raise PiError(
                code="tool_unknown", stage="mcp", message="The MCP tool is not available."
            )
        await self.open()
        session = self._sessions.get(tool.server)
        if session is None:
            raise PiError(
                code="tool_failed", stage="mcp", message="The MCP connection is unavailable."
            )
        try:
            return await asyncio.wait_for(
                session.call_tool(tool.name, arguments or {}), timeout=self.config.mcp_tool_timeout
            )
        except TimeoutError:
            raise PiError(
                code="unknown_outcome",
                stage="mcp",
                message="The remote tool did not respond; its execution outcome is unknown.",
                details={"execution_outcome": "unknown"},
            ) from None
        except Exception:
            raise PiError(
                code="unknown_outcome",
                stage="mcp",
                message="The remote tool failed; verify the external outcome before retrying.",
                details={"execution_outcome": "unknown"},
            ) from None

    async def close(self) -> None:
        self._sessions.clear()
        self._tools = {}
        try:
            await self._stack.aclose()
        except Exception:
            # Cleanup failure never overrides the primary business result.
            pass


def parse_servers(value: Any) -> list[McpServer]:
    """Parse Dify-resolved MCP JSON without accepting unresolved variables or stdio."""

    import json
    import re
    from urllib.parse import urlsplit

    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            raise PiError(
                code="invalid_configuration",
                stage="mcp",
                message="mcp_servers_config must be valid JSON.",
            ) from None
    else:
        payload = value
    if isinstance(payload, dict):
        payload = payload.get("mcpServers", payload)
    if not isinstance(payload, dict):
        raise PiError(
            code="invalid_configuration", stage="mcp", message="MCP servers must be an object."
        )
    servers: list[McpServer] = []
    for name, settings in payload.items():
        if not isinstance(settings, dict):
            raise PiError(
                code="invalid_configuration",
                stage="mcp",
                message="Each MCP server must be an object.",
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(name)):
            raise PiError(
                code="invalid_configuration", stage="mcp", message="Invalid MCP server name."
            )
        transport = str(settings.get("transport") or "sse").strip().lower()
        if transport not in {"sse", "streamable_http", "streamable-http"}:
            raise PiError(
                code="invalid_configuration",
                stage="mcp",
                message="Only remote sse and streamable_http MCP transports are supported.",
            )
        url = str(settings.get("url") or "")
        parsed = urlsplit(url) if url else None
        if (
            not parsed
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or "{{" in url
        ):
            raise PiError(
                code="invalid_configuration",
                stage="mcp",
                message="MCP server URL must be resolved HTTP(S).",
            )
        headers = settings.get("headers") or {}
        if not isinstance(headers, dict):
            raise PiError(
                code="invalid_configuration", stage="mcp", message="MCP headers must be an object."
            )
        for key, item in headers.items():
            if (
                not isinstance(key, str)
                or not isinstance(item, str)
                or any(char in item for char in ("\r", "\n", "{{"))
            ):
                raise PiError(
                    code="invalid_configuration",
                    stage="mcp",
                    message="MCP headers must be resolved single-line strings.",
                )
        servers.append(
            McpServer(
                name=str(name),
                url=url,
                transport="streamable_http" if transport.startswith("streamable") else "sse",
                headers={str(key): str(item) for key, item in headers.items()},
                timeout=_positive(settings.get("timeout"), 50.0),
                sse_read_timeout=_positive(settings.get("sse_read_timeout"), 50.0),
            )
        )
    return servers


def _positive(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _is_app_only(tool: Any) -> bool:
    name = str(getattr(tool, "name", "") or "")
    if name.startswith(("app__", "app:")):
        return True
    meta = getattr(tool, "meta", None) or getattr(tool, "_meta", None)
    if isinstance(meta, dict):
        return bool(meta.get("appOnly") or meta.get("app_only"))
    return False


def _sanitize(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "mcp"


def redact_servers(servers: list[McpServer]) -> list[dict[str, Any]]:
    return [{"name": server.name, "transport": server.transport} for server in servers]
