"""Tool-result normalization and one-time artifact delivery descriptors."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


@dataclass(slots=True)
class Artifact:
    id: str
    name: str
    mime_type: str = "application/octet-stream"
    kind: str = "file"
    data: bytes | None = None
    url: str = ""
    size: int = 0
    source: str = ""

    def public(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "name": self.name,
            "mime_type": self.mime_type,
            "kind": self.kind,
            "size": self.size or (len(self.data) if self.data else 0),
            "source": self.source,
        }
        if self.url:
            payload["url"] = self.url
        return payload


@dataclass(slots=True)
class NormalizedResult:
    text: str
    artifacts: list[Artifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_dify_responses(responses: Any) -> NormalizedResult:
    """Merge Dify tool responses and de-duplicate repeated halves / JSON copies."""

    parts: list[str] = []
    artifacts: list[Artifact] = []
    metadata: dict[str, Any] = {}
    for response in responses or []:
        kind = _type_name(_get(response, "type"))
        message = _get(response, "message", response)
        if kind in {"text", "textmessage"}:
            parts.append(_message_text(message))
        elif kind == "json":
            parts.append(
                json.dumps(_get(message, "json_object", message), ensure_ascii=False, default=str)
            )
        elif kind == "link":
            parts.append(f"result link: {_message_text(message)}")
            artifacts.append(
                Artifact(
                    id=f"dify_link_{len(artifacts)}",
                    name=_message_text(message)[:200] or "link",
                    kind="link",
                    url=_message_text(message),
                    source="dify",
                )
            )
        elif kind in {"image", "image_link"}:
            parts.append(f"Image output generated: {_message_text(message)}")
            artifacts.append(
                Artifact(
                    id=f"dify_image_{len(artifacts)}",
                    name="image",
                    mime_type="image/*",
                    kind="image",
                    url=_message_text(message),
                    source="dify",
                )
            )
        elif kind in {"blob", "blob_chunk", "file"}:
            parts.append("File output generated.")
            artifacts.append(
                Artifact(
                    id=f"dify_file_{len(artifacts)}",
                    name=_blob_name(message),
                    mime_type=_blob_mime(message),
                    kind="file",
                    size=_blob_size(message),
                    source="dify",
                )
            )
        elif kind == "variable":
            metadata.setdefault("variables", []).append(
                _get(message, "variable_name") or _message_text(message)
            )
            parts.append(f"Variable output: {_stringify(message)}")
        elif kind == "retriever_resources":
            text = _format_retriever_resources(message)
            if text:
                parts.append(text)
        elif kind == "log":
            continue
        else:
            text = _stringify(message)
            if text:
                parts.append(text)
    return NormalizedResult(
        text="\n".join(_dedup(parts)).strip() or "(tool completed with no output)",
        artifacts=artifacts,
        metadata=metadata,
    )


def normalize_mcp_result(result: Any) -> NormalizedResult:
    parts: list[str] = []
    artifacts: list[Artifact] = []
    structured = _get(result, "structuredContent") or _get(result, "structured_content")
    for item in _get(result, "content") or []:
        kind = _get(item, "type")
        if kind == "text":
            parts.append(str(_get(item, "text") or ""))
        elif kind == "image":
            data = _get(item, "data")
            mime = str(_get(item, "mimeType") or _get(item, "mime_type") or "image/png")
            raw = _decode_base64(data)
            artifacts.append(
                Artifact(
                    id=f"mcp_image_{len(artifacts)}",
                    name=f"image-{len(artifacts) + 1}",
                    mime_type=mime,
                    kind="image",
                    data=raw,
                    size=len(raw) if raw else 0,
                    source="mcp",
                )
            )
            parts.append("Image output generated.")
        elif kind in {"resource", "embedded_resource"}:
            resource = _get(item, "resource", item)
            uri = str(_get(resource, "uri") or "")
            mime = str(_get(resource, "mimeType") or _get(resource, "mime_type") or "text/plain")
            text = _get(resource, "text")
            blob = _get(resource, "blob")
            if text is not None and str(mime).startswith("text/"):
                parts.append(str(text))
            elif blob is not None:
                raw = _decode_base64(blob)
                name = uri.rsplit("/", 1)[-1] or f"resource-{len(artifacts) + 1}"
                artifacts.append(
                    Artifact(
                        id=f"mcp_file_{len(artifacts)}",
                        name=name,
                        mime_type=mime,
                        kind="file",
                        data=raw,
                        size=len(raw) if raw else 0,
                        source="mcp",
                    )
                )
                parts.append(f"File output generated: {name}")
            elif uri:
                parts.append(f"Resource link: {uri}")
        elif kind in {"resource_link", "resourceLink"}:
            uri = str(_get(item, "uri") or "")
            parts.append(f"Resource link: {uri}")
        else:
            text = _stringify(item)
            if text:
                parts.append(text)
    if structured is not None and not parts:
        parts.append(json.dumps(structured, ensure_ascii=False, default=str))
    return NormalizedResult(
        text="\n".join(_dedup(parts)).strip() or "(tool completed with no output)",
        artifacts=artifacts,
        metadata={"structured": structured is not None},
    )


def _dedup(parts: list[str]) -> list[str]:
    parts = [part for part in parts if part]
    if len(parts) >= 2 and len(parts) % 2 == 0:
        midpoint = len(parts) // 2
        if [_fingerprint(part) for part in parts[:midpoint]] == [
            _fingerprint(part) for part in parts[midpoint:]
        ]:
            parts = parts[:midpoint]
    result: list[str] = []
    last = ""
    for part in parts:
        fingerprint = _fingerprint(part)
        if result and fingerprint == last:
            continue
        result.append(part)
        last = fingerprint
    return result


def _fingerprint(part: str) -> str:
    stripped = part.strip()
    if not stripped or stripped[0] not in "[{":
        return part
    try:
        parsed = json.loads(stripped)
    except (TypeError, ValueError):
        return part
    return "json:" + json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_base64(value: Any) -> bytes | None:
    if not value:
        return None
    import base64

    try:
        raw = base64.b64decode(str(value), validate=True)
    except Exception:
        return None
    return raw if len(raw) <= MAX_ARTIFACT_BYTES else None


def _format_retriever_resources(message: Any) -> str:
    items = _get(message, "retriever_resources") or _get(message, "resources") or message
    if not isinstance(items, list):
        items = [items]
    lines = []
    for index, item in enumerate(items[:20], start=1):
        title = _get(item, "title") or _get(item, "document_name") or ""
        source = _get(item, "source") or _get(item, "url") or ""
        content = _get(item, "content") or _get(item, "text") or ""
        parts = [
            part
            for part in (
                f"title={title}" if title else "",
                f"source={source}" if source else "",
                str(content)[:500] if content else "",
            )
            if part
        ]
        lines.append(f"{index}. " + "; ".join(parts))
    return "Retrieved resources:\n" + "\n".join(lines) if lines else ""


def _blob_name(message: Any) -> str:
    return str(
        _get(message, "filename")
        or _get(message, "name")
        or _get(message, "output_filename")
        or "generated_file"
    )


def _blob_mime(message: Any) -> str:
    return str(
        _get(message, "mime_type") or _get(message, "mime_type") or "application/octet-stream"
    )


def _blob_size(message: Any) -> int:
    value = _get(message, "size")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _message_text(message: Any) -> str:
    return str(_get(message, "text", message) or "")


def _stringify(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return json.dumps(message, ensure_ascii=False, default=str)
    if hasattr(message, "model_dump"):
        return json.dumps(message.model_dump(mode="json"), ensure_ascii=False, default=str)
    return str(message or "")


def _type_name(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw).split(".")[-1].lower()


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
