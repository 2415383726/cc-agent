from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from uuid import uuid4

from ..messages import ToolResult


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

_SAFE_ENV_KEYS = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "LANG",
    "LC_ALL",
}


class WorkspaceExecutionRuntime:
    def __init__(
        self,
        workspace: Any | None,
        workspace_root: str | Path | None = None,
        timeout_seconds: int = 120,
        max_timeout_seconds: int = 600,
        max_output_chars: int = 8000,
    ):
        self.workspace = workspace
        if workspace_root is not None:
            self.workspace_root = Path(workspace_root)
        elif workspace is not None:
            self.workspace_root = Path(workspace.outputs_dir)
        else:
            import tempfile

            self.workspace_root = Path(tempfile.mkdtemp(prefix="cc-agent-exec-workspace-"))
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = max(1, int(timeout_seconds or 120))
        self.max_timeout_seconds = max(self.timeout_seconds, int(max_timeout_seconds or 600))
        self.max_output_chars = max(1000, int(max_output_chars or 8000))

    def run_python(
        self,
        code: str,
        input_file_ids: list[str] | None = None,
        args: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> ToolResult:
        if self.workspace is None:
            return _runtime_error("run_python", "run_python error: workspace is not configured for this run.")
        code_text = str(code or "")
        if not code_text.strip():
            return _runtime_error("run_python", "run_python error: code is empty.")
        run_dir = Path(self.workspace.tmp_dir) / "code-runs" / uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=True)
        self._write_sitecustomize(run_dir)
        script_path = run_dir / "main.py"
        script_path.write_text(code_text, encoding="utf-8")
        try:
            return self.run_process(
                [sys.executable, str(script_path)],
                tool_name="run_python",
                args=args or {},
                input_file_ids=input_file_ids or [],
                timeout_seconds=timeout_seconds,
                python_sandbox_dir=run_dir,
            )
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def run_process(
        self,
        command: list[str],
        tool_name: str,
        args: dict[str, Any] | None = None,
        input_file_ids: list[str] | None = None,
        timeout_seconds: int | None = None,
        env_extra: dict[str, str] | None = None,
        python_sandbox_dir: Path | None = None,
    ) -> ToolResult:
        timeout = min(self.max_timeout_seconds, max(1, int(timeout_seconds or self.timeout_seconds)))
        before = collect_workspace_files(self.workspace_root)
        try:
            files = self._workspace_files()
            inputs = self._input_files(files, input_file_ids or [])
            env = self._subprocess_env(
                files=files,
                inputs=inputs,
                args=args or {},
                env_extra=env_extra or {},
                python_sandbox_dir=python_sandbox_dir,
            )
            command = _rewrite_workspace_paths(command, self.workspace_root)
            completed = subprocess.run(
                command,
                cwd=self.workspace_root,
                env=env,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return _runtime_error(
                tool_name,
                f"{tool_name} timed out after {timeout} seconds.",
                stdout=_truncate(exc.stdout or "", self.max_output_chars),
                stderr=_truncate(exc.stderr or "", self.max_output_chars),
                status="timeout",
            )
        except Exception as exc:
            return _runtime_error(
                tool_name,
                f"{tool_name} error: {exc} (command: {' '.join(command)})",
            )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        artifacts = collect_declared_artifacts(stdout, self.workspace_root)
        if not artifacts:
            artifacts = collect_new_artifacts(self.workspace_root, before)
        artifacts = self._publish_workspace_artifacts(artifacts)
        metadata: dict[str, Any] = {
            "stdout": _truncate(stdout, self.max_output_chars),
            "stderr": _truncate(stderr, self.max_output_chars),
            "exit_code": completed.returncode,
            "artifacts": artifacts,
            "status": "completed" if completed.returncode == 0 else "failed",
        }
        if self.workspace is not None and artifacts:
            metadata.update(
                {
                    "activity_type": "cc_agent.workspace",
                    "activity": {"message": "Workspace files updated.", "files": artifacts},
                    "suppress_artifact_activity": True,
                }
            )
        return ToolResult(
            tool_call_id=tool_name,
            tool_name=tool_name,
            llm_observation=_observation(tool_name, metadata),
            metadata=metadata,
            is_error=completed.returncode != 0,
        )

    def _workspace_files(self) -> list[dict[str, Any]]:
        if self.workspace is None:
            return []
        files: list[dict[str, Any]] = []
        for file in getattr(self.workspace.manifest, "files", []) or []:
            if getattr(file, "status", "") == "deleted":
                continue
            local_path = self.workspace.materialize(file.id)
            files.append(
                {
                    "file_id": file.id,
                    "name": file.name,
                    "path": file.path,
                    "local_path": str(local_path),
                    "mime_type": file.mime_type,
                    "size": file.size,
                    "source": file.source,
                }
            )
        return files

    def _input_files(self, files: list[dict[str, Any]], input_file_ids: list[str]) -> list[dict[str, Any]]:
        requested = [str(item or "").strip() for item in input_file_ids if str(item or "").strip()]
        if not requested:
            return files
        by_id_or_path: dict[str, dict[str, Any]] = {}
        for item in files:
            by_id_or_path[str(item.get("file_id") or "")] = item
            by_id_or_path[str(item.get("path") or "")] = item
            by_id_or_path[str(item.get("name") or "")] = item
        inputs: list[dict[str, Any]] = []
        for value in requested:
            if value not in by_id_or_path:
                raise KeyError(f"workspace file not found: {value}")
            inputs.append(by_id_or_path[value])
        return inputs

    def _subprocess_env(
        self,
        files: list[dict[str, Any]],
        inputs: list[dict[str, Any]],
        args: dict[str, Any],
        env_extra: dict[str, str],
        python_sandbox_dir: Path | None = None,
    ) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if key.upper() in _SAFE_ENV_KEYS}
        workspace_dir = (
            Path(getattr(self.workspace, "local_root")).resolve()
            if self.workspace is not None
            else self.workspace_root.resolve()
        )
        tmp_dir = Path(getattr(self.workspace, "tmp_dir", workspace_dir / "tmp")).resolve() if self.workspace is not None else workspace_dir
        uploads_dir = (
            Path(getattr(self.workspace, "uploads_dir", workspace_dir / "uploads")).resolve()
            if self.workspace is not None
            else workspace_dir
        )
        outputs_dir = self.workspace_root.resolve()
        env.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "CC_AGENT_WORKSPACE_DIR": str(workspace_dir),
                "CC_AGENT_UPLOADS_DIR": str(uploads_dir),
                "CC_AGENT_OUTPUTS_DIR": str(outputs_dir),
                "CC_AGENT_TMP_DIR": str(tmp_dir),
                "CC_AGENT_FILES_JSON": json.dumps(files, ensure_ascii=False),
                "CC_AGENT_INPUTS_JSON": json.dumps(inputs, ensure_ascii=False),
                "CC_AGENT_ARGS_JSON": json.dumps(args, ensure_ascii=False),
                "CC_AGENT_ALLOWED_READ_ROOTS_JSON": json.dumps(self._allowed_read_roots(workspace_dir), ensure_ascii=False),
                "CC_AGENT_ALLOWED_WRITE_ROOTS_JSON": json.dumps(self._allowed_write_roots(outputs_dir, tmp_dir), ensure_ascii=False),
            }
        )
        if python_sandbox_dir is not None:
            env["PYTHONPATH"] = str(Path(python_sandbox_dir).resolve())
        env.update({str(key): str(value) for key, value in env_extra.items()})
        return env

    def _allowed_read_roots(self, workspace_dir: Path) -> list[str]:
        roots = {workspace_dir, Path(sys.executable).parent}
        for value in (sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix):
            if value:
                roots.add(Path(value))
        return [str(path.resolve()) for path in roots if path]

    def _allowed_write_roots(self, outputs_dir: Path, tmp_dir: Path) -> list[str]:
        return [str(outputs_dir.resolve()), str(tmp_dir.resolve())]

    def _write_sitecustomize(self, run_dir: Path) -> None:
        (run_dir / "sitecustomize.py").write_text(_SITECUSTOMIZE_SOURCE, encoding="utf-8")

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
            except Exception:
                continue
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


