from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def object_key_for_sha256(sha256: str) -> str:
    digest = str(sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("sha256 must be a 64-character hex digest")
    return f"objects/sha256/{digest[:2]}/{digest}"


def safe_workspace_path(root: str | Path, relative_path: str) -> Path:
    root_path = Path(root).resolve()
    raw = str(relative_path or "").replace("\\", "/").strip()
    if raw.startswith("workspace://"):
        raw = raw[len("workspace://") :]
    candidate_relative = Path(raw)
    if not raw or candidate_relative.is_absolute() or candidate_relative.drive:
        raise ValueError("workspace path must be relative")
    candidate = (root_path / candidate_relative).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("workspace path escapes workspace root") from exc
    return candidate


@dataclass(slots=True)
class WorkspaceFile:
    id: str
    name: str
    path: str
    object_key: str
    sha256: str
    size: int
    mime_type: str
    source: str
    status: str
    created_at: str
    updated_at: str

    source_id: str = ""
    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkspaceFile":
        return cls(
            id=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            path=str(payload.get("path") or ""),
            object_key=str(payload.get("object_key") or ""),
            sha256=str(payload.get("sha256") or ""),
            size=int(payload.get("size") or 0),
            mime_type=str(payload.get("mime_type") or payload.get("mimeType") or "application/octet-stream"),
            source=str(payload.get("source") or "unknown"),
            status=str(payload.get("status") or "ready"),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            source_id=str(payload.get("source_id") or payload.get("sourceId") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "object_key": self.object_key,
            "sha256": self.sha256,
            "size": self.size,
            "mime_type": self.mime_type,
            "source": self.source,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_id": self.source_id,
        }

    def public_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_id": self.id,
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "mime_type": self.mime_type,
            "source": self.source,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class WorkspaceManifest:
    prefix: str
    version: int = 0
    files: list[WorkspaceFile] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def empty(cls, prefix: str) -> "WorkspaceManifest":
        return cls(prefix=str(prefix or "").strip("/"))

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None, prefix: str) -> "WorkspaceManifest":
        if not isinstance(payload, dict):
            return cls.empty(prefix)
        files = [
            WorkspaceFile.from_dict(item)
            for item in payload.get("files", [])
            if isinstance(item, dict)
        ]
        return cls(
            prefix=str(payload.get("prefix") or prefix or "").strip("/"),
            version=int(payload.get("version") or 0),
            files=files,
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "prefix": self.prefix,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": [file.to_dict() for file in self.files],
        }

    def upsert_file(self, file: WorkspaceFile) -> WorkspaceFile:
        now = utc_now_iso()
        file.updated_at = file.updated_at or now
        for index, existing in enumerate(self.files):
            if existing.id == file.id or existing.path == file.path:
                file.created_at = file.created_at or existing.created_at
                self.files[index] = file
                self._touch()
                return file
        self.files.append(file)
        self._touch()
        return file

    def find(self, file_id_or_path: str) -> WorkspaceFile | None:
        value = str(file_id_or_path or "").strip()
        if value.startswith("workspace://"):
            value = value[len("workspace://") :]
        for file in self.files:
            if file.id == value or file.path == value or file.name == value:
                return file
        return None
    def find_by_source_id(self, source_id: str) -> WorkspaceFile | None:
        value = str(source_id or "").strip()
        if not value:
            return None
        for file in reversed(self.files):
            if file.source_id == value and file.status != "deleted":
                return file
        return None


    def next_file_id(self, prefix: str = "file") -> str:
        token = re.sub(r"[^0-9A-Za-z_]+", "_", str(prefix or "file")).strip("_") or "file"
        existing_ids = {file.id for file in self.files}
        index = len(self.files) + 1
        while f"{token}_{index}" in existing_ids:
            index += 1
        return f"{token}_{index}"

    def public_summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "files": [file.public_summary() for file in self.files if file.status != "deleted"],
        }

    def _touch(self) -> None:
        self.version += 1
        self.updated_at = utc_now_iso()
