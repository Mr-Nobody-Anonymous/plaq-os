# Investigation & Design Report: Sandbox Manager (`plaq-sandbox`)

**Explorer**: `explorer_m3_1`  
**Milestone**: M3 — Sandbox Manager & Agent Runtime Engine  
**Project Root**: `C:\Users\hp\Desktop\plaq-os`  
**Target Package**: `services/sandbox-manager` (`plaq-sandbox`)  
**Target Features**: Feature 13 (PathGuard Confinement), Feature 14 (Subprocess Sandbox Runner), Feature 15 (Git Worktree Isolation)  

---

## 1. Observation

### 1.1 Requirements Specification (`ORIGINAL_REQUEST.md § R3`)
- **§ R3. Plaq Agent Runtime, Tool Registry & Sandbox Boundaries**:
  - Typed tool registry with strict permission tiers:
    - `workspace.list` & `workspace.read` (`read_only`)
    - `workspace.patch` & `workspace.write` (`workspace_write`)
    - `git.diff` & `git.branch` (`git_isolated` worktrees)
    - `terminal.run` & `tests.run` (`process_sandbox` with execution timeouts)
    - `quantum.compile`, `quantum.estimate`, `quantum.simulate` (`quantum_engine`)
    - `artifacts.publish` (`privileged`)
  - Confinement of workspace mutations, path traversal defenses, process execution timeouts, and git worktrees.

### 1.2 Interface Contract in `PROJECT.md § 3`
From `PROJECT.md` lines 247-253:
```python
### 3. services/sandbox-manager <-> services/agent-runtime
- SandboxManager:
  - resolve_safe_path(workspace_root: str, relative_path: str) -> Path  # Raises PathTraversalError if escapes
  - run_command(cmd: List[str], cwd: str, timeout_sec: float = 30.0, env: Optional[dict] = None) -> ProcessResult
  - create_worktree(repo_path: str, task_id: str) -> str
  - cleanup_worktree(repo_path: str, task_id: str) -> None
```

### 1.3 Test Suite Contracts & Baselines
Direct inspection of `tests/e2e/test_tier1_feature.py` and `tests/e2e/test_tier2_boundary.py` established the exact contract tests:
1. **Feature 8: Sandbox PathGuard (`tests/e2e/test_tier1_feature.py:555-588`)**:
   - `test_f8_01_safe_relative_path_resolution`: Valid relative path resolves within workspace root.
   - `test_f8_02_reject_parent_directory_traversal`: `../../../etc/passwd` raises `PathTraversalError`.
   - `test_f8_03_reject_absolute_path_escape`: System root (`C:\Windows` or `/etc`) raises `PathTraversalError`.
   - `test_f8_04_reject_null_byte_injection`: `valid_dir/safe_file.txt\0/escape.sh` raises `PathTraversalError` matching `"Null byte"`.
   - `test_f8_05_nested_safe_directory_within_workspace`: Nested path `a/b/c/d/e/circuit.qasm` resolves safely within workspace root.
2. **Feature 9: Subprocess Runner (`tests/e2e/test_tier1_feature.py:594-637`)**:
   - `test_f9_01_successful_command_execution`: Captures returncode 0 and stdout (`plaq_sandbox_ok`).
   - `test_f9_02_failing_command_captures_stderr`: Captures non-zero exit code and stderr (`fatal_error`).
   - `test_f9_03_timeout_triggers_timeout_expired`: Exceeding timeout raises `subprocess.TimeoutExpired`.
   - `test_f9_04_environment_variable_isolation`: Custom environment variables are passed to child.
   - `test_f9_05_process_tree_termination`: Spawning child subprocesses terminates completely without hanging.
