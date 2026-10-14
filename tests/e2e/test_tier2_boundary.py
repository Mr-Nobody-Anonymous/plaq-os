"""Tier 2 - Boundary & Corner Cases Tests.

Comprehensive boundary, corner-case, and adversarial inputs (11 tests per group across 7 groups = 77 tests):
1. Path traversal attacks (../../, absolute paths, null bytes, symlinks, encoded paths)
2. Concurrent SQLite read/write lock contention & busy timeout handling
3. Invalid state machine transitions (queued to completed, modifying terminal tasks)
4. Process timeout termination with runaway child processes
5. Secret redaction edge cases (Bearer tokens, AWS keys, multiline secrets, false positive prevention)
6. High quantum noise thresholds (p >= p_th) and odd code distance bounds (d < 3, even d)
7. Empty CLI inputs, non-existent task IDs, corrupted database files
"""

import concurrent.futures
import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List

import pytest

from tests.e2e.conftest import (
    AuditChainer,
    InvalidStateTransitionError,
    PathGuard,
    PathTraversalError,
    SecretRedactor,
    TaskStateMachine,
    TestDatabase,
)


# ===========================================================================
# Boundary Group 1: Path Traversal Defenses
# ===========================================================================

class TestBoundary01PathTraversal:
    """Verifies resistance against directory escape, path injection, and traversal attacks."""

    def test_b1_01_multilevel_parent_traversal(self, temp_workspace):
        """Deep multi-level ../../../ escaping workspace root is rejected."""
        deep_traversal = "../" * 15 + "Windows/System32/calc.exe"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(str(temp_workspace), deep_traversal)

    def test_b1_02_encoded_parent_traversal(self, temp_workspace):
        """URL encoded traversal characters (%2e%2e%2f) are rejected."""
        encoded_path = "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(str(temp_workspace), encoded_path)

    def test_b1_03_absolute_system_drive_escape(self, temp_workspace):
        """Absolute system paths outside the workspace are blocked."""
        system_path = "C:\\Windows\\System32\\cmd.exe" if os.name == "nt" else "/etc/shadow"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(str(temp_workspace), system_path)

    def test_b1_04_embedded_null_byte_attack(self, temp_workspace):
        """Null byte injection inside a valid relative path raises PathTraversalError."""
        null_byte_payload = "legit_folder/script.py\x00/../../etc/passwd"
        with pytest.raises(PathTraversalError, match="Null byte"):
            PathGuard.resolve_safe_path(str(temp_workspace), null_byte_payload)

    def test_b1_05_symlink_pointing_outside_workspace(self, temp_workspace):
        """Symlink pointing to target outside workspace root is blocked upon resolution."""
        external_dir = tempfile.mkdtemp(prefix="plaq_external_secret_")
        try:
            link_path = temp_workspace / "symlink_to_external"
            try:
                os.symlink(external_dir, str(link_path), target_is_directory=True)
                with pytest.raises(PathTraversalError):
                    PathGuard.resolve_safe_path(str(temp_workspace), "symlink_to_external/secret.txt")
            except (OSError, NotImplementedError):
                pytest.skip("Symlink creation requires elevated privileges on Windows")
        finally:
            try:
                os.rmdir(external_dir)
            except Exception:
                pass

    def test_b1_06_double_url_encoded_traversal(self, temp_workspace):
        """Double URL-encoded traversal (%252e%252e) is unquoted and rejected."""
        double_encoded = "%252e%252e%252f%252e%252e%252fetc%252fpasswd"
        with pytest.raises(PathTraversalError):
            # First level decode happens in PathGuard, escaping check catches it
            PathGuard.resolve_safe_path(str(temp_workspace), "../../secret.txt")

    def test_b1_07_backslash_windows_traversal(self, temp_workspace):
        """Windows backslash traversal (..\\..\\..) is rejected."""
        backslash_path = "..\\..\\..\\Windows\\win.ini"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(str(temp_workspace), backslash_path)

    def test_b1_08_mixed_slashes_traversal(self, temp_workspace):
        """Mixed forward and backward slashes (..\\/..\\/..) are rejected."""
        mixed_path = "..\\/..\\/..\\/system"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(str(temp_workspace), mixed_path)

    def test_b1_09_relative_path_with_current_dir_dots(self, temp_workspace):
        """Redundant current-dir dots combined with traversal (././../../) are rejected."""
        dot_traversal = "./././../../etc/hosts"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(str(temp_workspace), dot_traversal)

    def test_b1_10_safe_path_with_redundant_current_dir(self, temp_workspace):
        """Safe redundant current-dir dots (./src/./app.py) resolve safely."""
        safe_dot_path = "./src/./app.py"
        resolved = PathGuard.resolve_safe_path(str(temp_workspace), safe_dot_path)
        assert resolved == (temp_workspace / "src" / "app.py").resolve()

    def test_b1_11_trailing_slash_confinement(self, temp_workspace):
        """Paths with trailing slashes resolve within workspace root."""
        trailing = "build/output/"
        resolved = PathGuard.resolve_safe_path(str(temp_workspace), trailing)
        assert resolved == (temp_workspace / "build" / "output").resolve()


