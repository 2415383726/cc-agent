from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

from .messages import ToolResult
from .workspace.execution_runtime import WorkspaceExecutionRuntime


TEXT_RESOURCE_SUFFIXES = {
    ".csv",
    ".html",
    ".json",
    ".md",
    ".svg",
    ".text",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
ARTIFACT_SUFFIXES = {
    ".csv",
    ".docx",
    ".html",
    ".jpg",
    ".jpeg",
    ".json",
    ".md",
    ".pdf",
    ".png",
    ".pptx",
    ".svg",
    ".txt",
    ".xlsx",
}


class SkillRuntime:
    def __init__(
        self,
        workspace_root: str | Path | None = None,
        timeout_seconds: int = 120,
        max_timeout_seconds: int = 600,
        max_output_chars: int = 8000,
        workspace: Any | None = None,
    ):
        self.workspace_root = (
            Path(workspace_root)
            if workspace_root is not None
            else Path(tempfile.mkdtemp(prefix="cc-agent-skill-workspace-"))
        )
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = max(1, int(timeout_seconds or 120))
        self.max_timeout_seconds = max(self.timeout_seconds, int(max_timeout_seconds or 600))
        self.max_output_chars = max(1000, int(max_output_chars or 8000))
        self.workspace = workspace

    def read_resource(self, skill: dict[str, Any], path: str, limit: int = 12000) -> ToolResult:
        skill_dir, root_error = _skill_dir(skill)
        if root_error:
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation=f"Skill resource error: {root_error} (requested: {path}).",
                is_error=True,
                synthetic=True,
            )
        assert skill_dir is not None
        normalized_path = _normalize_skill_rel_path(path, skill)
        resource_path, error = _resolve_under(skill_dir, normalized_path)
        if error:
            available = _list_skill_dir(skill_dir)
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation=(
                    f"Skill resource error: {error} (requested: {path}, normalized: {normalized_path}). "
                    f"Available under skill root:\n{available}"
                ),
                is_error=True,
                synthetic=True,
            )
        if resource_path.suffix.lower() not in TEXT_RESOURCE_SUFFIXES:
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation=f"Skill resource error: unsupported text resource type: {resource_path.suffix}",
                is_error=True,
                synthetic=True,
            )
        try:
            text = resource_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation="Skill resource error: resource is not UTF-8 text",
                is_error=True,
                synthetic=True,
            )
        except OSError as exc:
            return ToolResult(
                tool_call_id="SkillReadResource",
                tool_name="SkillReadResource",
                llm_observation=f"Skill resource error: {exc}",
                is_error=True,
                synthetic=True,
            )
        if len(text) > limit:
            text = text[:limit] + f"\n\n(resource truncated to {limit} chars)"
        return ToolResult(
            tool_call_id="SkillReadResource",
            tool_name="SkillReadResource",
            llm_observation=f"Skill resource loaded: {normalized_path}\n\n{text}",
        )

    def run_script(
        self,
        skill: dict[str, Any],
        script_path: str,
        args: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> ToolResult:
        skill_dir, root_error = _skill_dir(skill)
        if root_error:
            return _script_error(f"Skill script error: {root_error}")
        assert skill_dir is not None
        normalized_script_path = _normalize_skill_rel_path(script_path, skill)
        script, error = _resolve_under(skill_dir, normalized_script_path)
        if error:
            return _script_error(f"Skill script error: {error} (requested: {script_path}, normalized: {normalized_script_path})")
        try:
            script.relative_to(skill_dir / "scripts")
        except ValueError:
            return _script_error("Skill script error: script must be under scripts/")
        command, interpreter_error = _script_command(script)
        if interpreter_error:
            return _script_error(interpreter_error)
        # Append args as CLI arguments so argparse-based scripts can receive them
        cli_args = _args_to_cli(args or {})
        if cli_args:
            command.extend(cli_args)
        result = WorkspaceExecutionRuntime(
            workspace=self.workspace,
            workspace_root=self.workspace_root,
            timeout_seconds=self.timeout_seconds,
            max_timeout_seconds=self.max_timeout_seconds,
            max_output_chars=self.max_output_chars,
        ).run_process(
            command,
            tool_name="SkillRunScript",
            args=args or {},
            timeout_seconds=timeout_seconds,
            env_extra={"CC_AGENT_SKILL_DIR": str(skill_dir)},
        )
        metadata = dict(result.metadata or {})
        metadata.update(
            {
                "skill_name": skill.get("name") or skill.get("id"),
                "script_name": script.relative_to(skill_dir).as_posix(),
            }
        )
        result.metadata = metadata
        result.llm_observation = _script_observation("failed" if result.is_error else "completed", metadata)
        return result

    def render_shell(self, text: str, shell: str = "", timeout_seconds: int | None = None) -> str:
        return render_dynamic_shell_blocks(
            text,
            shell=shell,
            cwd=self.workspace_root,
            timeout_seconds=min(self.max_timeout_seconds, int(timeout_seconds or self.timeout_seconds)),
        )

    def _publish_workspace_artifacts(self, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.workspace is None or not artifacts:
            return artifacts
        published: list[dict[str, Any]] = []
        for artifact in artifacts:
            raw_path = str(artifact.get("path") or "").strip()
            path = Path(raw_path)
            if not path.is_absolute():
                path = self.workspace_root / raw_path
            try:
                published.append(
                    self.workspace.register_output_file(
                        path,
                        name=str(artifact.get("name") or path.name),
                        mime_type=str(artifact.get("mime_type") or ""),
                    )
                )
            except Exception as exc:
                fallback = {
                    key: value
                    for key, value in artifact.items()
                    if key not in {"bytes", "data_url"}
                }
                fallback.update({"status": "upload_failed", "error": str(exc)})
                published.append(fallback)
        return published


def collect_declared_artifacts(stdout: str, workspace: Path) -> list[dict[str, Any]]:
    payload = _last_json_object(stdout)
    raw_artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(raw_artifacts, list):
        return []
    artifacts: list[dict[str, Any]] = []
    for item in raw_artifacts:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = workspace / path
        artifact = _artifact_from_path(
            path,
            workspace=workspace,
            name=str(item.get("name") or item.get("filename") or ""),
            mime_type=str(item.get("mime_type") or item.get("mimeType") or ""),
        )
        if artifact:
            artifacts.append(artifact)
    return artifacts


def collect_new_artifacts(workspace: Path, before: set[Path]) -> list[dict[str, Any]]:
    artifacts = []
    for path in sorted(_workspace_files(workspace) - before):
        artifact = _artifact_from_path(path, workspace=workspace)
        if artifact:
            artifacts.append(artifact)
    return artifacts


def render_dynamic_shell_blocks(text: str, shell: str, cwd: Path, timeout_seconds: int = 120) -> str:
    return text


def artifact_events(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for artifact in artifacts or []:
        blob = artifact.get("bytes")
        if not isinstance(blob, (bytes, bytearray)):
            continue
        name = str(artifact.get("name") or "generated_file")
        mime_type = str(artifact.get("mime_type") or "application/octet-stream")
        events.append(
            {
                "type": "dify_blob",
                "blob": bytes(blob),
                "meta": {
                    "filename": name,
                    "output_filename": name,
                    "mime_type": mime_type,
                },
            }
        )
    return events


def artifact_activity_content(artifacts: list[dict[str, Any]], skill_name: str = "", script_name: str = "") -> dict[str, Any]:
    files = []
    for artifact in artifacts or []:
        files.append(
            {
                "name": artifact.get("name"),
                "mime_type": artifact.get("mime_type"),
                "size": artifact.get("size"),
                "status": artifact.get("status") or "attached",
                **(
                    {"download_url": artifact.get("download_url")}
                    if artifact.get("download_url")
                    else {}
                ),
                **(
                    {"expires_at": artifact.get("expires_at")}
                    if artifact.get("expires_at")
                    else {}
                ),
            }
        )
    return {
        "skillName": skill_name,
        "scriptName": script_name,
        "files": files,
        "message": "Generated files were attached to this chat response.",
    }


def _args_to_cli(args: dict[str, Any]) -> list[str]:
    """Convert a dict of arguments to CLI-style flags and positional args."""
    cli: list[str] = []
    # Positional-like args: keys that are digits or start with _
    for key in sorted(args.keys(), key=lambda k: (not str(k).isdigit(), str(k))):
        value = args[key]
        if str(key).startswith("_"):
            continue
        if str(key).startswith("--"):
            cli.append(str(key))
            if value is not True:
                cli.append(str(value))
        elif str(key).isdigit():
            cli.append(str(value))
        else:
            cli.append(f"--{key}")
            if value is not True:
                cli.append(str(value))
    return cli


def _script_command(script: Path) -> tuple[list[str], str]:
    suffix = script.suffix.lower()
    if suffix == ".py":
        python = os.environ.get("PYTHON", "") or sys.executable
        return [python, str(script)], ""
    if suffix in {".js", ".mjs", ".cjs"}:
        node = shutil.which("node")
        if not node:
            return [], "Skill script error: node interpreter is not available."
        return [node, str(script)], ""
    if suffix == ".sh":
        shell = shutil.which("bash") or shutil.which("sh")
        if not shell:
            return [], "Skill script error: shell interpreter is not available."
        return [shell, str(script)], ""
    if suffix == ".ps1":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return [], "Skill script error: PowerShell interpreter is not available."
        return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], ""
    return [], f"Skill script error: unsupported script type: {suffix}"


def _artifact_from_path(path: Path, workspace: Path, name: str = "", mime_type: str = "") -> dict[str, Any] | None:
    try:
        resolved = path.resolve()
        workspace_resolved = workspace.resolve()
        resolved.relative_to(workspace_resolved)
    except (OSError, ValueError):
        return None
    if not resolved.is_file() or resolved.suffix.lower() not in ARTIFACT_SUFFIXES:
        return None
    try:
        content = resolved.read_bytes()
    except OSError:
        return None
    guessed_mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    filename = name or resolved.name
    return {
        "name": filename,
        "path": resolved.relative_to(workspace_resolved).as_posix(),
        "mime_type": mime_type or guessed_mime,
        "size": len(content),
        "bytes": content,
        "data_url": f"data:{mime_type or guessed_mime};base64,{base64.b64encode(content).decode('ascii')}",
    }


def _workspace_files(workspace: Path) -> set[Path]:
    if not workspace.exists():
        return set()
    return {path.resolve() for path in workspace.rglob("*") if path.is_file()}


def _resolve_under(root: Path, rel_path: str) -> tuple[Path, str]:
    try:
        root_resolved = root.resolve()
        candidate = (root / rel_path).resolve()
        candidate.relative_to(root_resolved)
    except (OSError, ValueError):
        return root, "outside skill directory"
    if not candidate.is_file():
        return candidate, "file not found"
    return candidate, ""


def _list_skill_dir(skill_dir: Path, max_items: int = 50) -> str:
    try:
        items: list[str] = []
        for entry in sorted(skill_dir.rglob("*")):
            rel = entry.relative_to(skill_dir)
            if entry.is_dir():
                items.append(f"  {rel}/")
            else:
                items.append(f"  {rel}")
            if len(items) >= max_items:
                items.append(f"  ... ({max_items} item limit reached)")
                break
        return "\n".join(items) if items else "(empty directory)"
    except OSError:
        return "(directory not readable)"


def _skill_dir(skill: dict[str, Any]) -> tuple[Path | None, str]:
    raw_path = str(skill.get("path") or "").strip()
    if not raw_path:
        return None, "skill has no resource directory"
    path = Path(raw_path)
    skill_dir = path.parent if path.name else path
    if not skill_dir.exists() or not skill_dir.is_dir():
        return None, f"skill directory not found: {skill_dir}"
    return skill_dir, ""


def _normalize_skill_rel_path(rel_path: str, skill: dict[str, Any] | None = None) -> str:
    text = str(rel_path or "").replace("\\", "/").strip()
    if text.startswith("skill://"):
        text = text[len("skill://") :]
    skill = skill if isinstance(skill, dict) else {}
    names = [
        str(skill.get("name") or "").strip(),
        str(skill.get("id") or "").strip(),
    ]
    for _ in range(4):
        changed = False
        while text.startswith("./"):
            text = text[2:]
            changed = True
        if text.startswith("files/"):
            text = text[len("files/") :]
            changed = True
        for name in names:
            if name and text.lower().startswith(name.lower() + "/"):
                text = text[len(name) + 1 :]
                changed = True
                break
        if not changed:
            break
    return text


def _last_json_object(text: str) -> dict[str, Any] | None:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _script_error(message: str, stdout: str = "", stderr: str = "", status: str = "failed") -> ToolResult:
    metadata = {"stdout": stdout, "stderr": stderr, "status": status, "artifacts": []}
    return ToolResult(
        tool_call_id="SkillRunScript",
        tool_name="SkillRunScript",
        llm_observation=message,
        metadata=metadata,
        is_error=True,
        synthetic=True,
    )


def _script_observation(status: str, metadata: dict[str, Any]) -> str:
    exit_code = metadata.get("exit_code")
    exit_info = f"Exit code: {exit_code}" if exit_code is not None else "Exit code: N/A (script may not have started — check interpreter availability and script path)"
    lines = [
        f"Skill script {status}: {metadata.get('script_name') or ''}",
        exit_info,
    ]
    stdout = str(metadata.get("stdout") or "").strip()
    stderr = str(metadata.get("stderr") or "").strip()
    if stdout:
        lines.append(f"stdout:\n{stdout}")
    if stderr:
        lines.append(f"stderr:\n{stderr}")
    elif status == "failed" and not stdout:
        lines.append("stderr: (no output captured — the script may have failed before producing output)")
    artifacts = metadata.get("artifacts") or []
    if artifacts:
        has_download_url = any(isinstance(artifact, dict) and artifact.get("download_url") for artifact in artifacts)
        lines.append("Artifacts saved to the workspace:" if has_download_url else "Artifacts attached to the chat output:")
        for artifact in artifacts:
            lines.append(f"- {artifact.get('name')} ({artifact.get('size')} bytes)")
        if has_download_url:
            lines.append("Instruction: use the system-provided workspace download URLs; do not invent URLs.")
        else:
            lines.append("Instruction: Do not invent download URLs; the files are attached to this chat output.")
    return "\n".join(lines)


def _truncate(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...(truncated to {limit} chars)"
