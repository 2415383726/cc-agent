from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import mimetypes
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
import zipfile

from .skill_registry import SkillRegistry, _parse_frontmatter, _split_frontmatter
from .workspace.manifest import safe_workspace_path
from .workspace.storage_client import MinioStorageClient, StorageConfig


_NAME_RE = re.compile(r"^[\w-]{1,64}$")
_LAYERS = ("agent", "app", "user")
_SCRIPT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".sh", ".ps1"}
_MAX_PACKAGE_BYTES = 20 * 1024 * 1024


@dataclass(slots=True)
class SkillScope:
    app_id: str
    user_id: str


@dataclass(slots=True)
class SkillPackageMeta:
    id: str
    name: str
    display_name: str
    layer: str
    version: int
    status: str
    description: str
    updated_at: str
    prefix: str
    manifest_key: str


class SkillLibrarySession:
    def __init__(
        self,
        config: StorageConfig,
        scope: SkillScope,
        storage: Any | None = None,
        workspace: Any | None = None,
        local_root: str | Path | None = None,
        max_package_bytes: int = _MAX_PACKAGE_BYTES,
    ):
        self.config = config
        self.scope = scope
        self.storage = storage
        self.workspace = workspace
        self._owns_local_root = local_root is None
        self.local_root = Path(local_root) if local_root is not None else Path(tempfile.mkdtemp(prefix="cc-agent-skills-"))
        self.materialized_root = self.local_root / "skills"
        self.max_package_bytes = max(1024, int(max_package_bytes or _MAX_PACKAGE_BYTES))
        self.skills: list[dict[str, Any]] = []
        self.warnings: list[dict[str, str]] = []
        self._opened = False

    def open(self) -> "SkillLibrarySession":
        if self._opened:
            return self
        missing = self.config.missing_required()
        if missing:
            raise ValueError(f"MinIO skill config missing: {', '.join(missing)}")
        if self.storage is None:
            self.storage = MinioStorageClient(self.config)
        self.local_root.mkdir(parents=True, exist_ok=True)
        self.refresh()
        self._opened = True
        return self

    def close(self) -> None:
        if self._owns_local_root:
            shutil.rmtree(self.local_root, ignore_errors=True)

    def refresh(self) -> None:
        self._ensure_storage()
        if self.materialized_root.exists():
            shutil.rmtree(self.materialized_root)
        self.materialized_root.mkdir(parents=True, exist_ok=True)
        self.skills = []
        self.warnings = []

        accepted: dict[str, SkillPackageMeta] = {}
        for layer in _LAYERS:
            for manifest_key in self._manifest_keys(layer):
                payload = self.storage.get_json(manifest_key)
                meta, warning = self._normalize_manifest(payload, manifest_key, layer)
                if warning:
                    self.warnings.append(warning)
                    continue
                assert meta is not None
                if meta.status != "active":
                    continue
                if meta.name in accepted:
                    self.warnings.append(
                        {
                            "path": manifest_key,
                            "reason": f"skill name conflicts with {accepted[meta.name].layer} skill: {meta.name}",
                        }
                    )
                    continue
                try:
                    self._materialize(meta)
                except Exception as exc:
                    self.warnings.append({"path": manifest_key, "reason": str(exc)})
                    continue
                accepted[meta.name] = meta

        snapshot = SkillRegistry(self.materialized_root).load()
        self.warnings.extend(snapshot.warnings)
        skills: list[dict[str, Any]] = []
        for skill in snapshot.skills:
            name = str(skill.get("name") or "")
            meta = accepted.get(name)
            if meta is None:
                continue
            merged = dict(skill)
            merged["layer"] = meta.layer
            merged["source"] = meta.layer
            merged["status"] = meta.status
            merged["display_name"] = meta.display_name or skill.get("display_name") or name
            merged["description"] = meta.description or skill.get("description") or ""
            metadata = dict(merged.get("metadata") or {})
            metadata["skill_json"] = {
                "id": meta.id,
                "name": meta.name,
                "layer": meta.layer,
                "version": meta.version,
                "status": meta.status,
                "updated_at": meta.updated_at,
            }
            merged["metadata"] = metadata
            skills.append(merged)
        self.skills = skills

    def install(self, name: str = "", from_file_id: str = "", overwrite: bool = False) -> dict[str, Any]:
        self._ensure_storage()
        if self.workspace is None:
            return {"status": "invalid", "message": "workspace is not configured for skill installation"}
        staged_root: Path | None = None
        try:
            source_path = self._resolve_workspace_source(from_file_id)
            staged_root = self._stage_package(source_path)
            metadata = self._metadata_from_stage(staged_root, requested_name=name)

            protected_layer = self._protected_layer(metadata["name"])
            if protected_layer:
                return {
                    "status": "protected",
                    "name": metadata["name"],
                    "message": f"skill '{metadata['name']}' belongs to {protected_layer} layer and cannot be overwritten",
                }

            user_manifest = self.storage.get_json(self._skill_prefix("user", metadata["name"]) + "/skill.json")
            if isinstance(user_manifest, dict) and user_manifest.get("status", "active") == "active" and not overwrite:
                return {
                    "status": "needs_confirmation",
                    "name": metadata["name"],
                    "message": f"user skill '{metadata['name']}' already exists; retry with overwrite=true to replace it",
                }

            self._delete_prefix(self._skill_prefix("user", metadata["name"]) + "/files/")
            self._upload_staged_files(staged_root, metadata["name"])
            manifest = {
                "id": metadata["name"],
                "name": metadata["name"],
                "display_name": metadata.get("display_name") or metadata["name"],
                "layer": "user",
                "version": int((user_manifest or {}).get("version") or 0) + 1 if isinstance(user_manifest, dict) else 1,
                "status": "active",
                "description": metadata.get("description") or "",
                "updated_at": _utc_now_iso(),
            }
            self.storage.put_json(self._skill_prefix("user", metadata["name"]) + "/skill.json", manifest)
            self.refresh()
        except Exception as exc:
            payload = {"status": "invalid", "message": str(exc)}
            if "metadata" in locals() and isinstance(metadata, dict) and metadata.get("name"):
                payload["name"] = metadata["name"]
            return payload
        finally:
            if staged_root is not None:
                shutil.rmtree(staged_root.parent, ignore_errors=True)
        return {"status": "installed", "name": metadata["name"], "skill": manifest}

    def validate(self, from_file_id: str = "") -> dict[str, Any]:
        if self.workspace is None:
            return {"status": "invalid", "message": "workspace is not configured for skill validation"}
        staged_root: Path | None = None
        try:
            source_path = self._resolve_workspace_source(from_file_id)
            staged_root = self._stage_package(source_path)
            metadata = self._metadata_from_stage(staged_root)
        except Exception as exc:
            return {"status": "invalid", "message": str(exc)}
        finally:
            if staged_root is not None:
                shutil.rmtree(staged_root.parent, ignore_errors=True)
        return {"status": "valid", "name": metadata["name"], "description": metadata.get("description") or ""}

    def remove(self, name: str) -> dict[str, Any]:
        self._ensure_storage()
        try:
            skill_name = validate_skill_name(name)
        except ValueError as exc:
            return {"status": "invalid", "message": str(exc)}
        protected_layer = self._protected_layer(skill_name)
        if protected_layer:
            return {
                "status": "protected",
                "name": skill_name,
                "message": f"skill '{skill_name}' belongs to {protected_layer} layer and cannot be removed by the user",
            }
        prefix = self._skill_prefix("user", skill_name)
        manifest_key = f"{prefix}/skill.json"
        manifest = self.storage.get_json(manifest_key)
        if not isinstance(manifest, dict):
            return {"status": "not_found", "name": skill_name, "message": f"user skill not found: {skill_name}"}
        manifest.update(
            {
                "id": skill_name,
                "name": skill_name,
                "layer": "user",
                "status": "deleted",
                "updated_at": _utc_now_iso(),
            }
        )
        self.storage.put_json(manifest_key, manifest)
        self.refresh()
        return {"status": "removed", "name": skill_name}

    def restore(self, name: str) -> dict[str, Any]:
        self._ensure_storage()
        try:
            skill_name = validate_skill_name(name)
        except ValueError as exc:
            return {"status": "invalid", "message": str(exc)}
        protected_layer = self._protected_layer(skill_name)
        if protected_layer:
            return {
                "status": "protected",
                "name": skill_name,
                "message": f"skill '{skill_name}' belongs to {protected_layer} layer and cannot be overwritten",
            }
        manifest_key = f"{self._skill_prefix('user', skill_name)}/skill.json"
        manifest = self.storage.get_json(manifest_key)
        if not isinstance(manifest, dict):
            return {"status": "not_found", "name": skill_name, "message": f"user skill not found: {skill_name}"}
        manifest.update({"status": "active", "updated_at": _utc_now_iso()})
        self.storage.put_json(manifest_key, manifest)
        self.refresh()
        return {"status": "restored", "name": skill_name}

    def show(self, name: str) -> dict[str, Any]:
        skill_name = str(name or "").strip()
        for skill in self.skills:
            if skill.get("name") == skill_name or skill.get("id") == skill_name:
                return {
                    "status": "found",
                    "skill": {
                        key: value
                        for key, value in skill.items()
                        if key not in {"body", "path"}
                    },
                }
        return {"status": "not_found", "message": f"skill not found: {skill_name}"}

    def prompt_context(self) -> str:
        """Return prompt text telling the LLM how to access skill resources and scripts."""
        lines = ["Skill package resources:"]
        for skill in self.skills:
            path = str(skill.get("path") or "")
            if not path:
                continue
            scripts = skill.get("resources", {}).get("scripts", [])
            references = skill.get("resources", {}).get("references", [])
            lines.append(f"- {skill.get('name')}: use SkillReadResource for references/assets and SkillRunScript for scripts")
            for reference in references:
                lines.append(f"  reference: {reference}")
            if scripts:
                for script in scripts:
                    lines.append(f"  script: {script}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _manifest_keys(self, layer: str) -> list[str]:
        root = self._layer_root(layer)
        return [key for key in self.storage.list_objects(root) if key.endswith("/skill.json")]

    def _normalize_manifest(
        self,
        payload: Any,
        manifest_key: str,
        layer: str,
    ) -> tuple[SkillPackageMeta | None, dict[str, str] | None]:
        if not isinstance(payload, dict):
            return None, {"path": manifest_key, "reason": "missing or invalid skill.json"}
        try:
            skill_id = validate_skill_name(str(payload.get("id") or payload.get("name") or ""))
            name = validate_skill_name(str(payload.get("name") or skill_id))
        except ValueError as exc:
            return None, {"path": manifest_key, "reason": str(exc)}
        status = str(payload.get("status") or "active").strip().lower()
        prefix = manifest_key[: -len("/skill.json")]
        return (
            SkillPackageMeta(
                id=skill_id,
                name=name,
                display_name=str(payload.get("display_name") or payload.get("displayName") or name),
                layer=layer,
                version=_positive_int(payload.get("version"), 1),
                status=status,
                description=str(payload.get("description") or ""),
                updated_at=str(payload.get("updated_at") or payload.get("updatedAt") or ""),
                prefix=prefix,
                manifest_key=manifest_key,
            ),
            None,
        )

    def _materialize(self, meta: SkillPackageMeta) -> None:
        prefix = f"{meta.prefix}/files/"
        keys = [key for key in self.storage.list_objects(prefix) if not key.endswith("/")]
        if f"{prefix}SKILL.md" not in keys:
            raise ValueError("active skill package is missing files/SKILL.md")
        target_dir = self.materialized_root / meta.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for key in keys:
            rel_path = key[len(prefix) :]
            validate_skill_file_path(rel_path)
            self.storage.download_file(key, safe_workspace_path(target_dir, rel_path))

    def _resolve_workspace_source(self, from_file_id: str = "") -> Path:
        if from_file_id:
            return Path(self.workspace.materialize(from_file_id))
        candidates = list(getattr(getattr(self.workspace, "manifest", None), "files", []) or [])
        for file in reversed(candidates):
            name = str(getattr(file, "name", "") or "").lower()
            path = str(getattr(file, "path", "") or "").lower()
            if name.endswith(".zip") or path.endswith(".zip") or name == "skill.md" or path.endswith("/skill.md"):
                return Path(self.workspace.materialize(getattr(file, "id", "")))
        raise ValueError("no skill zip or SKILL.md file found in the current workspace")

    def _stage_package(self, source_path: Path) -> Path:
        if source_path.stat().st_size > self.max_package_bytes:
            raise ValueError("skill package exceeds maximum size")
        stage_parent = Path(tempfile.mkdtemp(prefix="cc-agent-skill-install-"))
        if source_path.suffix.lower() == ".zip":
            return self._stage_zip(source_path, stage_parent)
        if source_path.suffix.lower() in {".md", ".markdown", ".txt"}:
            stage = stage_parent / "package"
            stage.mkdir(parents=True, exist_ok=True)
            (stage / "SKILL.md").write_bytes(source_path.read_bytes())
            return stage
        raise ValueError("skill install source must be a .zip package or SKILL.md file")

    def _stage_zip(self, source_path: Path, stage_parent: Path) -> Path:
        with zipfile.ZipFile(source_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos:
                raise ValueError("skill zip is empty")
            total_size = sum(int(info.file_size or 0) for info in infos)
            if total_size > self.max_package_bytes:
                raise ValueError("skill zip exceeds maximum extracted size")
            raw_paths = [_zip_path(info) for info in infos]
            stripped_paths = _strip_single_root(raw_paths)
            stage = stage_parent / "package"
            stage.mkdir(parents=True, exist_ok=True)
            seen: set[str] = set()
            for info, rel_path in zip(infos, stripped_paths):
                if rel_path in seen:
                    raise ValueError(f"duplicate path in skill zip: {rel_path}")
                seen.add(rel_path)
                if _is_noise_path(rel_path):
                    continue
                validate_skill_file_path(rel_path)
                if _is_zip_symlink(info):
                    raise ValueError(f"unsafe zip path: symlink not allowed: {rel_path}")
                target = safe_workspace_path(stage, rel_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
            if not (stage / "SKILL.md").is_file():
                raise ValueError("skill zip must contain SKILL.md")
            return stage

    def _metadata_from_stage(self, staged_root: Path, requested_name: str = "") -> dict[str, str]:
        skill_path = staged_root / "SKILL.md"
        if not skill_path.is_file():
            raise ValueError("skill package must contain SKILL.md")
        text = skill_path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        metadata = _parse_frontmatter(frontmatter)
        name = requested_name or str(metadata.get("name") or "").strip()
        name = validate_skill_name(name)
        description = str(metadata.get("description") or "").strip()
        if not description:
            raise ValueError("SKILL.md frontmatter must include description")
        if not body.strip():
            raise ValueError("SKILL.md body is empty")
        return {
            "name": name,
            "display_name": str(metadata.get("display_name") or metadata.get("display-name") or name),
            "description": description,
        }

    def _upload_staged_files(self, staged_root: Path, name: str) -> None:
        prefix = self._skill_prefix("user", name)
        for path in sorted(item for item in staged_root.rglob("*") if item.is_file()):
            rel_path = path.relative_to(staged_root).as_posix()
            validate_skill_file_path(rel_path)
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.storage.put_bytes(f"{prefix}/files/{rel_path}", path.read_bytes(), mime_type)

    def _delete_prefix(self, prefix: str) -> None:
        for key in self.storage.list_objects(prefix):
            self.storage.delete_object(key)

    def _protected_layer(self, name: str) -> str:
        for layer in ("agent", "app"):
            for manifest_key in self._manifest_keys(layer):
                payload = self.storage.get_json(manifest_key)
                meta, _warning = self._normalize_manifest(payload, manifest_key, layer)
                if meta is not None and meta.status == "active" and meta.name == name:
                    return layer
        return ""

    def _skill_prefix(self, layer: str, name: str) -> str:
        return f"{self._layer_root(layer).rstrip('/')}/{validate_skill_name(name)}"

    def _layer_root(self, layer: str) -> str:
        if layer == "agent":
            return "_cc_agent/skills/agent/"
        if layer == "app":
            return f"{_segment(self.scope.app_id)}/skills/"
        if layer == "user":
            return f"{_segment(self.scope.app_id)}/users/{_segment(self.scope.user_id)}/skills/"
        raise ValueError(f"unsupported skill layer: {layer}")

    def _ensure_storage(self) -> None:
        if self.storage is None:
            raise RuntimeError("skill storage is not configured")


def validate_skill_name(value: str) -> str:
    name = str(value or "").strip()
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid skill name: {value}")
    return name


def validate_skill_file_path(value: str) -> str:
    rel_path = str(value or "").replace("\\", "/").strip()
    if not rel_path:
        raise ValueError("unsafe skill path: empty path")
    if rel_path.startswith("/") or rel_path.startswith("../") or "/../" in rel_path or rel_path == "..":
        raise ValueError(f"unsafe skill path: {value}")
    # Reject hidden files and backup/temp patterns
    parts = rel_path.split("/")
    if any(part.startswith(".") and part not in {".gitignore", ".gitkeep"} for part in parts):
        raise ValueError(f"unsupported skill path: hidden files not allowed: {value}")
    if any(part.endswith("~") or part.endswith(".bak") or part.startswith(".#") for part in parts):
        raise ValueError(f"unsupported skill path: backup file: {value}")
    if rel_path.startswith("scripts/") and Path(rel_path).suffix.lower() not in _SCRIPT_SUFFIXES:
        raise ValueError(f"unsupported skill script type: {value}")
    return rel_path


def _zip_path(info: zipfile.ZipInfo) -> str:
    path = str(info.filename or "").replace("\\", "/").strip()
    if not path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError(f"unsafe zip path: {info.filename}")
    parts = [part for part in path.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValueError(f"unsafe zip path: {info.filename}")
    return "/".join(parts)


def _strip_single_root(paths: list[str]) -> list[str]:
    if any(path == "SKILL.md" for path in paths):
        return paths
    roots = {path.split("/", 1)[0] for path in paths if "/" in path}
    if len(roots) == 1:
        root = next(iter(roots))
        return [path[len(root) + 1 :] if path.startswith(root + "/") else path for path in paths]
    return paths


def _is_noise_path(rel_path: str) -> bool:
    """Skip common build/IDE noise files during skill installation."""
    parts = rel_path.split("/")
    for part in parts:
        if part in {"__pycache__", ".git", ".svn", ".hg", "__MACOSX", ".DS_Store", "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache"}:
            return True
    return rel_path.endswith((".pyc", ".pyo", ".egg-info", ".dist-info"))


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return ((int(getattr(info, "external_attr", 0)) >> 16) & 0o170000) == 0o120000


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _segment(value: str) -> str:
    text = str(value or "default")
    text = re.sub(r"[\x00-\x1f<>:\"|?*\\/]+", "_", text)
    text = re.sub(r"_{3,}", "__", text)
    return text.strip("._-") or "default"