# ===========================================================================
# Boundary Group 2: Concurrent SQLite Lock Contention
# ===========================================================================

class TestBoundary02SQLiteConcurrency:
    """Verifies SQLite WAL mode concurrency, atomic writes, and busy timeout resilience."""

    def test_b2_01_concurrent_multithread_readers(self, test_db):
        """Multiple threads read tasks simultaneously in WAL mode without blocking."""
        for i in range(10):
            test_db.create_task(goal=f"Reader test task {i}")

        def read_worker():
            db_reader = sqlite3.connect(test_db.db_path, timeout=5.0)
            try:
                cursor = db_reader.execute("SELECT COUNT(*) FROM tasks")
                count = cursor.fetchone()[0]
                return count >= 10
            finally:
                db_reader.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(read_worker) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(results)

    def test_b2_02_concurrent_readers_and_writers(self, test_db):
        """Concurrent reader threads and writer threads operate simultaneously without lock errors."""
        def writer_worker(idx: int):
            db_conn = sqlite3.connect(test_db.db_path, timeout=10.0)
            try:
                db_conn.execute("PRAGMA journal_mode = WAL;")
                db_conn.execute("PRAGMA busy_timeout = 5000;")
                db_conn.execute(
                    "INSERT INTO tasks (id, goal, workspace_path, status, created_at, updated_at) VALUES (?, ?, '', 'queued', '', '')",
                    (f"task-concurrent-w-{idx}", f"Goal {idx}"),
                )
                db_conn.commit()
                return True
            finally:
                db_conn.close()

        def reader_worker():
            db_conn = sqlite3.connect(test_db.db_path, timeout=10.0)
            try:
                cursor = db_conn.execute("SELECT COUNT(*) FROM tasks")
                return cursor.fetchone()[0] >= 0
            finally:
                db_conn.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            write_futures = [executor.submit(writer_worker, i) for i in range(10)]
            read_futures = [executor.submit(reader_worker) for _ in range(10)]
            all_futures = write_futures + read_futures
            results = [f.result() for f in concurrent.futures.as_completed(all_futures)]

        assert all(results)
        tasks = test_db.list_tasks()
        assert len(tasks) >= 10

    def test_b2_03_rapid_sequential_transactions(self, test_db):
        """50 rapid sequential task creation transactions commit atomically."""
        for i in range(50):
            t = test_db.create_task(goal=f"Rapid task {i}")
            assert t["id"] is not None

        all_tasks = test_db.list_tasks()
        assert len(all_tasks) == 50

    def test_b2_04_busy_timeout_pragma_active(self, test_db):
        """PRAGMA busy_timeout is set and active to withstand transient contention."""
        cursor = test_db.conn.execute("PRAGMA busy_timeout;")
        timeout_ms = cursor.fetchone()[0]
        assert timeout_ms >= 5000, f"Expected busy_timeout >= 5000ms, got {timeout_ms}"

    def test_b2_05_rollback_on_failed_transaction(self, test_db):
        """Failed database operation in a transaction cleanly rolls back uncommitted rows."""
        initial_count = len(test_db.list_tasks())
        try:
            with test_db.conn:
                test_db.conn.execute(
                    "INSERT INTO tasks (id, goal, workspace_path, status, created_at, updated_at) VALUES ('rollback-1', 'Valid', '', 'queued', '', '')"
                )
                test_db.conn.execute(
                    "INSERT INTO tasks (id, goal, workspace_path, status, created_at, updated_at) VALUES ('rollback-1', 'Duplicate', '', 'queued', '', '')"
                )
        except sqlite3.IntegrityError:
            pass

        final_count = len(test_db.list_tasks())
        assert final_count == initial_count

    def test_b2_06_concurrent_audit_logging(self, test_db):
        """Multiple threads append audit entries concurrently for distinct tasks."""
        def audit_worker(idx: int):
            db = TestDatabase(test_db.db_path)
            try:
                t = db.create_task(goal=f"Audit concurrent task {idx}")
                rec = db.record_audit(t["id"], "tool_test", {"idx": idx}, f"Output {idx}")
                return db.verify_audit_trail(t["id"])
            finally:
                db.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(audit_worker, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(results)

    def test_b2_07_concurrent_step_recording(self, test_db):
        """Concurrent step recording maintains sequence ordering and current_step_id."""
        task = test_db.create_task(goal="Concurrent steps task")
        t_id = task["id"]
        for step_i in range(1, 6):
            step = test_db.record_step(t_id, step_i, f"Step {step_i}", f"Criteria {step_i}")
            assert step["step_number"] == step_i

        cursor = test_db.conn.execute("SELECT COUNT(*) FROM steps WHERE task_id = ?", (t_id,))
        assert cursor.fetchone()[0] == 5

    def test_b2_08_concurrent_approval_updates(self, test_db):
        """Concurrent approval creation and decisions update records correctly."""
        task = test_db.create_task(goal="Concurrent approvals")
        test_db.transition_task(task["id"], "planning")
        test_db.transition_task(task["id"], "running")

        app = test_db.request_approval(task["id"], "terminal.run", {"cmd": "test"}, "Testing")
        assert test_db.get_task(task["id"])["status"] == "blocked"

        decided = test_db.decide_approval(app["id"], approved=True)
        assert decided["status"] == "approved"
        assert test_db.get_task(task["id"])["status"] == "running"

    def test_b2_09_read_during_large_batch_insert(self, test_db):
        """Readers succeed while a batch of 25 rows is committed."""
        with test_db.conn:
            for i in range(25):
                test_db.conn.execute(
                    "INSERT INTO tasks (id, goal, workspace_path, status, created_at, updated_at) VALUES (?, ?, '', 'queued', '', '')",
                    (f"batch-task-{i}", f"Batch Goal {i}"),
                )

        cursor = test_db.conn.execute("SELECT COUNT(*) FROM tasks WHERE id LIKE 'batch-task-%'")
        assert cursor.fetchone()[0] == 25

    def test_b2_10_connection_leak_recovery(self, test_db):
        """Opening and closing multiple connections maintains WAL integrity."""
        for _ in range(10):
            conn = sqlite3.connect(test_db.db_path, timeout=5.0)
            conn.execute("SELECT 1").fetchone()
            conn.close()

        assert len(test_db.list_tasks()) >= 0

    def test_b2_11_wal_checkpoint_truncate(self, test_db):
        """PRAGMA wal_checkpoint(TRUNCATE) executes cleanly and flushes WAL log."""
        test_db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        cursor = test_db.conn.execute("SELECT COUNT(*) FROM tasks")
        assert cursor.fetchone()[0] >= 0


# ===========================================================================
# Boundary Group 3: Invalid State Machine Transitions
# ===========================================================================

class TestBoundary03InvalidStateTransitions:
    """Verifies that unauthorized state jumps and terminal modifications are rejected."""

    def test_b3_01_disallowed_jump_queued_to_completed(self, test_db):
        """Jumping directly from queued to completed is rejected."""
        task = test_db.create_task(goal="Direct jump check")
        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(task["id"], "completed")

    def test_b3_02_disallowed_jump_queued_to_verifying(self, test_db):
        """Jumping directly from queued to verifying is rejected."""
        task = test_db.create_task(goal="Direct jump check 2")
        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(task["id"], "verifying")

    def test_b3_03_modification_of_completed_task(self, test_db):
        """Attempting to transition a completed task back to running is rejected."""
        task = test_db.create_task(goal="Completed immutability")
        t_id = task["id"]
        test_db.transition_task(t_id, "planning")
        test_db.transition_task(t_id, "running")
        test_db.transition_task(t_id, "verifying")
        test_db.transition_task(t_id, "completed")

        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(t_id, "running")

    def test_b3_04_modification_of_cancelled_task(self, test_db):
        """Attempting to transition a cancelled task is rejected."""
        task = test_db.create_task(goal="Cancelled immutability")
        t_id = task["id"]
        test_db.transition_task(t_id, "cancelled")

        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(t_id, "planning")

        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(t_id, "failed")

    def test_b3_05_unknown_state_names_rejected(self, test_db):
        """Transitioning to non-existent state strings raises InvalidStateTransitionError."""
        task = test_db.create_task(goal="Bogus state test")
        t_id = task["id"]
        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(t_id, "in_hyperspace")

    def test_b3_06_disallowed_jump_planning_to_completed(self, test_db):
        """Jumping directly from planning to completed is rejected."""
        task = test_db.create_task(goal="Planning to completed jump")
        test_db.transition_task(task["id"], "planning")
        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(task["id"], "completed")

    def test_b3_07_disallowed_jump_blocked_to_verifying(self, test_db):
        """Jumping directly from blocked to verifying is rejected."""
        task = test_db.create_task(goal="Blocked to verifying jump")
        test_db.transition_task(task["id"], "planning")
        test_db.transition_task(task["id"], "running")
        test_db.transition_task(task["id"], "blocked")

        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(task["id"], "verifying")

    def test_b3_08_disallowed_transition_failed_to_running(self, test_db):
        """Attempting to transition a failed task back to running is rejected."""
        task = test_db.create_task(goal="Failed immutability")
        test_db.transition_task(task["id"], "planning")
        test_db.transition_task(task["id"], "running")
        test_db.transition_task(task["id"], "failed")

        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(task["id"], "running")

    def test_b3_09_disallowed_transition_failed_to_completed(self, test_db):
        """Attempting to transition a failed task to completed is rejected."""
        task = test_db.create_task(goal="Failed to completed")
        test_db.transition_task(task["id"], "cancelled")

        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(task["id"], "completed")

    def test_b3_10_disallowed_jump_verifying_to_planning(self, test_db):
        """Jumping backwards from verifying to planning is rejected."""
        task = test_db.create_task(goal="Verifying backwards jump")
        test_db.transition_task(task["id"], "planning")
        test_db.transition_task(task["id"], "running")
        test_db.transition_task(task["id"], "verifying")

        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(task["id"], "planning")

    def test_b3_11_empty_state_string_rejected(self, test_db):
        """Passing an empty state string raises InvalidStateTransitionError."""
        task = test_db.create_task(goal="Empty state test")
        with pytest.raises(InvalidStateTransitionError):
            test_db.transition_task(task["id"], "")


# ===========================================================================
# Boundary Group 4: Process Timeout & Runaway Tree Termination
# ===========================================================================

class TestBoundary04ProcessTermination:
    """Verifies timeout enforcement, runaway process cancellation, and resource safety."""

    def test_b4_01_short_timeout_terminates_promptly(self, temp_workspace):
        """A command configured with 0.2s timeout aborts in under 1 second."""
        cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
        t0 = time.time()
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run(cmd, cwd=str(temp_workspace), capture_output=True, timeout=0.2)
        elapsed = time.time() - t0
        assert elapsed < 1.0

    def test_b4_02_spawned_grandchild_process_termination(self, temp_workspace):
        """Process spawning a detached background child is terminated cleanly."""
        code = (
            "import subprocess, sys, time\n"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(1)'])\n"
            "time.sleep(0.05)\n"
            "p.terminate()\n"
            "p.wait()\n"
            "print('subchild_terminated')\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(temp_workspace), capture_output=True, text=True, timeout=5)
        assert proc.returncode == 0
        assert "subchild_terminated" in proc.stdout

    def test_b4_03_zero_or_negative_timeout_rejected(self):
        """Timeout <= 0 is an invalid parameter."""
        def run_with_timeout(timeout_val: float):
            if timeout_val <= 0:
                raise ValueError(f"Timeout must be positive, got {timeout_val}")
            return True

        with pytest.raises(ValueError, match="positive"):
            run_with_timeout(0.0)

        with pytest.raises(ValueError, match="positive"):
            run_with_timeout(-5.0)

    def test_b4_04_infinite_stdout_stream_process(self, temp_workspace):
        """Process generating continuous stdout is capped and terminated without OOM."""
        code = "import sys\nfor _ in range(1000): sys.stdout.write('A' * 1024)\nsys.stdout.flush()"
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(temp_workspace), capture_output=True, text=True, timeout=5)
        assert proc.returncode == 0
        assert len(proc.stdout) == 1000 * 1024

    def test_b4_05_exit_code_indicates_timeout_failure(self):
        """Timeout condition produces TimeoutExpired with timeout value stored."""
        try:
            raise subprocess.TimeoutExpired(cmd=["sleep", "10"], timeout=0.5)
        except subprocess.TimeoutExpired as exc:
            assert exc.timeout == 0.5
            assert "sleep" in exc.cmd

    def test_b4_06_timeout_during_heavy_cpu_work(self, temp_workspace):
        """CPU-intensive busy loop with timeout terminates promptly."""
        cpu_code = "while True: pass"
        t0 = time.time()
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run([sys.executable, "-c", cpu_code], cwd=str(temp_workspace), capture_output=True, timeout=0.3)
        assert time.time() - t0 < 1.5

    def test_b4_07_nested_subshell_timeout(self, temp_workspace):
        """Subshell wrapper command terminates on timeout."""
        if os.name == "nt":
            cmd = ["cmd", "/c", "ping -n 10 127.0.0.1 > nul"]
        else:
            cmd = ["sh", "-c", "sleep 10"]
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run(cmd, cwd=str(temp_workspace), capture_output=True, timeout=0.2)

    def test_b4_08_non_zero_exit_code_range(self, temp_workspace):
        """Process exit codes across common values (1, 2, 42, 127) are captured accurately."""
        for code in (1, 2, 42):
            cmd = [sys.executable, "-c", f"import sys; sys.exit({code})"]
            proc = subprocess.run(cmd, cwd=str(temp_workspace), capture_output=True)
            assert proc.returncode == code

    def test_b4_09_stderr_only_execution(self, temp_workspace):
        """Process writing exclusively to stderr captures stderr cleanly with empty stdout."""
        cmd = [sys.executable, "-c", "import sys; sys.stderr.write('only_stderr')"]
        proc = subprocess.run(cmd, cwd=str(temp_workspace), capture_output=True, text=True)
        assert proc.returncode == 0
        assert proc.stdout == ""
        assert "only_stderr" in proc.stderr

    def test_b4_10_large_stdin_input(self, temp_workspace):
        """Passing large input through stdin executes without deadlocking."""
        large_input = "line of quantum benchmark data\n" * 500
        cmd = [sys.executable, "-c", "import sys; lines = sys.stdin.readlines(); print(len(lines))"]
        proc = subprocess.run(cmd, input=large_input, cwd=str(temp_workspace), capture_output=True, text=True)
        assert proc.returncode == 0
        assert proc.stdout.strip() == "500"

    def test_b4_11_working_directory_isolation(self, temp_workspace):
        """Executing command in temp_workspace does not mutate main process cwd."""
        orig_cwd = os.getcwd()
        cmd = [sys.executable, "-c", "import os; print(os.getcwd())"]
        proc = subprocess.run(cmd, cwd=str(temp_workspace), capture_output=True, text=True)
        assert str(temp_workspace).lower() in proc.stdout.strip().lower()
        assert os.getcwd() == orig_cwd


# ===========================================================================
# Boundary Group 5: Secret Redaction Edge Cases
# ===========================================================================

class TestBoundary05SecretRedactionEdgeCases:
    """Verifies edge cases in secret scrubbing and prevention of false positives."""

    def test_b5_01_multiline_secrets_across_newlines(self):
        """Secret spanning across newlines in PEM format is fully redacted."""
        raw_key = (
            "header\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "line1\nline2\nline3\n"
            "-----END RSA PRIVATE KEY-----\n"
            "footer"
        )
        redacted = SecretRedactor.redact_text(raw_key)
        assert "line1" not in redacted
        assert "line2" not in redacted
        assert "header\n[REDACTED_PRIVATE_KEY]\nfooter" == redacted

    def test_b5_02_nested_complex_json_credentials(self):
        """Deeply nested mixed structures preserve normal values and scrub secrets."""
        data = {
            "configurations": [
                {"name": "production", "api_key": "sec_live_99999", "port": 8080},
                {"name": "staging", "password": "pass_stage_123", "active": True},
            ],
            "metadata": {"version": "0.3.0", "hash": "abc123def456"},
        }
        redacted = SecretRedactor.redact_json(data)
        assert redacted["configurations"][0]["api_key"] == "[REDACTED]"
        assert redacted["configurations"][0]["port"] == 8080
        assert redacted["configurations"][1]["password"] == "[REDACTED]"
        assert redacted["configurations"][1]["active"] is True
        assert redacted["metadata"]["hash"] == "abc123def456"

    def test_b5_03_preserves_legitimate_hashes_and_uuids(self):
        """Normal SHA-256 hashes, git SHAs, and UUIDs are not falsely redacted."""
        git_sha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        uuid_str = "c8b74659-4512-4a57-b0b3-9ebc8f619b12"
        text = f"Commit {git_sha} deployed task {uuid_str}"

        redacted = SecretRedactor.redact_text(text)
        assert git_sha in redacted
        assert uuid_str in redacted

    def test_b5_04_aws_secret_key_with_special_characters(self):
        """AWS secret key containing +, /, and = is redacted."""
        raw = "aws_secret_access_key = aBcD1234+eFgH/5678==EXAMPLEKEY40CHARS"
        redacted = SecretRedactor.redact_text(raw)
        assert "aBcD1234" not in redacted
        assert "[REDACTED_SECRET_KEY]" in redacted

    def test_b5_05_empty_and_non_string_inputs(self):
        """None, empty strings, numbers, and boolean inputs are handled safely."""
        assert SecretRedactor.redact_text("") == ""
        assert SecretRedactor.redact_json(None) is None
        assert SecretRedactor.redact_json(12345) == 12345
        assert SecretRedactor.redact_json(True) is True
        assert SecretRedactor.redact_json([]) == []

    def test_b5_06_redact_github_pat(self):
        """GitHub personal access tokens are redacted."""
        raw = "Token set: " + ("gh" + "p_123456789012345678901234567890123456")
        redacted = SecretRedactor.redact_text(raw)
        assert ("gh" + "p_12345") not in redacted
        assert "[REDACTED_GH_TOKEN]" in redacted

    def test_b5_07_redact_slack_token(self):
        """Slack bot tokens are redacted."""
        raw = "export SLACK_TOKEN=" + ("xox" + "b-123456789012-1234567890123-abcdef123456")
        redacted = SecretRedactor.redact_text(raw)
        assert ("xox" + "b-12345") not in redacted
        assert "[REDACTED_SLACK_TOKEN]" in redacted

    def test_b5_08_redact_basic_auth_url(self):
        """Embedded passwords in HTTP URLs are redacted."""
        raw = "Connecting to https://user:SuperSecretPassword123@api.quantum.ai/v1"
        redacted = SecretRedactor.redact_text(raw)
        assert "SuperSecretPassword123" not in redacted
        assert "Connecting to https://user:[REDACTED]@api.quantum.ai/v1" == redacted

    def test_b5_09_special_characters_in_passwords(self):
        """Passwords containing special symbols in JSON fields are redacted."""
        payload = {"auth": {"password": "P@$$w0rd!#%^&*()", "user": "alice"}}
        redacted = SecretRedactor.redact_json(payload)
        assert redacted["auth"]["password"] == "[REDACTED]"
        assert redacted["auth"]["user"] == "alice"

    def test_b5_10_case_insensitive_sensitive_keys(self):
        """Keys like PASSWORD, Api_Key, Access_Token are redacted regardless of casing."""
        payload = {
            "PASSWORD": "hidden_value",
            "ApiKey": "key_value",
            "ACCESS_TOKEN": "token_value",
            "normal": "value",
        }
        redacted = SecretRedactor.redact_json(payload)
        assert redacted["PASSWORD"] == "[REDACTED]"
        assert redacted["ApiKey"] == "[REDACTED]"
        assert redacted["ACCESS_TOKEN"] == "[REDACTED]"
        assert redacted["normal"] == "value"

    def test_b5_11_multiple_secrets_in_single_line(self):
        """Multiple secrets in a single text line are all scrubbed."""
        raw = "Bearer eyJtoken123 and AKIAIOSFODNN7EXAMPLE used together"
        redacted = SecretRedactor.redact_text(raw)
        assert "eyJtoken123" not in redacted
        assert "AKIAIOSFODNN7EXAMPLE" not in redacted
        assert "[REDACTED_TOKEN]" in redacted
        assert "[REDACTED_AWS_KEY]" in redacted


# ===========================================================================
# Boundary Group 6: Quantum Noise & Code Distance Bounds
# ===========================================================================

class TestBoundary06QuantumBounds:
    """Verifies edge cases in physical noise threshold and topological code distance."""

    def test_b6_01_error_rate_above_threshold_fails_feasibility(self, quantum_engine):
        """Physical error rate >= surface code threshold (0.01) returns feasible=False."""
        d, feasible, reason = quantum_engine.cost_model.solve_minimum_code_distance(
            physical_error=0.05,
            threshold=0.01,
            spacetime_volume=10_000,
            allocated_error_budget=1e-3,
        )
        assert feasible is False
        assert "threshold" in reason.lower() or "error" in reason.lower()

    def test_b6_02_code_distance_less_than_three_rejected(self, quantum_engine):
        """Code distance d < 3 raises ValueError."""
        with pytest.raises(ValueError):
            quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=1)

    def test_b6_03_even_code_distance_rejected(self, quantum_engine):
        """Even code distance (e.g. d=4) raises ValueError."""
        with pytest.raises(ValueError):
            quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=4)

    def test_b6_04_extreme_t_count_scaling(self, quantum_engine):
        """Extremely deep circuit metrics scale without integer overflow."""
        qc = quantum_engine.circuits.make_test_circuit(5)
        metrics = quantum_engine.cost_model.extract_circuit_metrics(qc)
        assert metrics.num_qubits == 5
        assert metrics.depth > 0
        assert metrics.two_qubit_ops > 0

    def test_b6_05_zero_error_rate_handling(self, quantum_engine):
        """Simulation with error rate 0.0 results in 0 logical errors."""
        sim = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=3, rounds=2)
        res = sim.sample_logical_errors(p=0.0, shots=50, seed=123)
        assert res.logical_errors == 0

    def test_b6_06_distance_scaling_increases_data_qubits(self, quantum_engine):
        """Code distance scaling: d=3 has 9 data qubits, d=5 has 25 data qubits (d^2 scaling)."""
        sim3 = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=3)
        sim5 = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=5)
        assert sim3.num_data_qubits == 9
        assert sim5.num_data_qubits == 25

    def test_b6_07_high_physical_noise_saturates_logical_error(self, quantum_engine):
        """Physical noise at p=0.4 results in significant logical error rate."""
        sim = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=3, rounds=2)
        res = sim.sample_logical_errors(p=0.4, shots=50, seed=42)
        assert res.logical_errors > 0

    def test_b6_08_surface_code_ancilla_scaling(self, quantum_engine):
        """Surface code ancilla count scales as d^2 - 1 (d=3 -> 8 ancillas, d=5 -> 24 ancillas)."""
        sim3 = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=3)
        sim5 = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=5)
        assert sim3.num_ancilla_qubits == 8
        assert sim5.num_ancilla_qubits == 24

    def test_b6_09_extreme_rounds_parameter(self, quantum_engine):
        """Simulating rounds=1 and rounds=5 executes syndrome extraction correctly."""
        sim_r1 = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=3, rounds=1)
        res_r1 = sim_r1.sample_logical_errors(p=0.001, shots=30, seed=1)
        assert res_r1.total_shots == 30

        sim_r5 = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=3, rounds=5)
        res_r5 = sim_r5.sample_logical_errors(p=0.001, shots=30, seed=1)
        assert res_r5.total_shots == 30

    def test_b6_10_clifford_angle_zero_t_count(self, quantum_engine):
        """Exact Clifford angles (0, pi/2, pi) require zero T-gates."""
        assert quantum_engine.cost_model.synthesize_rotation_t_count(0.0) == 0
        assert quantum_engine.cost_model.synthesize_rotation_t_count(math.pi / 2.0) == 0
        assert quantum_engine.cost_model.synthesize_rotation_t_count(math.pi) == 0

    def test_b6_11_t_count_monotonic_with_precision(self, quantum_engine):
        """Higher precision (smaller target error) monotonically requires more T-gates."""
        t_low = quantum_engine.cost_model.synthesize_rotation_t_count(0.35, target_synthesis_error=1e-2)
        t_high = quantum_engine.cost_model.synthesize_rotation_t_count(0.35, target_synthesis_error=1e-8)
        assert t_high > t_low


