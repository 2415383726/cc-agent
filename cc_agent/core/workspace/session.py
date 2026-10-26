from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import mimetypes
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .manifest import (
    WorkspaceFile,
    WorkspaceManifest,
    object_key_for_sha256,
    safe_workspace_path,
    utc_now_iso,
)
from .materializer import inspect_materialized_file, is_text_file, read_text_file
from .storage_client import ConditionalWriteConflict, MinioStorageClient, StorageConfig

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkspaceScope:
    app_id: str
    user_id: str
    conversation_id: str
    run_id: str = ""

    @property
    def workspace_prefix(self) -> str:
        return (
            f"{_segment(self.app_id)}/users/{_segment(self.user_id)}/"
            f"conversations/{_segment(self.conversation_id)}/workspace"
        )

    @property
    def manifest_key(self) -> str:
        return f"{self.workspace_prefix}/manifest.json"

class WorkspaceSession:
    def __init__(
        self,
        config: StorageConfig,
        scope: WorkspaceScope,
        storage: Any | None = None,
        dify_files: Iterable[Any] | None = None,
        local_root: str | Path | None = None,
    ):
        self.config = config
        self.scope = scope
        self.storage = storage
        self.dify_files = list(dify_files or [])
        self._owns_local_root = local_root is None
        self.local_root = Path(local_root) if local_root is not None else Path(tempfile.mkdtemp(prefix="cc-agent-workspace-"))
        self.uploads_dir = self.local_root / "uploads"
        self.outputs_dir = self.local_root / "outputs"
        self.tmp_dir = self.local_root / "tmp"
        self.manifest = WorkspaceManifest.empty(prefix=scope.workspace_prefix)
        self._base_version = 0
        self._base_etag: str | None = None
        self._opened = False
        self.imported_files: list[dict[str, Any]] = []

    def open(self) -> "WorkspaceSession":
        if self._opened:
            return self
        missing = self.config.missing_required()
        if missing:
            raise ValueError(f"MinIO workspace config missing: {', '.join(missing)}")
        if self.storage is None:
            self.storage = MinioStorageClient(self.config)
        self.local_root.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        try:

            if hasattr(self.storage, "get_json_with_etag"):
                current, self._base_etag = self.storage.get_json_with_etag(self.scope.manifest_key)
            else:
                current = self.storage.get_json(self.scope.manifest_key)
                self._base_etag = None
            self.manifest = WorkspaceManifest.from_dict(current, prefix=self.scope.workspace_prefix)
            self._base_version = self.manifest.version
            self.import_dify_files(self.dify_files)
            self._opened = True
            return self
        except Exception:
            self.close()
            raise

    def commit(self) -> None:
        self._ensure_open()
        if self.manifest.version == self._base_version:
            return
        if hasattr(self.storage, "put_json_conditional"):
            try:
                self._base_etag = self.storage.put_json_conditional(
                    self.scope.manifest_key, self.manifest.to_dict(), self._base_etag
                )
            except ConditionalWriteConflict as exc:
                raise RuntimeError("workspace manifest changed during commit") from exc
            self._base_version = self.manifest.version
            return
        current = self.storage.get_json(self.scope.manifest_key)
        current_version = int(current.get("version") or 0) if isinstance(current, dict) else 0
        if current_version != self._base_version:
            raise RuntimeError(
                f"workspace manifest version conflict: expected {self._base_version}, got {current_version}"
            )
        self.storage.put_json(self.scope.manifest_key, self.manifest.to_dict())
        self._base_version = self.manifest.version

    def close(self) -> None:
        self._opened = False
        if self._owns_local_root:
            shutil.rmtree(self.local_root, ignore_errors=True)

    def clear(self) -> None:
        """Reset the workspace manifest to empty and upload it."""
        self._ensure_open()
        logger.info("cc_agent workspace clearing: key=%s", self.scope.manifest_key)
        next_version = self._base_version + 1
        self.manifest = WorkspaceManifest.empty(prefix=self.scope.workspace_prefix)
        self.manifest.version = next_version
        self.commit()
        logger.info("cc_agent workspace cleared: manifest uploaded version=%s", self.manifest.version)
        # Clean up local uploads/outputs/tmp directories
        import shutil
        for dir_path in (self.uploads_dir, self.outputs_dir, self.tmp_dir):
            if dir_path.exists():
                shutil.rmtree(dir_path)
            dir_path.mkdir(parents=True, exist_ok=True)

    def __enter__(self) -> "WorkspaceSession":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.commit()
        finally:
            self.close()

    def import_dify_files(self, files: Iterable[Any]) -> list[WorkspaceFile]:
        self.imported_files = []
        imported: list[WorkspaceFile] = []
        for index, raw_file in enumerate(files or []):
            source_id = str(_first_value(raw_file, ["id", "upload_file_id", "uploadFileId", "dify_file_id"]) or "").strip()
            if source_id:
                existing = self.manifest.find_by_source_id(source_id)
                if existing is not None:
                    imported.append(existing)
                    self.imported_files.append(self._artifact_for_file(existing))
                    continue

            try:
                file_id_hint = _first_value(raw_file, ["id", "name", "filename", "document_name"]) or f"file_{index}"
                logger.info("cc_agent workspace importing file: index=%s file=%s keys=%s", index, file_id_hint, sorted(raw_file.keys()) if isinstance(raw_file, dict) else type(raw_file).__name__)
                file_bytes = self._dify_file_bytes(raw_file)
                logger.info("cc_agent workspace file downloaded: index=%s file=%s bytes=%s", index, file_id_hint, len(file_bytes))
            except Exception as exc:
                logger.warning("cc_agent workspace file import skipped: index=%s file=%s error=%s", index, _first_value(raw_file, ["name", "filename", "id"]) or f"file_{index}", exc)
                continue
            raw_name = _safe_filename(_first_value(raw_file, ["name", "filename", "document_name"]) or "uploaded_file")
            mime_type = _first_value(raw_file, ["mime_type", "mimeType", "mime"]) or mimetypes.guess_type(raw_name)[0] or "application/octet-stream"
            name = _add_extension(raw_name, mime_type)
            relative_path = self._unique_relative_path("uploads", name)
            digest = hashlib.sha256(file_bytes).hexdigest()
            existing = next(
                (file for file in reversed(self.manifest.files)
                 if file.source == "upload" and file.status != "deleted"
                 and file.sha256 == digest and file.name == name),
                None,
            )
            if existing is not None:
                imported.append(existing)
                self.imported_files.append(self._artifact_for_file(existing))
                continue

            local_path = safe_workspace_path(self.local_root, relative_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(file_bytes)
            registered = self._register_local_file(
                local_path,
                relative_path=relative_path,
                name=name,
                mime_type=mime_type,
                source="upload",
                file_id=self.manifest.next_file_id("upload"),
                source_id=source_id,
            )
            imported.append(registered)
            self.imported_files.append(self._artifact_for_file(registered))
        return imported

    def delete_file(self, file_id: str) -> dict[str, Any]:
        """Soft-delete a file from the workspace manifest."""
        self._ensure_open()
        file = self.manifest.find(file_id)
        if file is None:
            raise KeyError(f"workspace file not found: {file_id}")
        file.status = "deleted"
        file.updated_at = utc_now_iso()
        self.manifest.upsert_file(file)
        return {"file_id": file.id, "name": file.name, "status": "deleted"}

    def write_text_output(self, path: str, content: str, mime_type: str = "") -> dict[str, Any]:
        relative_path = str(path or "").strip().replace("\\", "/")
        if not relative_path:
            relative_path = "output.txt"
        if not relative_path.startswith("outputs/"):
            relative_path = f"outputs/{relative_path}"
        local_path = safe_workspace_path(self.local_root, relative_path)
        if not is_text_file(local_path, mime_type):
            raise ValueError("write_file only supports text, markdown, JSON, CSV, YAML, XML, and HTML outputs")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(str(content or ""), encoding="utf-8")
        file = self._register_local_file(
            local_path,
            relative_path=relative_path,
            name=local_path.name,
            mime_type=mime_type or mimetypes.guess_type(local_path.name)[0] or "text/plain",
            source="output",
            file_id=self.manifest.next_file_id("output"),
        )
        return self._artifact_for_file(file)

    def register_output_file(
        self,
        local_path: str | Path,
        relative_path: str | None = None,
        name: str = "",
        mime_type: str = "",
    ) -> dict[str, Any]:
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        if relative_path is None:
            try:
                relative_path = path.resolve().relative_to(self.local_root.resolve()).as_posix()
            except ValueError:
                relative_path = f"outputs/{_safe_filename(name or path.name)}"
                target = safe_workspace_path(self.local_root, relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
                path = target
        file = self._register_local_file(
            path,
            relative_path=relative_path,
            name=_safe_filename(name or path.name),
            mime_type=mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            source="output",
            file_id=self.manifest.next_file_id("output"),
        )
        return self._artifact_for_file(file)

    def materialize(self, file_id: str) -> Path:
        self._ensure_open()
        file = self._require_file(file_id)
        local_path = safe_workspace_path(self.local_root, file.path)
        if local_path.is_file() and _sha256_file(local_path) == file.sha256:
            return local_path
        self.storage.download_file(file.object_key, local_path)
        return local_path

    def list_files_payload(self) -> dict[str, Any]:
        summary = self.manifest.public_summary()
        for file_entry in summary.get("files", []):
            file = self.manifest.find(file_entry.get("id") or file_entry.get("file_id") or "")
            if file:
                file_entry["download_url"] = self.storage.presigned_get_url(
                    file.object_key, self.config.presign_expiry_seconds,
                    filename=file.name, mime_type=file.mime_type,
                )
        return summary

    def inspect_file(self, file_id: str, max_chars: int = 6000) -> dict[str, Any]:
        file = self._require_file(file_id)
        local_path = self.materialize(file.id)
        return {
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "mime_type": file.mime_type,
            "size": file.size,
            **inspect_materialized_file(local_path, file.mime_type, max_chars=max_chars),
        }

    def read_file(self, file_id: str, max_chars: int = 12000) -> dict[str, Any]:
        file = self._require_file(file_id)
        local_path = self.materialize(file.id)
        read = read_text_file(local_path, file.mime_type, max_chars=max_chars)
        return {
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "mime_type": file.mime_type,
            **read,
        }

    def prompt_context(self) -> str:
        files = [
            {
                "file_id": file.id,
                "name": file.name,
                "path": file.path,
                "size": file.size,
                "mime_type": file.mime_type,
                "source": file.source,
                "status": file.status,
            }
            for file in self.manifest.files
            if file.status != "deleted"
        ]
        return (
            "Workspace files:\n"
            f"{files}\n\n"
            "Workspace rules:\n"
            "- reference files by file_id; uploads are read-only\n"
            "- write final artifacts under outputs/ with write_file\n"
            "- use run_python for temporary Python analysis; cwd is outputs/\n"
            "- run_python and skill scripts can read CC_AGENT_FILES_JSON for all visible workspace files\n"
            "- code should write generated files under CC_AGENT_OUTPUTS_DIR; new outputs are auto-registered as artifacts\n"
            "- list_files returns a download_url for each file; format as [filename](download_url) when sharing\n"
            "- write_file also returns a download_url in its observation; format as [filename](download_url) in your reply"
        )

    def activity_payload(self) -> dict[str, Any]:
        return {
            "message": "Workspace files updated.",
            "files": [self._artifact_for_file(file) for file in self.manifest.files if file.status != "deleted"],
        }

    def _register_local_file(
        self,
        local_path: Path,
        relative_path: str,
        name: str,
        mime_type: str,
        source: str,
        file_id: str,
        source_id: str = "",
    ) -> WorkspaceFile:
        self._ensure_open()
        sha256 = _sha256_file(local_path)
        object_key = object_key_for_sha256(sha256)
        if not self.storage.object_exists(object_key):
            self.storage.upload_file(object_key, local_path, content_type=mime_type or "application/octet-stream")
        now = utc_now_iso()
        file = WorkspaceFile(
            id=file_id,
            name=name,
            path=relative_path,
            object_key=object_key,
            sha256=sha256,
            size=local_path.stat().st_size,
            mime_type=mime_type or "application/octet-stream",
            source=source,
            status="ready",
            created_at=now,
            updated_at=now,
            source_id=source_id,
        )
        return self.manifest.upsert_file(file)

    def _artifact_for_file(self, file: WorkspaceFile) -> dict[str, Any]:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, int(self.config.presign_expiry_seconds or 3600)))
        return {
            "id": file.id,
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "workspace_path": f"workspace://{file.path}",
            "size": file.size,
            "mime_type": file.mime_type,
            "source": file.source,
            "status": file.status,
            "download_url": self.storage.presigned_get_url(
                file.object_key, self.config.presign_expiry_seconds,
                filename=file.name, mime_type=file.mime_type,
            ),
            "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

    def _require_file(self, file_id: str) -> WorkspaceFile:
        file = self.manifest.find(file_id)
        if file is None:
            raise KeyError(f"workspace file not found: {file_id}")
        return file

    def _ensure_open(self) -> None:
        if self.storage is None:
            raise RuntimeError("workspace storage is not configured")

    def _unique_relative_path(self, root_name: str, filename: str) -> str:
        safe_name = _safe_filename(filename)
        stem = Path(safe_name).stem or "file"
        suffix = Path(safe_name).suffix
        candidate = f"{root_name}/{safe_name}"
        index = 2
        while safe_workspace_path(self.local_root, candidate).exists() or self.manifest.find(candidate):
            candidate = f"{root_name}/{stem}-{index}{suffix}"
            index += 1
        return candidate

    def _dify_file_bytes(self, raw_file: Any) -> bytes:
        for key in ("bytes", "blob", "content", "data"):
            value = _get(raw_file, key)
            if isinstance(value, bytes):
                return value
            if isinstance(value, bytearray):
                return bytes(value)
            if isinstance(value, str) and value:
                return value.encode("utf-8")
        for key in ("local_path", "path"):
            value = str(_get(raw_file, key) or "").strip()
            if value and not value.startswith("workspace://") and Path(value).is_file():
                return Path(value).read_bytes()
        url = _file_url(raw_file)
        if url:
            return _fetch_url_bytes(url)
        file_id = _first_value(raw_file, ["id", "upload_file_id", "uploadFileId", "dify_file_id"])
        raise ValueError(f"cannot import Dify file {file_id or '<unknown>'}: no readable content, local path, or URL")


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_url_bytes(url: str) -> bytes:
    import requests

    logger.info("cc_agent workspace fetching URL: url=%s...", url[:120] if len(url) > 120 else url)
    response = requests.get(url, timeout=30)
    logger.info("cc_agent workspace fetch response: status=%s content_type=%s bytes=%s", response.status_code, response.headers.get("content-type", ""), len(response.content))
    response.raise_for_status()
    return response.content


def _file_url(raw_file: Any) -> str:
    direct = _first_value(raw_file, ["download_url", "downloadUrl", "url", "remote_url", "preview_url", "previewUrl"])
    if direct:
        return str(direct)
    file_id = _first_value(raw_file, ["id", "upload_file_id", "uploadFileId", "dify_file_id"])
    if not file_id:
        return ""
    return f"files/{file_id}/file-preview"


def _first_value(obj: Any, keys: list[str]) -> Any:
    for key in keys:
        value = _get(obj, key)
        if value not in (None, ""):
            return value
    return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _safe_filename(value: str) -> str:
    name = Path(str(value or "file").replace("\\", "/")).name.strip()
    name = re.sub(r"[\x00-\x1f<>:\"|?*]+", "_", name).strip(" .")
    return name or "file"


_MIME_EXT = {
    "text/markdown": ".md",
    "text/plain": ".txt",
    "text/html": ".html",
    "text/css": ".css",
    "text/csv": ".csv",
    "text/xml": ".xml",
    "text/yaml": ".yaml",
    "application/json": ".json",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/gzip": ".gz",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/msword": ".doc",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}


def _add_extension(name: str, mime_type: str) -> str:
    stem, ext = (name.rsplit(".", 1) + [""])[:2]
    if ext and len(ext) <= 6:
        return name  # already has a plausible extension
    suffix = _MIME_EXT.get(str(mime_type or "").split(";")[0].strip().lower(), "")
    return name + suffix if suffix else name


def _segment(value: str) -> str:
    # Allow Unicode letters/numbers, dot, underscore, hyphen. Replace path separators,
    # control characters, and unsafe chars with underscores.
    text = str(value or "default")
    text = re.sub(r"[\x00-\x1f<>:\"|?*\\/]+", "_", text)
    # Collapse runs of underscores
    text = re.sub(r"_{3,}", "__", text)
    text = text.strip("._-") or "default"
    return text
