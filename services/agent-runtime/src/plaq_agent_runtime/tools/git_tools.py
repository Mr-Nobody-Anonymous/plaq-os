"""Git tools for repository and isolated worktree operations."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
from typing import Any, List, Optional

from pydantic import Field
from plaq_contracts.common import PlaqBaseModel
from plaq_contracts.tool import ToolResult
from plaq_sandbox.guard import PathGuard


class GitDiffParams(PlaqBaseModel):
    """Parameters for git.diff."""
    target: Optional[str] = Field(default=None, description="Specific file or path to diff")
    cached: bool = Field(default=False, description="Diff staged changes (--cached)")
    worktree_path: Optional[str] = Field(default=None, description="Isolated worktree directory path")
    commit: Optional[str] = Field(default=None, description="Base commit or branch to diff against")


class GitBranchParams(PlaqBaseModel):
    """Parameters for git.branch."""
    action: str = Field(default="list", description="Action: 'list', 'current', or 'create'")
    branch_name: Optional[str] = Field(default=None, description="Branch name for 'create' action")
    worktree_path: Optional[str] = Field(default=None, description="Isolated worktree directory path")


def git_diff(params: GitDiffParams, context: Any) -> ToolResult:
    """Run git diff in workspace or worktree."""
    t0 = time.perf_counter()
    workspace_root = getattr(context, "workspace_path", Path("."))
    if params.worktree_path:
        cwd = PathGuard.resolve_safe_path(workspace_root, params.worktree_path)
    else:
        cwd = Path(workspace_root).resolve()

    cmd = ["git", "diff"]
    if params.cached:
        cmd.append("--cached")
    if params.commit:
        cmd.append(params.commit)
    if params.target:
        cmd.extend(["--", params.target])

    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
        return ToolResult(
            success=proc.returncode == 0,
            output=proc.stdout,
            error=proc.stderr if proc.returncode != 0 else None,
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=proc.returncode,
            modified_files=[],
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            output="",
            error=str(exc),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )


def git_branch(params: GitBranchParams, context: Any) -> ToolResult:
    """List, show current, or create git branch."""
    t0 = time.perf_counter()
    workspace_root = getattr(context, "workspace_path", Path("."))
    if params.worktree_path:
        cwd = PathGuard.resolve_safe_path(workspace_root, params.worktree_path)
    else:
        cwd = Path(workspace_root).resolve()

    if params.action == "current":
        cmd = ["git", "branch", "--show-current"]
    elif params.action == "create":
        if not params.branch_name:
            return ToolResult(
                success=False,
                output="",
                error="branch_name is required when action='create'",
                duration_ms=(time.perf_counter() - t0) * 1000,
                exit_code=1,
                modified_files=[],
            )
        cmd = ["git", "branch", params.branch_name]
    else:
        cmd = ["git", "branch", "--list"]

    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
        return ToolResult(
            success=proc.returncode == 0,
            output=proc.stdout.strip(),
            error=proc.stderr if proc.returncode != 0 else None,
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=proc.returncode,
            modified_files=[],
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            output="",
            error=str(exc),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )
