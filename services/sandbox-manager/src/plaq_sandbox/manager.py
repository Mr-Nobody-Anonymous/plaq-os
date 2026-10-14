"""SandboxManager unified platform façade."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

from .guard import PathGuard
from .runner import ProcessResult, ProcessRunner
from .worktree import WorktreeInfo, WorktreeManager


class SandboxManager:
    """Unified façade for PathGuard, SubprocessRunner, and Git Worktrees."""

    def __init__(
        self,
        base_worktree_dir: str = ".worktrees",
        default_timeout_sec: float = 30.0,
    ) -> None:
        self.runner = ProcessRunner(default_timeout_sec=default_timeout_sec)
        self.worktree_mgr = WorktreeManager(base_worktree_dir=base_worktree_dir)

    def resolve_safe_path(self, workspace_root: Union[str, Path], relative_path: str) -> Path:
        """Resolve path and verify workspace boundary confinement."""
        return PathGuard.resolve_safe_path(workspace_root, relative_path)

    def run_command(
        self,
        cmd: Union[List[str], str],
        cwd: Optional[Union[str, Path]] = None,
        timeout_sec: float = 30.0,
        env: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
        raise_on_timeout: bool = False,
    ) -> ProcessResult:
        """Execute sandboxed subprocess with timeout and process-tree termination."""
        return self.runner.run(
            cmd=cmd,
            cwd=cwd,
            timeout_sec=timeout_sec,
            env=env,
            input_data=input_data,
            raise_on_timeout=raise_on_timeout,
        )

    def create_worktree(
        self,
        repo_path: Union[str, Path],
        task_id: str,
        branch_name: Optional[str] = None,
    ) -> str:
        """Create isolated git worktree for task."""
        return self.worktree_mgr.create_worktree(repo_path, task_id, branch_name=branch_name)

    def cleanup_worktree(self, repo_path: Union[str, Path], task_id: str) -> None:
        """Clean up isolated git worktree for task."""
        self.worktree_mgr.cleanup_worktree(repo_path, task_id)

    def get_worktree_status(
        self,
        repo_path: Union[str, Path],
        task_id: str,
    ) -> Optional[WorktreeInfo]:
        """Query worktree metadata."""
        return self.worktree_mgr.get_worktree_status(repo_path, task_id)

    def list_worktrees(self, repo_path: Union[str, Path]) -> List[WorktreeInfo]:
        """List active worktrees."""
        return self.worktree_mgr.list_worktrees(repo_path)