def collect_new_artifacts(workspace: Path, before: dict[Path, tuple[int, int]]) -> list[dict[str, Any]]:
    artifacts = []
    after = collect_workspace_files(workspace)
    changed_paths = [
        path
        for path, signature in after.items()
        if before.get(path) != signature
    ]
    for path in sorted(changed_paths):
        artifact = _artifact_from_path(path, workspace=workspace)
        if artifact:
            artifacts.append(artifact)
    return artifacts


def collect_workspace_files(workspace: Path) -> dict[Path, tuple[int, int]]:
    if not workspace.exists():
        return {}
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        stat = resolved.stat()
        snapshot[resolved] = (int(stat.st_mtime_ns), int(stat.st_size))
    return snapshot


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


def _runtime_error(tool_name: str, message: str, stdout: str = "", stderr: str = "", status: str = "failed") -> ToolResult:
    return ToolResult(
        tool_call_id=tool_name,
        tool_name=tool_name,
        llm_observation=message,
        metadata={"stdout": stdout, "stderr": stderr, "status": status, "artifacts": []},
        is_error=True,
        synthetic=True,
    )


def _observation(tool_name: str, metadata: dict[str, Any]) -> str:
    status = str(metadata.get("status") or "completed")
    lines = [f"{tool_name} {status}.", f"Exit code: {metadata.get('exit_code')}"]
    stdout = str(metadata.get("stdout") or "").strip()
    stderr = str(metadata.get("stderr") or "").strip()
    if stdout:
        lines.append(f"stdout:\n{stdout}")
    if stderr:
        lines.append(f"stderr:\n{stderr}")
    artifacts = metadata.get("artifacts") or []
    if artifacts:
        lines.append("Artifacts saved to the workspace:")
        for artifact in artifacts:
            lines.append(f"- {artifact.get('name')} ({artifact.get('size')} bytes)")
        lines.append("Instruction: use the system-provided workspace download URLs; do not invent URLs.")
    return "\n".join(lines)


