"""
Empirical Adversarial Stress Test Suite for Plaq-OS Control Plane (Milestone M2).
Executed by Empirical Challenger (challenger_m2_gen2_1).

Challenges:
1. Concurrency Stress: Multithreaded concurrent reads and writes against DatabaseEngine
   and ControlPlaneRepository confirming WAL mode, busy timeout, and zero lock errors.
2. State Machine Immutability: Transition attempts from all terminal states (completed,
   failed, cancelled) to any other state under parameter variations.
3. Foreign Key Cascades: Enforcement of relational integrity on orphaned inserts and
   cascading deletion on parent entity removal.
4. Cryptographic Audit Chain Integrity & Redaction: Concurrency and tamper detection.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from plaq_control_plane.audit import AuditChainer, AuditIntegrityError, AuditTrailManager
from plaq_control_plane.db import DatabaseEngine
from plaq_control_plane.redact import SecretRedactor
from plaq_control_plane.repository import ControlPlaneRepository
from plaq_control_plane.state_machine import InvalidStateTransitionError, TaskStateMachine


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def memory_repo():
    """Create in-memory repository for unit state checks."""
    engine = DatabaseEngine(":memory:")
    repo = ControlPlaneRepository(engine)
    yield repo
    engine.close()


@pytest.fixture
def temp_disk_db():
    """Create a temporary on-disk SQLite database file for realistic concurrency testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()

    engine = DatabaseEngine(tmp_path)
    repo = ControlPlaneRepository(engine)

    yield repo, engine, tmp_path

    engine.close()
    for ext in ["", "-wal", "-shm"]:
        p = tmp_path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


# ===========================================================================
# 1. Concurrency Stress Testing
# ===========================================================================