3. **Boundary Group 1: Path Traversal Defenses (`tests/e2e/test_tier2_boundary.py:42-122`)**:
   - `test_b1_01_multilevel_parent_traversal`: Deep traversal (`../` * 15 + `Windows/System32/calc.exe`) rejected.
   - `test_b1_02_encoded_parent_traversal`: URL encoded traversal (`%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd`) rejected.
   - `test_b1_03_absolute_system_drive_escape`: Absolute system drive paths outside workspace blocked.
   - `test_b1_04_embedded_null_byte_attack`: Embedded null byte `\x00` in relative path rejected with `"Null byte"`.
   - `test_b1_05_symlink_pointing_outside_workspace`: Symlink escaping workspace rejected upon resolution (skipped on Windows without admin privs).
   - `test_b1_06_double_url_encoded_traversal`: Double-encoded (`%252e%252e%252f`) rejected.
   - `test_b1_07_backslash_windows_traversal`: Windows backslash traversal (`..\..\..\Windows\win.ini`) rejected.
   - `test_b1_08_mixed_slashes_traversal`: Mixed slashes (`..\/\..\/\..\system`) rejected.
   - `test_b1_09_relative_path_with_current_dir_dots`: `./././../../etc/hosts` rejected.
   - `test_b1_10_safe_path_with_redundant_current_dir`: `./src/./app.py` resolves safely.
   - `test_b1_11_trailing_slash_confinement`: `build/output/` resolves safely.
4. **Boundary Group 4: Process Termination (`tests/e2e/test_tier2_boundary.py:392-493`)**:
   - `test_b4_01_short_timeout_terminates_promptly`: 0.2s timeout aborts in under 1.0s.
   - `test_b4_02_spawned_grandchild_process_termination`: Grandchild processes are cleanly terminated.
   - `test_b4_03_zero_or_negative_timeout_rejected`: Timeout `<= 0` raises `ValueError` matching `"positive"`.
   - `test_b4_04_infinite_stdout_stream_process`: Large stdout stream handled without deadlock or OOM.
   - `test_b4_05_exit_code_indicates_timeout_failure`: Timeout records `TimeoutExpired` with timeout value.
   - `test_b4_06_timeout_during_heavy_cpu_work`: CPU busy loop terminates promptly on timeout.
   - `test_b4_07_nested_subshell_timeout`: Subshell (`cmd /c ping ...`) terminates on timeout.
   - `test_b4_08_non_zero_exit_code_range`: Common exit codes (1, 2, 42) captured accurately.
   - `test_b4_09_stderr_only_execution`: Captures stderr cleanly with empty stdout.
   - `test_b4_10_large_stdin_input`: Passing large stdin executes without deadlocking.
   - `test_b4_11_working_directory_isolation`: Executing in `cwd` does not mutate parent process `os.getcwd()`.

### 1.4 Current Repository State
- Command `python -c "import plaq_sandbox"` fails with `ModuleNotFoundError: No module named 'plaq_sandbox'`.
- Directory `services/sandbox-manager` contains only `.gitkeep`.
- `tests/e2e/conftest.py` already includes `PROJECT_ROOT / "services" / "sandbox-manager" / "src"` in `sys.path`.
- Currently, `conftest.py` has a fallback `PathGuard` and `PathTraversalError` class so tests run, but the official service implementation in `services/sandbox-manager` does not yet exist.

---

## 2. Logic Chain

```
[Requirement § R3 + Interface Contract § 3]
                   │
                   ▼
[Package: services/sandbox-manager (plaq-sandbox)]
  ├── guard.py    : PathGuard, PathTraversalError
  ├── runner.py   : ProcessRunner, ProcessResult, kill_process_tree, run_command
  ├── worktree.py : WorktreeManager, WorktreeInfo, WorktreeError
  ├── manager.py  : SandboxManager (Unified Façade)
  └── __init__.py : Clean exports
```

