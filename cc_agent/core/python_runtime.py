from __future__ import annotations

from typing import Any

from .messages import ToolResult
from .workspace.execution_runtime import WorkspaceExecutionRuntime


class PythonCodeRuntime:
    def __init__(
        self,
        workspace: Any,
        timeout_seconds: int = 120,
        max_timeout_seconds: int = 600,
        max_output_chars: int = 8000,
    ):
        self.runtime = WorkspaceExecutionRuntime(
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            max_timeout_seconds=max_timeout_seconds,
            max_output_chars=max_output_chars,
        )

    def run(
        self,
        code: str,
        input_file_ids: list[str] | None = None,
        args: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> ToolResult:
        return self.runtime.run_python(
            code,
            input_file_ids=input_file_ids,
            args=args,
            timeout_seconds=timeout_seconds,
        )
