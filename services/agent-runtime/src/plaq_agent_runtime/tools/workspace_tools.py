"""Workspace filesystem tools using PathGuard confinement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Optional

from pydantic import Field
from plaq_contracts.common import PlaqBaseModel
from plaq_contracts.tool import ToolResult
from plaq_sandbox.guard import PathGuard


class WorkspaceListParams(PlaqBaseModel):
    """Parameters for workspace.list."""
    path: str = Field(default=".", description="Relative directory path to list")
    recursive: bool = Field(default=False, description="Whether to recurse into subdirectories")
    max_depth: int = Field(default=3, description="Maximum recursion depth")
    include_hidden: bool = Field(default=False, description="Whether to include hidden files")


class WorkspaceReadParams(PlaqBaseModel):
    """Parameters for workspace.read."""
    path: str = Field(default="", description="Relative file path to read")
    start_line: Optional[int] = Field(default=None, description="1-indexed starting line")
    end_line: Optional[int] = Field(default=None, description="1-indexed ending line")
    encoding: str = Field(default="utf-8", description="File text encoding")


class WorkspaceWriteParams(PlaqBaseModel):
    """Parameters for workspace.write."""
    path: str = Field(default="", description="Relative file path to write")
    content: str = Field(default="", description="Content to write")
    encoding: str = Field(default="utf-8", description="File text encoding")
    create_parents: bool = Field(default=True, description="Create missing parent directories")


class WorkspacePatchParams(PlaqBaseModel):
    """Parameters for workspace.patch."""
    path: str = Field(default="", description="Relative file path to patch")
    target: Optional[str] = Field(default=None, description="Target substring to replace")
    replacement: Optional[str] = Field(default=None, description="Replacement substring")
    diff: Optional[str] = Field(default=None, description="Unified diff string to apply")
    allow_multiple: bool = Field(default=False, description="Allow replacing multiple occurrences")

    def model_post_init(self, __context: Any) -> None:
        # Check if 'file' or 'target_file' was passed
        extra = getattr(self, "__pydantic_extra__", None) or {}
        if not self.path:
            if "file" in extra:
                self.path = extra["file"]
            elif "target_file" in extra:
                self.path = extra["target_file"]


def workspace_list(params: WorkspaceListParams, context: Any) -> ToolResult:
    """List directory contents within workspace boundaries."""
    t0 = time.perf_counter()
    workspace_root = getattr(context, "workspace_path", Path("."))
    target_dir = PathGuard.resolve_safe_path(workspace_root, params.path)

    if not target_dir.exists():
        return ToolResult(
            success=False,
            output="",
            error=f"Directory does not exist: {params.path}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )

    if not target_dir.is_dir():
        return ToolResult(
            success=False,
            output="",
            error=f"Path is not a directory: {params.path}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )

    entries = []
    try:
        def scan(cur_dir: Path, current_depth: int):
            if current_depth > params.max_depth:
                return
            for item in sorted(cur_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if not params.include_hidden and item.name.startswith("."):
                    continue
                rel_path = str(item.relative_to(target_dir)).replace("\\", "/")
                is_directory = item.is_dir()
                size_bytes = 0
                if not is_directory:
                    try:
                        size_bytes = item.stat().st_size
                    except Exception:
                        pass
                entries.append({
                    "name": item.name,
                    "path": rel_path,
                    "is_dir": is_directory,
                    "size_bytes": size_bytes,
                })
                if is_directory and params.recursive:
                    scan(item, current_depth + 1)

        scan(target_dir, 1)
        output_str = json.dumps(entries, indent=2)
        return ToolResult(
            success=True,
            output=output_str,
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=0,
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


def workspace_read(params: WorkspaceReadParams, context: Any) -> ToolResult:
    """Read file content within workspace boundaries."""
    t0 = time.perf_counter()
    workspace_root = getattr(context, "workspace_path", Path("."))
    file_path = PathGuard.resolve_safe_path(workspace_root, params.path)

    if not file_path.exists():
        return ToolResult(
            success=False,
            output="",
            error=f"File not found: {params.path}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )

    if file_path.is_dir():
        return ToolResult(
            success=False,
            output="",
            error=f"Path is a directory, not a file: {params.path}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )

    try:
        content = file_path.read_text(encoding=params.encoding)
        if params.start_line is not None or params.end_line is not None:
            lines = content.splitlines(keepends=True)
            start = max(1, params.start_line or 1) - 1
            end = params.end_line if params.end_line is not None else len(lines)
            content = "".join(lines[start:end])

        return ToolResult(
            success=True,
            output=content,
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=0,
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


def workspace_write(params: WorkspaceWriteParams, context: Any) -> ToolResult:
    """Write or overwrite file within workspace boundaries."""
    t0 = time.perf_counter()
    workspace_root = Path(getattr(context, "workspace_path", ".")).resolve()
    file_path = PathGuard.resolve_safe_path(workspace_root, params.path)

    try:
        if params.create_parents:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        content_bytes = params.content.encode(params.encoding)
        file_path.write_bytes(content_bytes)
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        rel_path = str(file_path.relative_to(workspace_root)).replace("\\", "/")

        return ToolResult(
            success=True,
            output=f"Wrote {len(content_bytes)} bytes, sha256={sha256}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=0,
            modified_files=[rel_path],
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


def workspace_patch(params: WorkspacePatchParams, context: Any) -> ToolResult:
    """Apply substring replacement or unified diff patch to a file."""
    t0 = time.perf_counter()
    workspace_root = Path(getattr(context, "workspace_path", ".")).resolve()
    file_path = PathGuard.resolve_safe_path(workspace_root, params.path)

    if not file_path.exists():
        return ToolResult(
            success=False,
            output="",
            error=f"File not found for patching: {params.path}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )

    try:
        content = file_path.read_text(encoding="utf-8")

        if params.target is not None and params.replacement is not None:
            if params.target not in content:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Target substring not found in file: {params.target!r}",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    exit_code=1,
                    modified_files=[],
                )
            count = content.count(params.target)
            if count > 1 and not params.allow_multiple:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Target substring found multiple ({count}) times but allow_multiple=False",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    exit_code=1,
                    modified_files=[],
                )
            new_content = content.replace(params.target, params.replacement)
        elif params.diff is not None:
            # Apply each hunk against its declared context; never append on mismatch.
            import re
            original = content.splitlines(keepends=True)
            diff_lines = params.diff.splitlines(keepends=True)
            result = []
            cursor = 0
            i = 0
            hunks = 0
            while i < len(diff_lines):
                if not diff_lines[i].startswith("@@"):
                    i += 1
                    continue
                match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", diff_lines[i])
                if not match:
                    raise ValueError("Invalid patch hunk header")
                old_start = int(match.group(1))
                old_count = int(match.group(2) or 1)
                new_count = int(match.group(4) or 1)
                target = old_start if old_count == 0 else old_start - 1
                if target < cursor or target > len(original):
                    raise ValueError("Patch hunk position is invalid")
                result.extend(original[cursor:target])
                cursor = target
                removed = added = 0
                i += 1
                while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                    line = diff_lines[i]
                    if line.startswith(("--- ", "+++ ")):
                        break
                    if line.startswith("\\ No newline"):
                        raise ValueError("Patch without final newline is not supported")
                    if not line or line[0] not in " +-":
                        raise ValueError("Invalid patch hunk line")
                    prefix, text = line[0], line[1:]
                    if prefix in " -":
                        if cursor >= len(original) or original[cursor] != text:
                            raise ValueError("Patch context does not match file")
                        cursor += 1
                        removed += 1
                    if prefix in " +":
                        result.append(text)
                        added += 1
                    i += 1
                if removed != old_count or added != new_count:
                    raise ValueError("Patch hunk line counts do not match")
                hunks += 1
            if not hunks:
                raise ValueError("Patch contains no hunks")
            result.extend(original[cursor:])
            new_content = "".join(result)
        else:
            return ToolResult(
                success=False,
                output="",
                error="Must provide either (target, replacement) or diff",
                duration_ms=(time.perf_counter() - t0) * 1000,
                exit_code=1,
                modified_files=[],
            )

        content_bytes = new_content.encode("utf-8")
        file_path.write_bytes(content_bytes)
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        rel_path = str(file_path.relative_to(workspace_root)).replace("\\", "/")

        return ToolResult(
            success=True,
            output=f"Patched {params.path}, sha256={sha256}",
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=0,
            modified_files=[rel_path],
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
