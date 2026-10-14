"""Unit and integration tests for plaq_control_plane package."""

import json
import os
import tempfile
import pytest

from plaq_control_plane import (
    AuditChainer,
    CheckpointRecoveryManager,
    ControlPlaneDatabase,
    ControlPlaneRepository,
    DatabaseEngine,
    InvalidStateTransitionError,
    SecretRedactor,
    TaskStateMachine,
)


@pytest.fixture
def memory_repo():
    engine = DatabaseEngine(":memory:")
    repo = ControlPlaneRepository(engine)
    yield repo
    engine.close()


def test_schema_and_pragmas():
    engine = DatabaseEngine(":memory:")
    conn = engine.conn
    journal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    # For in-memory database SQLite journal_mode is memory or wal
    fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    busy = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    assert fk == 1
    assert busy >= 5000
    engine.close()


def test_task_crud_and_validation(memory_repo):
    with pytest.raises(ValueError, match="empty"):
        memory_repo.create_task("")

    task = memory_repo.create_task("Test task", parameters={"qubits": 6})
    t_id = task["id"]
    assert task["status"] == "queued"
    assert json.loads(task["parameters"])["qubits"] == 6

    # Test transitions
    memory_repo.transition_task(t_id, "planning")
    assert memory_repo.get_task(t_id)["status"] == "planning"

    memory_repo.transition_task(t_id, "running")
    assert memory_repo.get_task(t_id)["status"] == "running"

    with pytest.raises(InvalidStateTransitionError):
        memory_repo.transition_task(t_id, "completed")

    memory_repo.transition_task(t_id, "verifying")
    memory_repo.transition_task(t_id, "completed")
    assert memory_repo.get_task(t_id)["completed_at"] is not None

    with pytest.raises(InvalidStateTransitionError):
        memory_repo.transition_task(t_id, "running")


def test_step_and_tool_call_lifecycle(memory_repo):
    task = memory_repo.create_task("Step task")
    t_id = task["id"]

    step = memory_repo.record_step(t_id, 1, "Compile circuit", "depth <= 100")
    assert step["task_id"] == t_id
    assert step["status"] == "running"

    updated_task = memory_repo.get_task(t_id)
    assert updated_task["current_step_id"] == step["id"]

    call = memory_repo.record_tool_call(
        task_id=t_id,
        step_id=step["id"],
        tool_name="quantum.compile",
        parameters={"qubits": 4},
        output="compiled",
        exit_code=0,
        duration_ms=15.5,
    )
    assert call["tool_name"] == "quantum.compile"
    assert call["exit_code"] == 0


def test_approval_flow_and_gating(memory_repo):
    task = memory_repo.create_task("Approval task")
    t_id = task["id"]
    memory_repo.transition_task(t_id, "planning")
    memory_repo.transition_task(t_id, "running")

    app = memory_repo.request_approval(
        task_id=t_id,
        tool_name="workspace.patch",
        parameters={"file": "test.py"},
        reason="Check changes",
    )
    assert memory_repo.get_task(t_id)["status"] == "blocked"

    memory_repo.decide_approval(app["id"], approved=True, reason="Looks good")
    assert memory_repo.get_task(t_id)["status"] == "running"


def test_audit_hash_chain_and_redaction(memory_repo):
    task = memory_repo.create_task("Audit task")
    t_id = task["id"]

    r1 = memory_repo.record_audit(
        task_id=t_id,
        tool_name="tool1",
        parameters={"auth_token": "secret_abc"},
        output="Authorization: Bearer secret_xyz",
    )
    assert r1["sequence_number"] == 1
    assert r1["previous_hash"] == AuditChainer.GENESIS_HASH
    assert "secret_abc" not in r1["parameters"]
    assert "secret_xyz" not in r1["output"]

    r2 = memory_repo.record_audit(
        task_id=t_id,
        tool_name="tool2",
        parameters={"ok": True},
        output="done",
    )
    assert r2["sequence_number"] == 2
    assert r2["previous_hash"] == r1["current_hash"]
    assert memory_repo.verify_audit_trail(t_id) is True


def test_checkpoint_recovery_manager(memory_repo):
    t1 = memory_repo.create_task("In flight 1")
    memory_repo.transition_task(t1["id"], "planning")

    t2 = memory_repo.create_task("Completed task")
    memory_repo.transition_task(t2["id"], "planning")
    memory_repo.transition_task(t2["id"], "running")
    memory_repo.transition_task(t2["id"], "verifying")
    memory_repo.transition_task(t2["id"], "completed")

    recovery = CheckpointRecoveryManager(memory_repo)
    active = recovery.scan_active_tasks()
    active_ids = {t["id"] for t in active}
    assert t1["id"] in active_ids
    assert t2["id"] not in active_ids

    ctx = recovery.rehydrate_task(t1["id"])
    assert ctx.status == "planning"
    assert ctx.recommended_action == "resume_planning"