### 2.1 PathGuard Design Logic
1. **Null-Byte Injection**: Attackers insert `\0` or `\x00` to truncate path strings in C-based filesystem APIs. `PathGuard` must explicitly inspect raw input for `"\0"` and raise `PathTraversalError(f"Null byte detected in path: {relative_path!r}")`.
2. **Defensive URL Unquoting**: Attackers encode traversal tokens as `%2e` (`.`), `%2f` (`/`), `%5c` (`\`), or double-encode as `%252e`. Unquoting recursively (up to 3 iterations) and replacing canonical hex characters ensures hidden traversal sequences are fully normalized before resolution.
3. **Canonical Path Resolution**: 
   - `root_canonical = Path(workspace_root).resolve()`
   - `target = (root_canonical / decoded).resolve()`
   - `target.resolve()` evaluates symlinks and resolves all relative segments (`..`, `.`).
4. **Strict Containment Verification**:
   - `target.relative_to(root_canonical)` raises `ValueError` if `target` escapes `root_canonical`.
   - On Windows, paths must also be verified against common path prefix `os.path.commonpath([str(root_canonical), str(target)]) == str(root_canonical)` to prevent case-mismatch anomalies across drive letters.

### 2.2 Subprocess Runner & Windows Process-Tree Termination Logic
1. **The Windows Process Tree Problem**:
   On Windows, terminating a parent process via standard `proc.terminate()` or `proc.kill()` calls `TerminateProcess(hProcess)`. It does NOT terminate child or grandchild processes spawned by that process. Any grandchild keeps running in the background, locking files, holding open console handles, and consuming CPU/RAM.
2. **Deterministic Termination Strategy**:
   - **Windows**: Use `taskkill /F /T /PID <pid>`.
     - `/F`: Forcefully terminate process.
     - `/T`: Terminate the specified process and all child processes spawned by it.
     - `/PID <pid>`: Target process identifier.
     - Must be executed with `check=False` and suppression of `stdout/stderr` because if the process exited milliseconds earlier, `taskkill` exits with code 128 (process not found), which is normal and safe.
   - **Unix (POSIX)**: Use `preexec_fn=os.setsid` at spawn time, and `os.killpg(os.getpgid(pid), signal.SIGKILL)` at termination time.
3. **Deadlock-Free I/O Communication**:
   - Using `proc.communicate(input=input_data, timeout=timeout_sec)` ensures stdout and stderr are read in parallel threads/buffers without blocking when buffer size exceeds 64KB (resolving `test_b4_04` and `test_b4_10`).
4. **Timeout Enforcement & Result Format**:
   - If `timeout_sec <= 0`: Raise `ValueError("Timeout must be positive, got {timeout_sec}")`.
   - On `subprocess.TimeoutExpired`:
     1. Invoke `kill_process_tree(proc.pid)`.
     2. Attempt secondary drain `proc.communicate(timeout=0.5)` to salvage whatever output was generated.
     3. Either return `ProcessResult(exit_code=-1, timed_out=True, stderr=...)` or re-raise `subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_sec)` depending on `raise_on_timeout` flag.
5. **Environment Preservation**:
   - An isolated environment cannot simply be `{}` on Windows. Windows processes require `SystemRoot` (usually `C:\Windows`), `COMSPEC`, `PATH`, and `TEMP` to dynamically link runtime libraries (`msvcrt.dll`, `kernel32.dll`). Stripping these causes Python subprocesses to fail immediately with DLL initialization failure (0xC0000142). `ProcessRunner` must ensure baseline Windows system variables are preserved when creating isolated execution environments.

### 2.3 Git Worktree Isolation Logic
1. **Location & Naming**:
   - Worktree root: `<repo_path>/.worktrees/<task_id>`
   - Isolated branch: `task/<task_id>`
   - Command: `git -C <repo_path> worktree add -B task/<task_id> <wt_path> HEAD`
   - Using `-B` forces creation or reset of the branch, allowing idempotency and recovery if a previous run failed mid-execution.
2. **Worktree Status & Query**:
   - `git -C <repo_path> worktree list --porcelain` returns structured output:
     ```text
     worktree C:/repo/.worktrees/task-123
     HEAD a1b2c3d4...
     branch refs/heads/task/task-123
     ```
   - Parsing porcelain output allows `get_worktree_status(repo_path, task_id)` and `list_worktrees(repo_path)`.
3. **Windows File Lock Recovery in Cleanup**:
   - When deleting `.worktrees/<task_id>` on Windows, file handles may linger (e.g. anti-malware scanner, file indexer, delayed child process termination).
   - If `git worktree remove --force` fails:
     1. Retry up to 3 times with 0.2s exponential backoff.
     2. Execute `git worktree prune`.
     3. If directory remains on disk, remove via `shutil.rmtree` with custom error handler `_on_rm_error` that unsets read-only flags (`os.chmod(path, stat.S_IWRITE)`). Git marks pack files and index objects as read-only, which causes standard Windows `os.remove` to throw `PermissionError`.
4. **Repository Protection**:
   - Ensure `<repo_path>/.worktrees/.gitignore` exists containing `*` so created worktrees are never tracked by the host repository.

---

## 3. Caveats & Edge Conditions

1. **Windows File Locking Dynamics**:
   - If a background process spawned inside a worktree is still alive, Windows will lock the executable file and directory, preventing `worktree remove`. `ProcessRunner.kill_process_tree()` must be invoked before attempting worktree teardown.
2. **Read-Only Git Attributes**:
   - On Windows, `git` creates read-only files in `.git/objects/pack/`. If `shutil.rmtree` is called on a worktree without handling `stat.S_IWRITE`, Windows raises `PermissionError: [WinError 5] Access is denied`. The custom error handler is mandatory.
3. **Windows Symlink Privileges**:
   - In Windows, creating symbolic links requires `SeCreateSymbolicLinkPrivilege` (Developer Mode or Admin privileges). `test_b1_05` properly skips if privileges are absent. `PathGuard` must safely handle symlink resolution via `.resolve()` regardless of whether symlinks were created locally or pre-existing.
4. **Windows Path Length Limits (MAX_PATH = 260)**:
   - Deeply nested directories inside `.worktrees/<task_id>/...` can exceed 260 characters if `task_id` is excessively long. `task_id` must be validated to contain only safe alphanumeric characters and hyphens, preventing path inflation.
5. **Windows Line Endings (`\r\n`) vs Unix (`\n`)**:
   - Command outputs captured via `text=True` in `subprocess.Popen` are translated to `\n` by Python universal newlines. Any binary execution should preserve raw bytes when `text=False`.

---

## 4. Conclusion & Architectural Specification

The package `plaq-sandbox` (`services/sandbox-manager`) should be implemented with the following module structure:

```text
services/sandbox-manager/
├── pyproject.toml
├── README.md
└── src/
    └── plaq_sandbox/
        ├── __init__.py
        ├── guard.py
        ├── runner.py
        ├── worktree.py
        └── manager.py
