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
        # Fallback using psutil if available
        try:
            import psutil
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except Exception:
                    pass
            parent.kill()
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
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
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
            cmd_args = [str(arg) for arg in cmd]

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
    """Convenience function running a command with default ProcessRunner."""
    runner = ProcessRunner()
    return runner.run(
        cmd=cmd,
        cwd=cwd,
        timeout_sec=timeout_sec,
        env=env,
        input_data=input_data,
        raise_on_timeout=raise_on_timeout,
    )
