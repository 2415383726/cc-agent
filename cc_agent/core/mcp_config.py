from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    name: str
    url: str = field(repr=False)
    transport: str = "sse"
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    timeout: float = 50
    sse_read_timeout: float = 50


def parse_mcp_servers(value: Any) -> list[McpServerConfig]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return []
    try:
        payload = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        raise ValueError("mcp_servers_config must be a valid JSON object.") from None
    if not isinstance(payload, dict):
        raise TypeError("mcp_servers_config must be a JSON object.")
    if "mcpServers" in payload:
        payload = payload["mcpServers"]
    if not isinstance(payload, dict):
        raise TypeError("mcpServers must be a JSON object.")
    servers = []
    for name, settings in payload.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise ValueError(
                "MCP server names must contain 1-64 letters, digits, underscores or hyphens."
            )
        if not isinstance(settings, dict):
            raise TypeError(f"MCP server {name}: configuration must be an object.")
        transport = settings.get("transport", "sse")
        if transport not in ("sse", "streamable_http"):
            raise ValueError(f"MCP server {name}: transport must be sse or streamable_http.")
        url = settings.get("url")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            valid_url = parsed and parsed.scheme in ("http", "https") and parsed.hostname
        except ValueError:
            valid_url = False
        if not valid_url or not isinstance(url, str) or "{{" in url:
            raise ValueError(f"MCP server {name}: url must be a resolved HTTP(S) URL.")
        headers = settings.get("headers", {})
        if not isinstance(headers, dict) or any(
            not isinstance(key, str)
            or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)
            or not isinstance(item, str)
            or any(character in item for character in ("\r", "\n", "{{"))
            for key, item in headers.items()
        ):
            raise ValueError(f"MCP server {name}: headers must be resolved single-line strings.")
        servers.append(
            McpServerConfig(
                name=name,
                url=url,
                transport=transport,
                headers=dict(headers),
                timeout=_timeout(settings.get("timeout", 50), name),
                sse_read_timeout=_timeout(settings.get("sse_read_timeout", 50), name),
            )
        )
    return servers


def _timeout(value: Any, server: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"MCP server {server}: timeouts must be positive finite numbers.")
    return float(value)


class McpRedactor:
    """Remove configured credentials when a remote server echoes them back."""

    def __init__(self, servers: list[McpServerConfig]):
        values: set[str] = set()
        for server in servers:
            values.update((server.url, unquote(server.url)))
            parsed = urlsplit(server.url)
            values.update(value for _, value in parse_qsl(parsed.query) if value)
            if parsed.password:
                values.add(unquote(parsed.password))
            for key, value in server.headers.items():
                if re.search(
                    r"(?:^|[-_])(user|employee|tenant|org|organization)[-_]?id$", key, re.IGNORECASE
                ):
                    continue
                if value:
                    values.add(value)
                    if key.lower() in ("authorization", "proxy-authorization") and " " in value:
                        values.add(value.split(" ", 1)[1])
        self._values = sorted((value for value in values if value), key=len, reverse=True)

    def text(self, value: str) -> str:
        for secret in self._values:
            value = value.replace(secret, "[redacted]")
        return value

    def payload(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.payload(item) for item in value]
        if isinstance(value, dict):
            return {self.text(str(key)): self.payload(item) for key, item in value.items()}
        return value
