from __future__ import annotations

import base64
import copy
import hashlib
import json
import logging
import mimetypes
import re
from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from typing import Any, Protocol, Self

from .mcp_config import McpRedactor, McpServerConfig
from .messages import ToolCall, ToolResult
from .tool_registry import ToolSpec


class McpSession(Protocol):
    def list_tools(self, cursor: str | None = None) -> dict[str, Any]: ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


SessionFactory = Callable[[McpServerConfig], AbstractContextManager[McpSession]]
logger = logging.getLogger(__name__)


class McpToolProvider:
    """Own one run's remote connections and model-visible tool routing."""

    def __init__(
        self, servers: list[McpServerConfig], session_factory: SessionFactory | None = None
    ):
        self.servers = servers
        self._session_factory = session_factory or _sdk_session
        self._stack = ExitStack()
        self._sessions: dict[str, McpSession] = {}
        self._specs: list[ToolSpec] = []
        self._redactor = McpRedactor(servers)

    def __enter__(self) -> Self:
        for server in self.servers:
            try:
                session = self._stack.enter_context(self._session_factory(server))
                self._sessions[server.name] = session
                self._discover(server, session)
            except Exception:  # noqa: BLE001 - SDK errors must not expose credentials.
                self.close()
                raise ValueError(f"MCP initialization failed for server {server.name}.") from None
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._stack.close()
        except Exception as exc:  # noqa: BLE001 - cleanup must attempt every connection.
            logger.warning("MCP cleanup failed (%s).", type(exc).__name__)
        finally:
            self._sessions.clear()
            self._specs.clear()

    def tool_specs(self) -> list[ToolSpec]:
        return list(self._specs)

    def _discover(self, server: McpServerConfig, session: McpSession) -> None:
        cursor = None
        cursors: set[str] = set()
        names: set[str] = set()
        while True:
            page = session.list_tools(cursor)
            for tool in page.get("tools", []):
                original = tool["name"]
                if not isinstance(original, str) or not original or original in names:
                    raise ValueError("MCP returned an invalid or duplicate tool name.")
                names.add(original)
                if not _is_plain_model_tool(tool):
                    continue
                exposed = _tool_name(server.name, self._redactor.text(original))
                self._specs.append(
                    ToolSpec(
                        name=exposed,
                        kind="mcp",
                        original_name=original,
                        entity=server.name,
                        prompt_tool={
                            "name": exposed,
                            "description": self._redactor.text(str(tool.get("description") or "")),
                            "parameters": self._redactor.payload(
                                copy.deepcopy(
                                    tool.get("inputSchema") or {"type": "object", "properties": {}}
                                )
                            ),
                        },
                    )
                )
            cursor = page.get("nextCursor")
            if not cursor:
                return
            if not isinstance(cursor, str) or cursor in cursors:
                raise ValueError("MCP returned an invalid pagination cursor.")
            cursors.add(cursor)

    def execute(self, spec: ToolSpec, tool_call: ToolCall) -> ToolResult:
        try:
            result = self._sessions[str(spec.entity)].call_tool(
                spec.original_name, tool_call.arguments
            )
            # Decode media before redacting text: secrets may coincide with base64 substrings.
            parts, display = _content_parts(result.get("content", []))
            parts = [self._redactor.text(part) for part in parts]
            for message in display:
                message["meta"] = self._redactor.payload(message["meta"])
            output = self._redactor.payload(result.get("structuredContent"))
            if output is not None:
                encoded = json.dumps(output, ensure_ascii=False)
                if encoded not in parts:
                    parts.append(encoded)
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                llm_observation="\n".join(parts) or "(tool completed with no output)",
                is_error=bool(result.get("isError")),
                metadata={"output": output} if output is not None else {},
                display_messages=display,
            )
        except Exception:  # noqa: BLE001 - always pair failed calls with a safe tool result.
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                llm_observation="MCP tool invocation failed.",
                is_error=True,
                synthetic=True,
            )


def _is_plain_model_tool(tool: dict[str, Any]) -> bool:
    meta = tool.get("_meta", {})
    if not isinstance(meta, dict):
        return False
    ui = meta.get("ui", {})
    if not isinstance(ui, dict):
        return False
    if "resourceUri" in ui or "ui/resourceUri" in meta or "openai/outputTemplate" in meta:
        return False
    if "visibility" not in ui:
        return True
    visibility = ui["visibility"]
    return isinstance(visibility, list) and "model" in visibility


def _tool_name(server: str, original: str) -> str:
    raw = f"mcp__{server}__{original}"
    normalized = re.sub(r"[^A-Za-z0-9_-]", "_", raw)
    if len(raw) <= 64 and normalized == raw and "__" not in server and "__" not in original:
        return raw
    digest = hashlib.sha256(json.dumps([server, original]).encode()).hexdigest()[:12]
    return f"{normalized[:50]}__{digest}"


def _sdk_session(server: McpServerConfig) -> AbstractContextManager[McpSession]:
    from .mcp_client import SdkMcpSession

    return SdkMcpSession(server)


def _content_parts(content: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    parts: list[str] = []
    display: list[dict[str, Any]] = []
    for item in content:
        kind = item.get("type")
        if kind == "text":
            parts.append(str(item.get("text") or ""))
        elif kind == "resource_link":
            parts.append(f"Result link: {item.get('uri', '')}")
        else:
            resource = item.get("resource", {}) if kind == "resource" else item
            if "text" in resource:
                parts.append(str(resource["text"]))
                continue
            data = resource.get("blob") if kind == "resource" else resource.get("data")
            if not isinstance(data, str) or len(data) > 28_000_000:
                raise ValueError("Unsupported or oversized MCP content.")
            blob = base64.b64decode(data, validate=True)
            mime_type = str(resource.get("mimeType") or "application/octet-stream")
            extension = mimetypes.guess_extension(mime_type) or ".bin"
            display.append(
                {
                    "type": "dify_blob",
                    "blob": blob,
                    "meta": {
                        "mime_type": mime_type,
                        "filename": f"mcp-output-{len(display) + 1}{extension}",
                    },
                }
            )
            parts.append("File output generated.")
    return parts, display