def _truncate(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...(truncated to {limit} chars)"


_WORKSPACE_PATH_PREFIXES = ("outputs/", "uploads/", "tmp/")


def _rewrite_workspace_paths(command: list[str], workspace_root: Path) -> list[str]:
    """Resolve workspace-relative paths in command args to absolute paths.

    LLMs pass workspace file paths like ``outputs/report.pdf``, but the
    subprocess CWD is already the outputs directory.  This rewrites known
    workspace prefixes to absolute paths under the real workspace root.
    Only relative paths are rewritten; absolute paths pass through unchanged.
    """
    real_root = workspace_root.parent
    rewritten: list[str] = []
    for arg in command:
        if os.path.isabs(arg):
            rewritten.append(arg)
            continue
        for prefix in _WORKSPACE_PATH_PREFIXES:
            if arg.startswith(prefix):
                resolved = str(real_root / arg.lstrip("/"))
                rewritten.append(resolved)
                break
        else:
            rewritten.append(arg)
    return rewritten


_SITECUSTOMIZE_SOURCE = r'''
import json
import os
from pathlib import Path
import sys


def _roots(name):
    try:
        return [Path(item).resolve() for item in json.loads(os.environ.get(name, "[]"))]
    except Exception:
        return []


READ_ROOTS = _roots("CC_AGENT_ALLOWED_READ_ROOTS_JSON")
WRITE_ROOTS = _roots("CC_AGENT_ALLOWED_WRITE_ROOTS_JSON")
NULL_NAMES = {"NUL", "/dev/null"}


def _under(path, roots):
    try:
        resolved = Path(path).resolve()
    except Exception:
        return True
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _is_write(mode, flags):
    mode_text = str(mode or "")
    if any(token in mode_text for token in ("w", "a", "x", "+")):
        return True
    try:
        flag_value = int(flags or 0)
    except Exception:
        return False
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    return bool(flag_value & write_flags)


def _check_open(args):
    if not args:
        return
    path = args[0]
    if not isinstance(path, (str, bytes, os.PathLike)):
        return
    text_path = os.fsdecode(path)
    if text_path in NULL_NAMES:
        return
    mode = args[1] if len(args) > 1 else ""
    flags = args[2] if len(args) > 2 else 0
    if _is_write(mode, flags):
        if not _under(text_path, WRITE_ROOTS):
            raise PermissionError(f"write outside allowed workspace is blocked: {text_path}")
        return
    if not _under(text_path, READ_ROOTS):
        raise PermissionError(f"read outside allowed workspace is blocked: {text_path}")


def _audit(event, args):
    if event == "open":
        _check_open(args)
    elif event in {"subprocess.Popen", "os.system", "os.spawn", "pty.spawn"}:
        raise PermissionError("subprocess is disabled in run_python")
    elif event in {"socket.connect", "socket.bind", "socket.listen"}:
        raise PermissionError("network access is disabled in run_python")


_WORKSPACE_PATH_PREFIXES = ("outputs/", "uploads/", "tmp/")


def _rewrite_workspace_paths(command: list[str], workspace_root: Path) -> list[str]:
    """Resolve workspace-relative paths in command args to absolute paths.

    LLMs pass workspace file paths like ``outputs/report.pdf``, but the
    subprocess CWD is already the outputs directory.  This rewrites known
    workspace prefixes to absolute paths under the real workspace root.
    Only relative paths are rewritten; absolute paths pass through unchanged.
    """
    real_root = workspace_root.parent
    rewritten: list[str] = []
    for arg in command:
        if os.path.isabs(arg):
            rewritten.append(arg)
            continue
        for prefix in _WORKSPACE_PATH_PREFIXES:
            if arg.startswith(prefix):
                resolved = str(real_root / arg.lstrip("/"))
                rewritten.append(resolved)
                break
        else:
            rewritten.append(arg)
    return rewritten


sys.addaudithook(_audit)
'''
