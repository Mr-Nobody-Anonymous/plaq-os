"""Process sandbox tools for shell execution and test running."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Union

from pydantic import Field
from plaq_contracts.common import PlaqBaseModel
from plaq_contracts.tool import ToolResult
from plaq_sandbox.guard import PathGuard
from plaq_sandbox.runner import ProcessRunner


class TerminalRunParams(PlaqBaseModel):
    """Parameters for terminal.run."""
    cmd: Union[str, List[str]] = Field(default="", description="Command string or arguments list")
    timeout_sec: float = Field(default=30.0, description="Execution timeout in seconds")
    cwd: Optional[str] = Field(default=None, description="Working directory relative to workspace")
    env: Optional[Dict[str, str]] = Field(default=None, description="Environment variables dictionary")

    def model_post_init(self, __context: Any) -> None:
        extra = getattr(self, "__pydantic_extra__", None) or {}
        if not self.cmd and "command" in extra:
            self.cmd = extra["command"]


class TestsRunParams(PlaqBaseModel):
    """Parameters for tests.run."""
    test_path: Optional[str] = Field(default=None, description="Test path or file to execute")
    args: List[str] = Field(default_factory=list, description="Additional pytest CLI arguments")
    timeout_sec: float = Field(default=60.0, description="Test run timeout in seconds")
    cwd: Optional[str] = Field(default=None, description="Working directory relative to workspace")

    def model_post_init(self, __context: Any) -> None:
        extra = getattr(self, "__pydantic_extra__", None) or {}
        if not self.test_path and "path" in extra:
            self.test_path = extra["path"]


def terminal_run(params: TerminalRunParams, context: Any) -> ToolResult:
    """Execute sandboxed terminal command via ProcessRunner."""
    workspace_root = getattr(context, "workspace_path", Path("."))
    if params.cwd:
        effective_cwd = PathGuard.resolve_safe_path(workspace_root, params.cwd)
    else:
        effective_cwd = Path(workspace_root).resolve()

    runner = getattr(getattr(context, "sandbox_manager", None), "runner", None) or ProcessRunner()

    res = runner.run(
        cmd=params.cmd,
        cwd=effective_cwd,
        timeout_sec=params.timeout_sec,
        env=params.env,
        raise_on_timeout=False,
    )

    if res.timed_out:
        return ToolResult(
            success=False,
            output=res.stdout,
            error=f"Execution timed out after {params.timeout_sec}s\n{res.stderr}".strip(),
            duration_ms=res.duration_ms,
            exit_code=-1,
            modified_files=[],
        )

    return ToolResult(
        success=res.success,
        output=res.stdout,
        error=res.stderr if not res.success else None,
        duration_ms=res.duration_ms,
        exit_code=res.exit_code,
        modified_files=[],
    )


def tests_run(params: TestsRunParams, context: Any) -> ToolResult:
    """Run pytest suite safely inside sandbox."""
    workspace_root = getattr(context, "workspace_path", Path("."))
    if params.cwd:
        effective_cwd = PathGuard.resolve_safe_path(workspace_root, params.cwd)
    else:
        effective_cwd = Path(workspace_root).resolve()

    runner = getattr(getattr(context, "sandbox_manager", None), "runner", None) or ProcessRunner()

    cmd = [sys.executable, "-m", "pytest"]
    if params.test_path:
        # Verify path exists safely within workspace if provided
        safe_test_target = PathGuard.resolve_safe_path(workspace_root, params.test_path)
        cmd.append(str(safe_test_target))

    if params.args:
        cmd.extend(params.args)

    res = runner.run(
        cmd=cmd,
        cwd=effective_cwd,
        timeout_sec=params.timeout_sec,
        raise_on_timeout=False,
    )

    if res.timed_out:
        return ToolResult(
            success=False,
            output=res.stdout,
            error=f"Test run timed out after {params.timeout_sec}s\n{res.stderr}".strip(),
            duration_ms=res.duration_ms,
            exit_code=-1,
            modified_files=[],
        )

    return ToolResult(
        success=res.success,
        output=res.stdout,
        error=res.stderr if not res.success else None,
        duration_ms=res.duration_ms,
        exit_code=res.exit_code,
        modified_files=[],
    )