```

### Complete Code Specifications for the Worker

#### Specification 1: `services/sandbox-manager/pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "plaq-sandbox"
version = "0.1.0"
description = "Plaq-OS Process Execution Sandbox, Path Confinement & Git Worktree Isolation"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0.0",
    "plaq-contracts>=0.1.0",
]

[tool.setuptools.packages.find]
where = ["src"]
```

#### Specification 2: `src/plaq_sandbox/guard.py`
```python
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
        decoded = relative_path
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
        target = (root_canonical / decoded).resolve()

        try:
            target.relative_to(root_canonical)
        except ValueError as exc:
            raise PathTraversalError(
                f"Path traversal detected: '{relative_path}' resolves to '{target}', which escapes '{root_canonical}'"
            ) from exc

        # Windows case-insensitive and drive-letter defense
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
```

#### Specification 3: `src/plaq_sandbox/runner.py`
```python
"""Subprocess execution runner with timeout support and Windows process-tree termination."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Union

from plaq_contracts.common import PlaqBaseModel
from plaq_contracts.tool import ToolResult


class ProcessResult(PlaqBaseModel):
    """Result of sandboxed process execution."""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    timed_out: bool = False
    pid: Optional[int] = None

    @property
    def returncode(self) -> int:
        return self.exit_code

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        return self.stdout

    def to_tool_result(self, modified_files: Optional[List[str]] = None) -> ToolResult:
        return ToolResult(
            success=self.success,
            output=self.stdout,
            error=self.stderr if not self.success else None,
            duration_ms=self.duration_ms,
            exit_code=self.exit_code,
            modified_files=modified_files or [],
        )


def kill_process_tree(pid: int) -> None:
    """Terminate a process and all its child/grandchild processes."""
    if not pid:
        return

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass
    else:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass


class ProcessRunner:
    """Sandboxed subprocess runner with timeout enforcement and process-tree termination."""

    # Essential Windows environment keys required for C runtime DLLs
    WINDOWS_ESSENTIAL_ENV = {
        "SystemRoot",
        "SYSTEMROOT",
        "SystemDrive",
        "SYSTEMDRIVE",
        "COMSPEC",
        "ComSpec",
        "PATH",
        "Path",
        "PATHEXT",
        "TEMP",
        "TMP",
    }

    def __init__(
        self,
        default_cwd: Optional[Union[str, Path]] = None,
        default_timeout_sec: float = 30.0,
    ) -> None:
        self.default_cwd = Path(default_cwd).resolve() if default_cwd else None
        self.default_timeout_sec = default_timeout_sec

    def _prepare_env(self, env: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if env is None:
            return None

        merged = dict(env)
        if sys.platform == "win32":
            # Preserve essential Windows variables if not specified
            for key in self.WINDOWS_ESSENTIAL_ENV:
                if key not in merged and key in os.environ:
                    merged[key] = os.environ[key]
        return merged

    def run(
        self,
        cmd: Union[List[str], str],
        cwd: Optional[Union[str, Path]] = None,
        timeout_sec: Optional[float] = 30.0,
        env: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
        text: bool = True,
        raise_on_timeout: bool = False,
    ) -> ProcessResult:
        if timeout_sec is not None and timeout_sec <= 0:
            raise ValueError(f"Timeout must be positive, got {timeout_sec}")

        effective_timeout = timeout_sec if timeout_sec is not None else self.default_timeout_sec
        effective_cwd = Path(cwd or self.default_cwd or os.getcwd()).resolve()

        if isinstance(cmd, str):
            cmd_args = shlex.split(cmd, posix=sys.platform != "win32")
        else:
            cmd_args = list(cmd)

        resolved_env = self._prepare_env(env)

        creationflags = 0
        preexec_fn = None
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
        else:
            preexec_fn = os.setsid

        t0 = time.perf_counter()
        proc = subprocess.Popen(
            cmd_args,
            cwd=str(effective_cwd),
            env=resolved_env,
            stdin=subprocess.PIPE if input_data is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
        )

        timed_out = False
        stdout_str = ""
        stderr_str = ""
        exit_code = 0

        try:
            stdout_data, stderr_data = proc.communicate(input=input_data, timeout=effective_timeout)
            exit_code = proc.returncode
            stdout_str = stdout_data or ""
            stderr_str = stderr_data or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            kill_process_tree(proc.pid)
            try:
                proc.kill()
            except Exception:
                pass
            try:
                out_salvage, err_salvage = proc.communicate(timeout=0.5)
                stdout_str = out_salvage or ""
                stderr_str = (err_salvage or "") + f"\nProcess timed out after {effective_timeout}s"
            except Exception:
                stdout_str = ""
                stderr_str = f"Process timed out after {effective_timeout}s"

            exit_code = -1
            if raise_on_timeout:
                raise subprocess.TimeoutExpired(
                    cmd=cmd_args,
                    timeout=effective_timeout,
                    output=stdout_str,
                    stderr=stderr_str,
                ) from exc

        duration_ms = (time.perf_counter() - t0) * 1000.0

        return ProcessResult(
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_ms=duration_ms,
            timed_out=timed_out,
            pid=proc.pid,
        )


def run_command(
    cmd: Union[List[str], str],
    cwd: Optional[Union[str, Path]] = None,
    timeout_sec: float = 30.0,
    env: Optional[Dict[str, str]] = None,
    input_data: Optional[str] = None,
    raise_on_timeout: bool = False,
) -> ProcessResult:
    runner = ProcessRunner()
    return runner.run(
        cmd=cmd,
        cwd=cwd,
        timeout_sec=timeout_sec,
        env=env,
        input_data=input_data,
        raise_on_timeout=raise_on_timeout,
    )
```

#### Specification 4: `src/plaq_sandbox/worktree.py`
```python
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
from typing import List, Optional, Union

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

        # Compute worktree path
        wt_dir = canonical_repo / self.base_worktree_dir / task_id
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
```

#### Specification 5: `src/plaq_sandbox/manager.py`
```python
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
```

#### Specification 6: `src/plaq_sandbox/__init__.py`
```python
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
```

---

## 5. Verification Method

To verify the implementation independently, execute the following commands from the repository root:

1. **Verify Python Import**:
   ```pwsh
   python -c "import plaq_sandbox; from plaq_sandbox import SandboxManager, PathGuard, PathTraversalError, ProcessRunner, ProcessResult, WorktreeManager; print('plaq_sandbox loaded successfully')"
   ```
2. **Verify Tier 1 Feature Sandbox Tests**:
   ```pwsh
   python -m pytest tests/e2e/test_tier1_feature.py -k "TestFeature08SandboxPathGuard or TestFeature09SubprocessRunner" -v
   ```
   *Expected outcome*: 10 tests passed.
3. **Verify Tier 2 Boundary Traversal & Process Tests**:
   ```pwsh
   python -m pytest tests/e2e/test_tier2_boundary.py -k "TestBoundary01PathTraversal or TestBoundary04ProcessTermination" -v
   ```
   *Expected outcome*: 21 tests passed, 1 skipped (Windows symlink privilege check).
4. **Invalidation Conditions**:
   - If `PathGuard.resolve_safe_path` fails to reject null bytes (`\0`) with match `"Null byte"`.
   - If `ProcessRunner.run` hangs when child processes spawn grandchildren or background jobs.
   - If worktree cleanup crashes on Windows due to read-only git metadata file permissions.

---

## 6. Worker Action Plan

For `worker_m3_1` (or designated implementer):

1. **Create Package Structure**:
   - Create directories `services/sandbox-manager/src/plaq_sandbox/`.
   - Write `services/sandbox-manager/README.md`.
   - Write `services/sandbox-manager/pyproject.toml` (Specification 1).
2. **Implement Guard Module**:
   - Write `services/sandbox-manager/src/plaq_sandbox/guard.py` (Specification 2).
   - Ensure null-byte check happens before and after URL decode.
   - Enforce case-insensitive Windows canonical path confinement.
3. **Implement Subprocess Runner**:
   - Write `services/sandbox-manager/src/plaq_sandbox/runner.py` (Specification 3).
   - Ensure `kill_process_tree` invokes `taskkill /F /T /PID` on Windows.
   - Ensure Windows essential environment variables are preserved.
   - Ensure timeout `<= 0` raises `ValueError`.
4. **Implement Worktree Manager**:
   - Write `services/sandbox-manager/src/plaq_sandbox/worktree.py` (Specification 4).
   - Handle git worktree creation, status, and cleanup.
   - Include `_remove_readonly` callback for `shutil.rmtree` on Windows.
5. **Implement Unified Façade & Package Exports**:
   - Write `services/sandbox-manager/src/plaq_sandbox/manager.py` (Specification 5).
   - Write `services/sandbox-manager/src/plaq_sandbox/__init__.py` (Specification 6).
6. **Execution Verification**:
   - Run verification commands listed in Section 5.
   - Verify zero regressions across `tests/e2e/test_tier1_feature.py` and `tests/e2e/test_tier2_boundary.py`.
