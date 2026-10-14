"""Unit tests for plaq_sandbox package (PathGuard, ProcessRunner, WorktreeManager, SandboxManager)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import pytest

from plaq_sandbox import (
    PathGuard,
    PathTraversalError,
    ProcessResult,
    ProcessRunner,
    SandboxManager,
    WorktreeError,
    WorktreeInfo,
    WorktreeManager,
    kill_process_tree,
    run_command,
)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory(prefix="plaq_test_ws_") as tmp:
        ws = Path(tmp).resolve()
        (ws / "src").mkdir()
        (ws / "README.md").write_text("# Test Workspace\n", encoding="utf-8")
        yield ws


@pytest.fixture
def temp_git_repo(temp_workspace):
    """Initialize a git repository in the temporary workspace."""
    subprocess.run(["git", "init", str(temp_workspace)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(temp_workspace), "config", "user.email", "test@plaq.ai"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(temp_workspace), "config", "user.name", "Plaq Tester"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(temp_workspace), "add", "."], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(temp_workspace), "commit", "-m", "Initial commit"], capture_output=True, check=True)
    return temp_workspace


class TestPathGuard:
    """Verifies PathGuard path confinement and traversal defenses."""

    def test_safe_relative_path_resolution(self, temp_workspace):
        rel = "src/model.py"
        resolved = PathGuard.resolve_safe_path(temp_workspace, rel)
        assert resolved == (temp_workspace / "src" / "model.py").resolve()
        assert str(resolved).startswith(str(temp_workspace))

    def test_parent_traversal_rejection(self, temp_workspace):
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(temp_workspace, "../../../etc/passwd")

    def test_url_encoded_traversal_rejection(self, temp_workspace):
        encoded = "%2e%2e%2f%2e%2e%2fsecret.txt"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(temp_workspace, encoded)

    def test_double_url_encoded_traversal_rejection(self, temp_workspace):
        double_encoded = "%252e%252e%252f%252e%252e%252fsecret.txt"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(temp_workspace, double_encoded)

    def test_null_byte_rejection(self, temp_workspace):
        with pytest.raises(PathTraversalError, match="Null byte"):
            PathGuard.resolve_safe_path(temp_workspace, "safe/file.py\0/escape.sh")

        with pytest.raises(PathTraversalError, match="Null byte"):
            PathGuard.resolve_safe_path(temp_workspace, "safe/file.py\x00/escape.sh")

    def test_absolute_system_escape_rejection(self, temp_workspace):
        outside = "C:\\Windows\\System32\\cmd.exe" if os.name == "nt" else "/etc/passwd"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(temp_workspace, outside)

    def test_nested_safe_directory(self, temp_workspace):
        nested = "a/b/c/d/e/circuit.qasm"
        resolved = PathGuard.resolve_safe_path(temp_workspace, nested)
        assert resolved == (temp_workspace / "a" / "b" / "c" / "d" / "e" / "circuit.qasm").resolve()

    def test_is_safe_path_helper(self, temp_workspace):
        assert PathGuard.is_safe_path(temp_workspace, "safe.py") is True
        assert PathGuard.is_safe_path(temp_workspace, "../escape.py") is False

    def test_guard_instance_methods(self, temp_workspace):
        guard = PathGuard(temp_workspace)
        assert guard.is_safe("src/circuit.py") is True
        assert guard.is_safe("../evil.py") is False
        resolved = guard.resolve("src/circuit.py")
        assert resolved == (temp_workspace / "src" / "circuit.py").resolve()


class TestProcessRunner:
    """Verifies ProcessRunner sandboxing, timeout enforcement, and exit codes."""

    def test_successful_execution(self, temp_workspace):
        runner = ProcessRunner()
        cmd = [sys.executable, "-c", "print('hello_sandbox')"]
        res = runner.run(cmd, cwd=temp_workspace)
        assert res.success is True
        assert res.exit_code == 0
        assert "hello_sandbox" in res.stdout
        assert res.timed_out is False

    def test_failing_command_captures_stderr(self, temp_workspace):
        runner = ProcessRunner()
        cmd = [sys.executable, "-c", "import sys; sys.stderr.write('err_msg'); sys.exit(42)"]
        res = runner.run(cmd, cwd=temp_workspace)
        assert res.success is False
        assert res.exit_code == 42
        assert "err_msg" in res.stderr

    def test_timeout_returns_timed_out(self, temp_workspace):
        runner = ProcessRunner()
        cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
        res = runner.run(cmd, cwd=temp_workspace, timeout_sec=0.2, raise_on_timeout=False)
        assert res.timed_out is True
        assert res.exit_code == -1
        assert "timed out" in res.stderr.lower()

    def test_timeout_raises_when_requested(self, temp_workspace):
        runner = ProcessRunner()
        cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
        with pytest.raises(subprocess.TimeoutExpired):
            runner.run(cmd, cwd=temp_workspace, timeout_sec=0.2, raise_on_timeout=True)

    def test_reject_zero_or_negative_timeout(self, temp_workspace):
        runner = ProcessRunner()
        cmd = [sys.executable, "-c", "print(1)"]
        with pytest.raises(ValueError, match="positive"):
            runner.run(cmd, cwd=temp_workspace, timeout_sec=0.0)
        with pytest.raises(ValueError, match="positive"):
            runner.run(cmd, cwd=temp_workspace, timeout_sec=-1.0)

    def test_environment_variable_propagation(self, temp_workspace):
        runner = ProcessRunner()
        cmd = [sys.executable, "-c", "import os; print(os.environ.get('MY_TEST_KEY', ''))"]
        res = runner.run(cmd, cwd=temp_workspace, env={"MY_TEST_KEY": "sandbox_val_123"})
        assert "sandbox_val_123" in res.stdout.strip()

    def test_to_tool_result(self, temp_workspace):
        res = ProcessResult(
            exit_code=0,
            stdout="output_data",
            stderr="",
            duration_ms=12.5,
            timed_out=False,
            pid=1234,
        )
        tool_res = res.to_tool_result(modified_files=["report.json"])
        assert tool_res.success is True
        assert tool_res.output == "output_data"
        assert tool_res.modified_files == ["report.json"]
        assert tool_res.exit_code == 0


class TestWorktreeManager:
    """Verifies Git Worktree creation, status query, and cleanup."""

    def test_is_git_repo(self, temp_git_repo, temp_workspace):
        mgr = WorktreeManager()
        assert mgr.is_git_repo(temp_git_repo) is True
        with tempfile.TemporaryDirectory() as non_repo:
            assert mgr.is_git_repo(non_repo) is False

    def test_create_and_cleanup_worktree(self, temp_git_repo):
        mgr = WorktreeManager()
        task_id = "test-task-wt-1"
        wt_path = mgr.create_worktree(temp_git_repo, task_id)
        assert Path(wt_path).exists()
        assert (Path(wt_path) / "README.md").exists()

        status = mgr.get_worktree_status(temp_git_repo, task_id)
        assert status is not None
        assert status.task_id == task_id

        mgr.cleanup_worktree(temp_git_repo, task_id)
        assert not Path(wt_path).exists()
        assert mgr.get_worktree_status(temp_git_repo, task_id) is None

    def test_invalid_task_id_rejected(self, temp_git_repo):
        mgr = WorktreeManager()
        with pytest.raises(WorktreeError):
            mgr.create_worktree(temp_git_repo, "../../evil_id")


class TestSandboxManagerFacade:
    """Verifies unified SandboxManager façade."""

    def test_facade_methods(self, temp_git_repo):
        sm = SandboxManager()
        # Path resolution
        safe_p = sm.resolve_safe_path(temp_git_repo, "README.md")
        assert safe_p.exists()

        # Command execution
        res = sm.run_command([sys.executable, "-c", "print('facade_ok')"], cwd=temp_git_repo)
        assert "facade_ok" in res.stdout

        # Worktree operations
        wt_p = sm.create_worktree(temp_git_repo, "facade-task-1")
        assert Path(wt_p).exists()
        status = sm.get_worktree_status(temp_git_repo, "facade-task-1")
        assert status is not None
        sm.cleanup_worktree(temp_git_repo, "facade-task-1")
        assert not Path(wt_p).exists()
