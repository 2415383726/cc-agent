from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {
    ".csv",
    ".html",
    ".json",
    ".log",
    ".md",
    ".markdown",
    ".text",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_MIME_PREFIXES = {"text/"}
TEXT_MIME_TYPES = {
    "application/csv",
    "application/json",
    "application/ld+json",
    "application/x-ndjson",
    "application/xml",
    "application/yaml",
}


def is_text_file(path: str | Path, mime_type: str = "") -> bool:
    suffix = Path(path).suffix.lower()
    mime = str(mime_type or "").lower()
    return suffix in TEXT_SUFFIXES or mime in TEXT_MIME_TYPES or any(mime.startswith(prefix) for prefix in TEXT_MIME_PREFIXES)


def inspect_materialized_file(path: str | Path, mime_type: str = "", max_chars: int = 6000) -> dict[str, Any]:
    file_path = Path(path)
    if not is_text_file(file_path, mime_type):
        return {
            "kind": "binary",
            "size": file_path.stat().st_size if file_path.exists() else 0,
            "mime_type": mime_type or "application/octet-stream",
        }
    text = file_path.read_text(encoding="utf-8", errors="replace")
    suffix = file_path.suffix.lower()
    if suffix == ".json" or str(mime_type or "").lower() in {"application/json", "application/ld+json"}:
        return _inspect_json(text, max_chars=max_chars)
    if suffix in {".csv", ".tsv"}:
        return _inspect_csv(text, delimiter="\t" if suffix == ".tsv" else ",")
    return {
        "kind": "text",
        "chars": len(text),
        "lines": text.count("\n") + (1 if text else 0),
        "preview": _truncate(text, max_chars),
    }


def read_text_file(path: str | Path, mime_type: str = "", max_chars: int = 12000) -> dict[str, Any]:
    file_path = Path(path)
    if not is_text_file(file_path, mime_type):
        raise ValueError("file is not a supported text file")
    text = file_path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars] + f"\n\n(file truncated to {max_chars} chars)"
    return {"content": text, "truncated": truncated, "chars": len(text)}


def _inspect_json(text: str, max_chars: int) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "kind": "json",
            "valid": False,
            "error": str(exc),
            "preview": _truncate(text, max_chars),
        }
    if isinstance(payload, dict):
        shape: dict[str, Any] = {"type": "object", "keys": list(payload.keys())[:50]}
    elif isinstance(payload, list):
        shape = {"type": "array", "items": len(payload)}
    else:
        shape = {"type": type(payload).__name__}
    return {
        "kind": "json",
        "valid": True,
        "shape": shape,
        "preview": _truncate(json.dumps(payload, ensure_ascii=False, indent=2), max_chars),
    }


def _inspect_csv(text: str, delimiter: str) -> dict[str, Any]:
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    header = rows[0] if rows else []
    sample_rows = rows[1:6] if len(rows) > 1 else []
    return {
        "kind": "csv",
        "rows": len(rows),
        "columns": len(header),
        "header": header,
        "sample_rows": sample_rows,
    }


def _truncate(value: str, max_chars: int) -> str:
    text = str(value or "")
    limit = max(100, int(max_chars or 6000))
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...(truncated to {limit} chars)"