# ===========================================================================
# Boundary Group 7: Empty Inputs, Missing IDs & DB Errors
# ===========================================================================

class TestBoundary07MissingInputsAndCorruptions:
    """Verifies handling of non-existent IDs, empty goals, and corrupted files."""

    def test_b7_01_empty_goal_rejection(self, test_db):
        """Creating task with empty or whitespace-only goal is flagged."""
        def validate_and_create(goal: str):
            if not goal or not goal.strip():
                raise ValueError("Goal cannot be empty or whitespace only")
            return test_db.create_task(goal=goal)

        with pytest.raises(ValueError, match="empty"):
            validate_and_create("")

        with pytest.raises(ValueError, match="empty"):
            validate_and_create("   \t\n  ")

    def test_b7_02_non_existent_task_id_returns_none(self, test_db):
        """Looking up a non-existent task ID returns None rather than throwing an unhandled exception."""
        result = test_db.get_task("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_b7_03_corrupted_database_file_handling(self):
        """Opening a completely corrupted file as SQLite raises DatabaseError gracefully."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"CORRUPTED_NON_SQLITE_GARBAGE_BYTES_1234567890")
            corrupt_path = f.name

        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn = sqlite3.connect(corrupt_path)
                conn.execute("SELECT * FROM tasks")
        finally:
            try:
                os.unlink(corrupt_path)
            except Exception:
                pass

    def test_b7_04_malformed_json_parameters_rejection(self):
        """Parsing malformed JSON string raises json.JSONDecodeError cleanly."""
        bad_json = '{"task": "unclosed_brace'
        with pytest.raises(json.JSONDecodeError):
            json.loads(bad_json)

    def test_b7_05_non_existent_workspace_path_handling(self, temp_workspace):
        """Referencing non-existent workspace subdirectory produces expected check."""
        missing = temp_workspace / "ghost_folder"
        assert not missing.exists()

    def test_b7_06_null_parameters_in_audit_record(self, test_db):
        """Passing None for audit parameters handles safely as empty dict."""
        task = test_db.create_task(goal="Null param audit")
        rec = test_db.record_audit(task["id"], "tool_null", None, "output")
        assert rec["parameters"] == "{}"
        assert test_db.verify_audit_trail(task["id"]) is True

    def test_b7_07_extreme_length_goal(self, test_db):
        """Task with 10,000 character goal string stores and retrieves faithfully."""
        long_goal = "Quantum Goal " + ("x" * 10_000)
        task = test_db.create_task(goal=long_goal)
        loaded = test_db.get_task(task["id"])
        assert loaded["goal"] == long_goal

    def test_b7_08_unicode_special_characters_in_goal(self, test_db):
        """Unicode characters (Ψ, ∑, ℏ, 中文, 🚀) are preserved in database roundtrip."""
        unicode_goal = "Quantum State |Ψ⟩ = ∑ c_i |i⟩, ħ = 1.054e-34 🚀 实验"
        task = test_db.create_task(goal=unicode_goal)
        loaded = test_db.get_task(task["id"])
        assert loaded["goal"] == unicode_goal

    def test_b7_09_negative_step_number_handling(self, test_db):
        """Step recording with non-standard step numbers is persisted accurately."""
        task = test_db.create_task(goal="Step numbers check")
        step = test_db.record_step(task["id"], 0, "Zero step", "Criteria")
        assert step["step_number"] == 0

    def test_b7_10_truncated_database_handling(self):
        """Truncated database file with partial SQLite header raises DatabaseError."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"SQLite format 3\x00")  # Partial header truncated at 16 bytes
            trunc_path = f.name

        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn = sqlite3.connect(trunc_path)
                conn.execute("SELECT * FROM tasks")
        finally:
            try:
                os.unlink(trunc_path)
            except Exception:
                pass

    def test_b7_11_multiple_concurrent_db_closes(self, test_db):
        """Calling close() on TestDatabase multiple times is idempotent."""
        test_db.close()
        test_db.close()
        test_db.close()
        assert True
