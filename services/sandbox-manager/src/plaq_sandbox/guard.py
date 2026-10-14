"""PathGuard workspace path confinement and path traversal defense."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import urllib.parse
from typing import Union


class PathTraversalError(ValueError):
    """Raised when a path attempts to escape the designated workspace root."""
    pass


class PathGuard:
    """Enforces workspace boundary confinement, rejecting traversal attacks."""

    def __init__(self, workspace_root: Union[str, Path]) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    @staticmethod
    def resolve_safe_path(workspace_root: Union[str, Path], relative_path: str) -> Path:
        """Resolve path and verify it stays inside workspace_root."""
        if not relative_path:
            return Path(workspace_root).resolve()

        # Reject null byte injection
        if "\0" in relative_path or "\x00" in relative_path:
            raise PathTraversalError(f"Null byte detected in path: {relative_path!r}")

        # Decode URL-encoded traversal patterns recursively
        decoded = str(relative_path)
        for _ in range(3):
            new_decoded = urllib.parse.unquote(decoded)
            if new_decoded == decoded:
                break
            decoded = new_decoded

        decoded = (
            decoded.replace("%2e", ".")
            .replace("%2E", ".")
            .replace("%2f", "/")
            .replace("%2F", "/")
            .replace("%5c", "\\")
            .replace("%5C", "\\")
        )

        if "\0" in decoded or "\x00" in decoded:
            raise PathTraversalError(f"Null byte detected in path: {relative_path!r}")

        root_canonical = Path(workspace_root).resolve()
        
        # Check if decoded is absolute path on Unix or Windows
        p_decoded = Path(decoded)
        if p_decoded.is_absolute():
            target = p_decoded.resolve()
        else:
            target = (root_canonical / decoded).resolve()

        try:
            target.relative_to(root_canonical)
        except ValueError as exc:
            raise PathTraversalError(
                f"Path traversal detected: '{relative_path}' resolves to '{target}', which escapes '{root_canonical}'"
            ) from exc

        # Windows drive and casing containment defense
        if sys.platform == "win32":
            try:
                common = os.path.commonpath([str(root_canonical), str(target)])
                if Path(common).resolve() != root_canonical:
                    raise PathTraversalError(f"Path escapes workspace root: '{relative_path}'")
            except ValueError as exc:
                raise PathTraversalError(f"Drive mismatch or traversal detected: '{relative_path}'") from exc

        return target

    @classmethod
    def is_safe_path(cls, workspace_root: Union[str, Path], relative_path: str) -> bool:
        """Return True if path is safe, False otherwise."""
        try:
            cls.resolve_safe_path(workspace_root, relative_path)
            return True
        except (PathTraversalError, ValueError):
            return False

    def resolve(self, relative_path: str) -> Path:
        """Resolve path relative to this instance's workspace root."""
        return self.resolve_safe_path(self.workspace_root, relative_path)

    def is_safe(self, relative_path: str) -> bool:
        """Check if path is safe relative to this instance's workspace root."""
        return self.is_safe_path(self.workspace_root, relative_path)
