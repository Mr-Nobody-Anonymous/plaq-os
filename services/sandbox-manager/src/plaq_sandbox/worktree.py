"""Git Worktree isolation manager for sandboxed task file mutations."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Union

from plaq_contracts.common import PlaqBaseModel
from .guard import PathGuard, PathTraversalError


class WorktreeError(RuntimeError):
    """Raised when git worktree operations fail."""
    pass


class WorktreeInfo(PlaqBaseModel):
    """Metadata regarding an active git worktree."""

    task_id: str
    path: str
    branch: str
    head_commit: Optional[str] = None
    is_locked: bool = False
    exists: bool = True


def _remove_readonly(func, path, exc_info):
    """Error handler for shutil.rmtree on Windows read-only git metadata."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


class WorktreeManager:
    """Manages isolated .worktrees/<task_id> git worktrees."""

    SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

    def __init__(self, base_worktree_dir: str = ".worktrees") -> None:
        self.base_worktree_dir = base_worktree_dir

    def _validate_task_id(self, task_id: str) -> None:
        if not task_id or not self.SAFE_TASK_ID_RE.match(task_id):
            raise WorktreeError(f"Invalid task_id for worktree isolation: {task_id!r}")

    def is_git_repo(self, repo_path: Union[str, Path]) -> bool:
        """Verify whether repo_path is inside a git repository."""
        canonical = Path(repo_path).resolve()
        res = subprocess.run(
            ["git", "-C", str(canonical), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"

    def create_worktree(
        self,
        repo_path: Union[str, Path],
        task_id: str,
        branch_name: Optional[str] = None,
        commit: str = "HEAD",
    ) -> str:
        self._validate_task_id(task_id)
        canonical_repo = Path(repo_path).resolve()

        if not self.is_git_repo(canonical_repo):
            raise WorktreeError(f"Directory is not a valid git repository: {canonical_repo}")

        # Compute worktree path safely within repo
        wt_path = PathGuard.resolve_safe_path(canonical_repo, f"{self.base_worktree_dir}/{task_id}")

        # Ensure base .worktrees/.gitignore ignores all worktree contents
        worktrees_root = canonical_repo / self.base_worktree_dir
        worktrees_root.mkdir(parents=True, exist_ok=True)
        gitignore_file = worktrees_root / ".gitignore"
        if not gitignore_file.exists():
            try:
                gitignore_file.write_text("*\n!.gitignore\n", encoding="utf-8")
            except Exception:
                pass

        # Cleanup any lingering worktree at this path
        if wt_path.exists():
            self.cleanup_worktree(canonical_repo, task_id)

        branch = branch_name or f"task/{task_id}"

        # Execute git worktree add with branch creation / force-reset
        cmd = ["git", "-C", str(canonical_repo), "worktree", "add", "-B", branch, str(wt_path), commit]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise WorktreeError(f"Failed to create git worktree: {proc.stderr.strip() or proc.stdout.strip()}")

        return str(wt_path)

    def get_worktree_status(self, repo_path: Union[str, Path], task_id: str) -> Optional[WorktreeInfo]:
        self._validate_task_id(task_id)
        all_trees = self.list_worktrees(repo_path)
        for wt in all_trees:
            if wt.task_id == task_id:
                return wt
        return None

    def list_worktrees(self, repo_path: Union[str, Path]) -> List[WorktreeInfo]:
        canonical_repo = Path(repo_path).resolve()
        if not self.is_git_repo(canonical_repo):
            return []

        proc = subprocess.run(
            ["git", "-C", str(canonical_repo), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return []

        worktrees: List[WorktreeInfo] = []
        current: Dict[str, Any] = {}

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                if "path" in current:
                    p = Path(current["path"]).resolve()
                    task_id = p.name
                    branch = current.get("branch", "").replace("refs/heads/", "")
                    worktrees.append(
                        WorktreeInfo(
                            task_id=task_id,
                            path=str(p),
                            branch=branch,
                            head_commit=current.get("HEAD"),
                            is_locked=current.get("locked", False),
                            exists=p.exists(),
                        )
                    )
                current = {}
                continue

            parts = line.split(" ", 1)
            key = parts[0]
            val = parts[1] if len(parts) > 1 else True
            if key == "worktree":
                current["path"] = val
            elif key == "HEAD":
                current["HEAD"] = val
            elif key == "branch":
                current["branch"] = val
            elif key == "locked":
                current["locked"] = True

        if "path" in current:
            p = Path(current["path"]).resolve()
            worktrees.append(
                WorktreeInfo(
                    task_id=p.name,
                    path=str(p),
                    branch=current.get("branch", "").replace("refs/heads/", ""),
                    head_commit=current.get("HEAD"),
                    is_locked=current.get("locked", False),
                    exists=p.exists(),
                )
            )

        return worktrees

    def cleanup_worktree(
        self,
        repo_path: Union[str, Path],
        task_id: str,
        delete_branch: bool = True,
    ) -> None:
        self._validate_task_id(task_id)
        canonical_repo = Path(repo_path).resolve()
        if not self.is_git_repo(canonical_repo):
            return

        wt_path = canonical_repo / self.base_worktree_dir / task_id

        # 1. Attempt git worktree remove with retry for Windows file locks
        for attempt in range(3):
            proc = subprocess.run(
                ["git", "-C", str(canonical_repo), "worktree", "remove", "--force", str(wt_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                break
            time.sleep(0.2 * (attempt + 1))

        # 2. Prune git worktree administrative entries
        subprocess.run(
            ["git", "-C", str(canonical_repo), "worktree", "prune"],
            capture_output=True,
            check=False,
        )

        # 3. Clean up directory if still lingering on disk
        if wt_path.exists():
            shutil.rmtree(wt_path, onerror=_remove_readonly)

        # 4. Optional branch deletion
        if delete_branch:
            branch = f"task/{task_id}"
            subprocess.run(
                ["git", "-C", str(canonical_repo), "branch", "-D", branch],
                capture_output=True,
                check=False,
            )
