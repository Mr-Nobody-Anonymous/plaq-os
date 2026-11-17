"""Workspace file-tree API for the workbench sidebar."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, status

from plaq_sandbox.guard import PathGuard, PathTraversalError

router = APIRouter(prefix="/api/v1/workspace", tags=["Workspace"])

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    ".mypy_cache",
}


def _default_root() -> Path:
    env = os.environ.get("PLAQ_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def _list_tree(root: Path, rel: Path, depth: int, max_entries: int, acc: List[Dict[str, Any]]) -> None:
    if depth < 0 or len(acc) >= max_entries:
        return
    try:
        entries = sorted(rel.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return
    for child in entries:
        if len(acc) >= max_entries:
            return
        if child.name in _SKIP_DIRS or child.name.startswith("."):
            continue
        try:
            PathGuard.resolve_safe_path(root, str(child.relative_to(root)))
        except PathTraversalError:
            continue
        is_dir = child.is_dir()
        acc.append(
            {
                "name": child.name,
                "path": str(child.relative_to(root)).replace("\\", "/"),
                "kind": "dir" if is_dir else "file",
            }
        )
        if is_dir and depth > 0:
            _list_tree(root, child, depth - 1, max_entries, acc)


@router.get("/tree")
def workspace_tree(
    path: str = Query(default=""),
    depth: int = Query(default=2, ge=0, le=4),
    limit: int = Query(default=80, ge=1, le=400),
) -> Dict[str, Any]:
    base = _default_root()
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace root not found")
    try:
        start = PathGuard.resolve_safe_path(base, path or "")
    except PathTraversalError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not start.exists() or not start.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace path not found")
    entries: List[Dict[str, Any]] = []
    _list_tree(base, start, depth, limit, entries)
    rel = "" if start == base else str(start.relative_to(base)).replace("\\", "/")
    return {"root": str(base), "path": rel, "entries": entries, "truncated": len(entries) >= limit}
