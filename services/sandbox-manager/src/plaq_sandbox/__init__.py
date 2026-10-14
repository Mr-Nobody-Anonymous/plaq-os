"""Plaq-OS Sandbox Manager: PathGuard, Subprocess Runner & Git Worktrees."""

from .guard import PathGuard, PathTraversalError
from .manager import SandboxManager
from .runner import ProcessResult, ProcessRunner, kill_process_tree, run_command
from .worktree import WorktreeError, WorktreeInfo, WorktreeManager

__version__ = "0.1.0"

__all__ = [
    "PathGuard",
    "PathTraversalError",
    "ProcessRunner",
    "ProcessResult",
    "kill_process_tree",
    "run_command",
    "WorktreeManager",
    "WorktreeInfo",
    "WorktreeError",
    "SandboxManager",
]