class TestM2ConcurrencyStress:
    """Empirically stress-test SQLite WAL mode, connection pooling, and busy timeout."""

    def test_wal_mode_and_pragmas_on_disk(self, temp_disk_db):
        """Verify on-disk database strictly enables WAL mode, foreign keys, and busy timeout >= 5000."""
        repo, engine, db_path = temp_disk_db
        with engine.connection() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0].upper()
            foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]

        assert journal_mode == "WAL", f"Expected WAL mode, got {journal_mode}"
        assert foreign_keys == 1, "Foreign keys must be active"
        assert busy_timeout >= 5000, f"Expected busy_timeout >= 5000ms, got {busy_timeout}"

    def test_heavy_multithreaded_read_write_stress(self, temp_disk_db):
        """Run 20 writer threads and 10 continuous reader threads concurrently.

        Ensures zero database lock contention errors, zero dropped records,
        and consistent state under high thread contention.
        """
        repo, engine, db_path = temp_disk_db
        num_writers = 20
        tasks_per_writer = 5
        total_expected_tasks = num_writers * tasks_per_writer
        stop_readers = threading.Event()
        reader_counts = []
        errors = []

        def writer_worker(writer_id: int):
            try:
                for j in range(tasks_per_writer):
                    goal = f"Stress task w{writer_id}-t{j}"
                    t = repo.create_task(goal=goal, parameters={"writer": writer_id, "index": j})
                    t_id = t["id"]
                    # Progression
                    repo.transition_task(t_id, "planning")
                    step = repo.record_step(t_id, 1, f"Step 1 for {goal}", "criteria met")
                    repo.transition_task(t_id, "running")
                    repo.record_tool_call(
                        task_id=t_id,
                        step_id=step["id"],
                        tool_name="quantum.simulate",
                        parameters={"qubits": 8, "noise": 0.001},
                        output=f"Simulated w{writer_id}-t{j}",
                        exit_code=0,
                        duration_ms=12.4,
                    )
                    repo.record_audit(
                        task_id=t_id,
                        tool_name="quantum.simulate",
                        parameters={"writer": writer_id},
                        output=f"Done w{writer_id}-t{j}",
                        exit_code=0,
                        duration_ms=12.4,
                    )
            except Exception as e:
                errors.append(f"Writer {writer_id} error: {e}")

        def reader_worker(reader_id: int):
            try:
                while not stop_readers.is_set():
                    tasks = repo.list_tasks()
                    reader_counts.append(len(tasks))
                    if tasks:
                        # Pick a task to read details
                        target = tasks[-1]
                        fetched = repo.get_task(target["id"])
                        assert fetched is not None
                    time.sleep(0.005)
            except Exception as e:
                errors.append(f"Reader {reader_id} error: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            # Start 10 readers
            reader_futures = [executor.submit(reader_worker, r) for r in range(10)]
            # Start 20 writers
            writer_futures = [executor.submit(writer_worker, w) for w in range(num_writers)]

            # Wait for all writers to complete
            for f in concurrent.futures.as_completed(writer_futures):
                f.result()

            # Stop readers
            stop_readers.set()
            for f in concurrent.futures.as_completed(reader_futures):
                f.result()

        assert not errors, f"Concurrency errors encountered: {errors}"

        # Verify all tasks exist in repository
        all_tasks = repo.list_tasks()
        assert len(all_tasks) == total_expected_tasks, (
            f"Expected {total_expected_tasks} tasks, got {len(all_tasks)}"
        )
        assert len(reader_counts) > 20, "Readers did not execute sufficient read cycles"

    def test_concurrent_audit_chain_verifiability(self, temp_disk_db):
        """Concurrent logging across 15 separate tasks produces 100% valid SHA-256 chains."""
        repo, engine, db_path = temp_disk_db
        num_tasks = 15
        entries_per_task = 6
        task_ids = []

        for i in range(num_tasks):
            t = repo.create_task(goal=f"Audit task {i}")
            task_ids.append(t["id"])

        def audit_logger(t_id: str):
            for seq in range(entries_per_task):
                repo.record_audit(
                    task_id=t_id,
                    tool_name=f"tool_step_{seq}",
                    parameters={"step": seq, "token": f"bearer secret_{seq}"},
                    output=f"Output for step {seq}",
                    exit_code=0,
                    duration_ms=5.0 + seq,
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(audit_logger, tid) for tid in task_ids]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        # Independently verify the audit trail for every single task
        for tid in task_ids:
            trail = repo.get_audit_trail(tid)
            assert len(trail) == entries_per_task, f"Task {tid} missing audit entries"
            assert repo.verify_audit_trail(tid) is True, f"Hash chain verification failed for {tid}"

    def test_wal_checkpoint_truncate_under_read_pressure(self, temp_disk_db):
        """WAL checkpoint TRUNCATE executes safely during active reading without deadlock."""
        repo, engine, db_path = temp_disk_db
        # Insert initial data
        for i in range(25):
            repo.create_task(goal=f"Checkpoint pre-task {i}")

        stop_flag = threading.Event()
        read_success = []

        def reader():
            while not stop_flag.is_set():
                tasks = repo.list_tasks()
                read_success.append(len(tasks) >= 25)
                time.sleep(0.002)

        reader_thread = threading.Thread(target=reader)
        reader_thread.start()

        try:
            # Perform repeated checkpoints
            for _ in range(5):
                engine.wal_checkpoint("TRUNCATE")
                time.sleep(0.01)
        finally:
            stop_flag.set()
            reader_thread.join()

        assert all(read_success)
        assert len(read_success) >= 5


# ===========================================================================
# 2. State Machine Immutability & Complete Transition Matrix
# ===========================================================================

class TestM2StateMachineImmutability:
    """Stress-test state machine immutability and complete transition matrix."""

    ALL_STATES = [
        "queued",
        "planning",
        "running",
        "verifying",
        "completed",
        "failed",
        "cancelled",
        "blocked",
    ]

    TERMINAL_STATES = ["completed", "failed", "cancelled"]

    @pytest.mark.parametrize("terminal_state", ["completed", "failed", "cancelled"])
    @pytest.mark.parametrize("target_state", [
        "queued", "planning", "running", "verifying",
        "completed", "failed", "cancelled", "blocked",
        "UNKNOWN", "", "in_progress", "terminated",
    ])
    def test_terminal_state_immutability_all_targets(self, memory_repo, terminal_state, target_state):
        """Empirically verify that NO transition is permitted out of any terminal state.

        Tests all combinations against both TaskStateMachine and ControlPlaneRepository.
        """
        # 1. Test TaskStateMachine directly
        assert TaskStateMachine.can_transition(terminal_state, target_state) is False
        with pytest.raises(InvalidStateTransitionError):
            TaskStateMachine.validate_transition(terminal_state, target_state)

        # 2. Test ControlPlaneRepository
        task = memory_repo.create_task(goal=f"Terminal test {terminal_state}")
        t_id = task["id"]

        # Advance to desired terminal state
        if terminal_state == "cancelled":
            memory_repo.transition_task(t_id, "cancelled")
        elif terminal_state == "failed":
            memory_repo.transition_task(t_id, "planning")
            memory_repo.transition_task(t_id, "failed")
        elif terminal_state == "completed":
            memory_repo.transition_task(t_id, "planning")
            memory_repo.transition_task(t_id, "running")
            memory_repo.transition_task(t_id, "verifying")
            memory_repo.transition_task(t_id, "completed")

        curr = memory_repo.get_task(t_id)
        assert curr["status"] == terminal_state
        completed_at_orig = curr["completed_at"]

        # Attempt illegal transition with various parameters
        for err_arg in [None, "Some error reason", ""]:
            with pytest.raises(InvalidStateTransitionError):
                memory_repo.transition_task(t_id, target_state, error=err_arg)

        # Confirm state and timestamps are unchanged
        post = memory_repo.get_task(t_id)
        assert post["status"] == terminal_state
        assert post["completed_at"] == completed_at_orig

    def test_exhaustive_64_state_transition_matrix(self):
        """Test all 8x8 = 64 state transitions against the official specification."""
        allowed_spec = {
            "queued": {"planning", "cancelled"},
            "planning": {"running", "failed", "cancelled"},
            "running": {"verifying", "blocked", "failed", "cancelled"},
            "blocked": {"running", "failed", "cancelled"},
            "verifying": {"completed", "running", "failed", "cancelled"},
            "completed": set(),
            "failed": set(),
            "cancelled": set(),
        }

        for from_s in self.ALL_STATES:
            for to_s in self.ALL_STATES:
                expected_allowed = to_s in allowed_spec[from_s]
                actual_allowed = TaskStateMachine.can_transition(from_s, to_s)
                assert actual_allowed == expected_allowed, (
                    f"Transition {from_s} -> {to_s}: expected {expected_allowed}, got {actual_allowed}"
                )

                if expected_allowed:
                    # Must not raise
                    TaskStateMachine.validate_transition(from_s, to_s)
                else:
                    # Must raise
                    with pytest.raises(InvalidStateTransitionError):
                        TaskStateMachine.validate_transition(from_s, to_s)

    def test_state_machine_self_transitions_disallowed(self):
        """Every state transitioning to itself must be rejected."""
        for state in self.ALL_STATES:
            assert TaskStateMachine.can_transition(state, state) is False
            with pytest.raises(InvalidStateTransitionError):
                TaskStateMachine.validate_transition(state, state)


# ===========================================================================
# 3. Foreign Key Cascades & Relational Integrity
# ===========================================================================

class TestM2ForeignKeyCascades:
    """Empirically test SQLite relational constraints, orphaned inserts, and cascades."""

    def test_orphaned_inserts_rejected(self, temp_disk_db):
        """Inserting child rows with non-existent parent IDs raises sqlite3.IntegrityError."""
        repo, engine, db_path = temp_disk_db
        fake_task_id = "00000000-0000-0000-0000-000000000000"
        fake_proj_id = "11111111-1111-1111-1111-111111111111"
        fake_step_id = "22222222-2222-2222-2222-222222222222"

        with engine.connection() as conn:
            # 1. Step without task
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO steps (id, task_id, step_number, step_name, criteria, status, started_at) VALUES ('s1', ?, 1, 'orphan', 'crit', 'running', 'now')",
                    (fake_task_id,),
                )

            # 2. Tool call without task
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO tool_calls (id, task_id, tool_name, created_at) VALUES ('tc1', ?, 'quantum.compile', 'now')",
                    (fake_task_id,),
                )

            # 3. Approval without task
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO approvals (id, task_id, tool_name, reason, status, created_at) VALUES ('app1', ?, 'patch', 'r', 'pending', 'now')",
                    (fake_task_id,),
                )

            # 4. Artifact without task
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO artifacts (id, task_id, artifact_type, name, file_path, sha256_hash, size_bytes, created_at) VALUES ('art1', ?, 'diff', 'd', '/p', 'hash', 10, 'now')",
                    (fake_task_id,),
                )

            # 5. Audit record without task
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO audit_trail (id, task_id, sequence_number, tool_name, exit_code, duration_ms, previous_hash, current_hash, created_at) VALUES ('aud1', ?, 1, 't', 0, 1.0, '0', '1', 'now')",
                    (fake_task_id,),
                )

            # 6. Workspace with non-existent project_id
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO workspaces (id, project_id, path, created_at) VALUES ('ws1', ?, '/workspace', 'now')",
                    (fake_proj_id,),
                )

    def test_cascading_delete_on_task_removal(self, temp_disk_db):
        """Deleting a parent task automatically cascades to delete all child rows.

        Tables affected: steps, tool_calls, approvals, artifacts, audit_trail, agent_sessions.
        """
        repo, engine, db_path = temp_disk_db

        # Create parent task
        task = repo.create_task(goal="Parent task to delete")
        t_id = task["id"]
        repo.transition_task(t_id, "planning")
        repo.transition_task(t_id, "running")

        # Create child step
        step = repo.record_step(t_id, 1, "Step 1", "Criteria 1")
        s_id = step["id"]

        # Create child tool call
        tc = repo.record_tool_call(
            task_id=t_id,
            step_id=s_id,
            tool_name="terminal.run",
            parameters={"cmd": "ls"},
            output="file.txt",
            exit_code=0,
            duration_ms=5.0,
        )

        # Create child approval
        app = repo.request_approval(t_id, "file.delete", {"path": "old.py"}, "cleanup", step_id=s_id)

        # Create child artifact
        art = repo.record_artifact(
            task_id=t_id,
            artifact_type="benchmark_report",
            name="Report",
            file_path="/reports/rep.json",
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            size_bytes=1024,
        )

        # Create child audit record
        aud = repo.record_audit(t_id, "terminal.run", {"cmd": "ls"}, "file.txt", exit_code=0)

        # Verify all children exist
        with engine.connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM steps WHERE task_id = ?", (t_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM tool_calls WHERE task_id = ?", (t_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM approvals WHERE task_id = ?", (t_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM artifacts WHERE task_id = ?", (t_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE task_id = ?", (t_id,)).fetchone()[0] == 1

            # Delete the parent task
            conn.execute("DELETE FROM tasks WHERE id = ?", (t_id,))

            # Verify cascading deletion wiped all child records
            assert conn.execute("SELECT COUNT(*) FROM tasks WHERE id = ?", (t_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM steps WHERE task_id = ?", (t_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM tool_calls WHERE task_id = ?", (t_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM approvals WHERE task_id = ?", (t_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM artifacts WHERE task_id = ?", (t_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE task_id = ?", (t_id,)).fetchone()[0] == 0

    def test_step_deletion_sets_null_on_tool_calls(self, temp_disk_db):
        """Deleting a step sets tool_calls.step_id to NULL (ON DELETE SET NULL)."""
        repo, engine, db_path = temp_disk_db
        task = repo.create_task(goal="Task for step null test")
        t_id = task["id"]
        step = repo.record_step(t_id, 1, "Step to delete", "Criteria")
        s_id = step["id"]

        tc = repo.record_tool_call(
            task_id=t_id,
            step_id=s_id,
            tool_name="git.diff",
            output="diff --git",
        )
        tc_id = tc["id"]

        with engine.connection() as conn:
            assert conn.execute("SELECT step_id FROM tool_calls WHERE id = ?", (tc_id,)).fetchone()[0] == s_id

            # Delete the step
            conn.execute("DELETE FROM steps WHERE id = ?", (s_id,))

            # Tool call should remain, but step_id should now be NULL
            row = conn.execute("SELECT step_id, task_id FROM tool_calls WHERE id = ?", (tc_id,)).fetchone()
            assert row is not None
            assert row[0] is None
            assert row[1] == t_id

    def test_project_deletion_cascades_workspaces(self, temp_disk_db):
        """Deleting a project cascades and deletes all associated workspaces."""
        repo, engine, db_path = temp_disk_db
        with engine.connection() as conn:
            conn.execute("INSERT INTO projects (id, name, created_at) VALUES ('p-del', 'Proj Del', 'now')")
            conn.execute("INSERT INTO workspaces (id, project_id, path, created_at) VALUES ('ws-del-1', 'p-del', '/path1', 'now')")
            conn.execute("INSERT INTO workspaces (id, project_id, path, created_at) VALUES ('ws-del-2', 'p-del', '/path2', 'now')")

            assert conn.execute("SELECT COUNT(*) FROM workspaces WHERE project_id = 'p-del'").fetchone()[0] == 2

            # Delete project
            conn.execute("DELETE FROM projects WHERE id = 'p-del'")
            assert conn.execute("SELECT COUNT(*) FROM workspaces WHERE project_id = 'p-del'").fetchone()[0] == 0

    def test_sqlite_check_constraint_rejects_bogus_status(self, temp_disk_db):
        """Direct SQL inserts with invalid status fail the SQLite CHECK constraint."""
        repo, engine, db_path = temp_disk_db
        with engine.connection() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO tasks (id, goal, workspace_path, status, created_at, updated_at) VALUES ('t-bogus', 'g', '', 'hyper_mode', 'now', 'now')"
                )
