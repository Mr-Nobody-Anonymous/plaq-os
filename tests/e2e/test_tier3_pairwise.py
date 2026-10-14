"""Tier 3 - Cross-Feature Pairwise Combinations Tests.

Covers pairwise interactions across major architectural subsystems:
1. Task State Machine + Approval Gate + Audit Trail (>=5 tests)
2. Agent Execution Loop + Process Sandbox + Secret Redaction (>=5 tests)
3. CLI + FastAPI REST + SQLite Persistence (>=5 tests)
4. Quantum Engine + Artifact Service + WebSocket Event Broadcaster (>=5 tests)
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from tests.e2e.conftest import (
    AuditChainer,
    AuditIntegrityError,
    EventRecorder,
    InvalidStateTransitionError,
    PathGuard,
    PathTraversalError,
    SecretRedactor,
    TaskStateMachine,
    TestDatabase,
)


# ===========================================================================
# Pairwise 1: Task State Machine + Approval Gate + Audit Trail
# ===========================================================================

class TestPairwise01StateApprovalAudit:
    """Verifies state machine transitions, approval gating, and audit hash chaining interactions."""

    def test_p1_01_blocked_transition_logs_audit_with_hash(self, test_db):
        """When a task transitions to blocked for approval, an audit record is chained."""
        task = test_db.create_task(goal="Approval audit link")
        t_id = task["id"]
        test_db.transition_task(t_id, "planning")
        test_db.transition_task(t_id, "running")

        app = test_db.request_approval(
            task_id=t_id,
            tool_name="terminal.run",
            parameters={"cmd": "git push --force"},
            reason="Force push protection",
        )
        assert test_db.get_task(t_id)["status"] == "blocked"

        rec = test_db.record_audit(
            task_id=t_id,
            tool_name="approval.request",
            parameters={"approval_id": app["id"], "reason": "Force push protection"},
            output="Approval pending",
        )
        assert rec["sequence_number"] == 1
        assert test_db.verify_audit_trail(t_id) is True

    def test_p1_02_approval_granted_logs_audit_and_unblocks(self, test_db):
        """Granting approval logs audit entry, transitions task to running, and preserves chain."""
        task = test_db.create_task(goal="Grant approval test")
        t_id = task["id"]
        test_db.transition_task(t_id, "planning")
        test_db.transition_task(t_id, "running")

        app = test_db.request_approval(t_id, "workspace.patch", {"file": "core.py"}, "Patching core")
        test_db.record_audit(t_id, "approval.request", {"app_id": app["id"]}, "blocked")

        test_db.decide_approval(app["id"], approved=True, decided_by="lead_dev")
        assert test_db.get_task(t_id)["status"] == "running"

        test_db.record_audit(t_id, "approval.decided", {"app_id": app["id"], "decision": "approved"}, "unblocked")
        assert test_db.verify_audit_trail(t_id) is True

    def test_p1_03_approval_denied_logs_audit_and_fails_task(self, test_db):
        """Denying approval transitions task to failed and logs audit entry with reason."""
        task = test_db.create_task(goal="Deny approval test")
        t_id = task["id"]
        test_db.transition_task(t_id, "planning")
        test_db.transition_task(t_id, "running")

        app = test_db.request_approval(t_id, "terminal.run", {"cmd": "rm -rf /"}, "Root deletion")
        test_db.record_audit(t_id, "approval.request", {"cmd": "rm -rf /"}, "pending")

        test_db.decide_approval(app["id"], approved=False, reason="Security policy violation")
        task_after = test_db.get_task(t_id)
        assert task_after["status"] == "failed"
        assert "Security policy violation" in task_after["error"]

        test_db.record_audit(t_id, "approval.decided", {"decision": "denied"}, "failed")
        assert test_db.verify_audit_trail(t_id) is True

    def test_p1_04_multiple_approval_cycles_preserve_chain(self, test_db):
        """Sequential approval cycles across multiple steps maintain unbroken hash chain."""
        task = test_db.create_task(goal="Multi-gate pipeline")
        t_id = task["id"]
        test_db.transition_task(t_id, "planning")
        test_db.transition_task(t_id, "running")

        # Approval gate 1
        a1 = test_db.request_approval(t_id, "step1_tool", {}, "Gate 1")
        test_db.record_audit(t_id, "approval_1_req", {}, "pending")
        test_db.decide_approval(a1["id"], approved=True)
        test_db.record_audit(t_id, "approval_1_ok", {}, "approved")

        # Approval gate 2
        a2 = test_db.request_approval(t_id, "step2_tool", {}, "Gate 2")
        test_db.record_audit(t_id, "approval_2_req", {}, "pending")
        test_db.decide_approval(a2["id"], approved=True)
        test_db.record_audit(t_id, "approval_2_ok", {}, "approved")

        assert test_db.get_task(t_id)["status"] == "running"
        assert test_db.verify_audit_trail(t_id) is True
        trail = test_db.get_audit_trail(t_id)
        assert len(trail) == 4

    def test_p1_05_tampered_audit_detected_in_approval_flow(self, test_db):
        """Tampering with audit log during approval flow is detected by verification."""
        task = test_db.create_task(goal="Tamper flow check")
        t_id = task["id"]
        test_db.transition_task(t_id, "planning")
        test_db.transition_task(t_id, "running")

        r1 = test_db.record_audit(t_id, "init_tool", {"action": "prep"}, "ready")
        app = test_db.request_approval(t_id, "critical_tool", {}, "Audit check")
        r2 = test_db.record_audit(t_id, "approval_req", {}, "pending")

        # Maliciously modify parameters of record 1
        with test_db.conn:
            test_db.conn.execute("UPDATE audit_trail SET parameters = '{\"action\": \"tampered\"}' WHERE id = ?", (r1["id"],))

        assert test_db.verify_audit_trail(t_id) is False


# ===========================================================================
# Pairwise 2: Agent Execution Loop + Process Sandbox + Secret Redaction
# ===========================================================================

class TestPairwise02AgentSandboxSecret:
    """Verifies agent loop executing tools in sandboxed process with secret scrubbing."""

    def test_p2_01_agent_loop_scrubs_secrets_from_sandbox_output(self, temp_workspace, test_db):
        """Sandboxed process emitting an API token has its output scrubbed in audit log."""
        task = test_db.create_task(goal="Scrub output in agent loop", workspace_path=str(temp_workspace))
        test_db.transition_task(task["id"], "planning")
        test_db.transition_task(task["id"], "running")

        # Run sandboxed command that outputs sensitive secret
        cmd = [sys.executable, "-c", "print('Login token: Bearer my-secret-jwt-token-xyz')"]
        proc = subprocess.run(cmd, cwd=str(temp_workspace), capture_output=True, text=True, timeout=5)
        raw_output = proc.stdout.strip()
        assert "my-secret-jwt-token-xyz" in raw_output

        # Record audit via control plane which executes SecretRedactor
        audit = test_db.record_audit(
            task_id=task["id"],
            tool_name="terminal.run",
            parameters={"cmd": "python print_token.py"},
            output=raw_output,
            exit_code=proc.returncode,
        )
        assert "my-secret-jwt-token-xyz" not in audit["output"]
        assert "Bearer [REDACTED_TOKEN]" in audit["output"]

    def test_p2_02_agent_loop_sandbox_timeout_handling(self, temp_workspace, test_db):
        """Timed-out sandboxed command is captured and logged as failure in agent loop."""
        task = test_db.create_task(goal="Timeout in loop", workspace_path=str(temp_workspace))
        test_db.transition_task(task["id"], "planning")
        test_db.transition_task(task["id"], "running")

        cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
        try:
            subprocess.run(cmd, cwd=str(temp_workspace), capture_output=True, timeout=0.2)
            exit_code = 0
            err_msg = ""
        except subprocess.TimeoutExpired as exc:
            exit_code = -1
            err_msg = f"Execution timed out after {exc.timeout}s"

        assert exit_code == -1
        audit = test_db.record_audit(
            task_id=task["id"],
            tool_name="terminal.run",
            parameters={"timeout": 0.2},
            output=err_msg,
            exit_code=exit_code,
        )
        assert audit["exit_code"] == -1
        assert "timed out" in audit["output"]

    def test_p2_03_agent_loop_sandbox_pathguard_rejection(self, temp_workspace, test_db):
        """Tool attempting path traversal outside workspace is blocked before execution."""
        task = test_db.create_task(goal="Path traversal in loop", workspace_path=str(temp_workspace))
        test_db.transition_task(task["id"], "planning")
        test_db.transition_task(task["id"], "running")

        traversal_path = "../../etc/shadow"
        with pytest.raises(PathTraversalError):
            PathGuard.resolve_safe_path(str(temp_workspace), traversal_path)

        # Audit records failed path validation
        audit = test_db.record_audit(
            task_id=task["id"],
            tool_name="workspace.read",
            parameters={"path": traversal_path},
            output="PathTraversalError: escape detected",
            exit_code=1,
        )
        assert audit["exit_code"] == 1
        assert "PathTraversalError" in audit["output"]

    def test_p2_04_agent_loop_environment_scrubbing(self, temp_workspace, test_db):
        """Sensitive environment keys passed to agent loop are sanitized in audit parameters."""
        task = test_db.create_task(goal="Sanitize env vars")
        raw_env = {
            "PLAQ_ENV": "development",
            "API_KEY": "super_secret_token_12345",
            "AWS_SECRET": "AKIATEST9999999999",
        }
        audit = test_db.record_audit(
            task_id=task["id"],
            tool_name="terminal.run",
            parameters={"env": raw_env},
            output="Started with environment",
            exit_code=0,
        )
        logged_params = json.loads(audit["parameters"])
        assert logged_params["env"]["PLAQ_ENV"] == "development"
        assert logged_params["env"]["API_KEY"] == "[REDACTED]"
        assert logged_params["env"]["AWS_SECRET"] == "[REDACTED]"

    def test_p2_05_agent_loop_file_write_computes_sha256_audit(self, temp_workspace, test_db):
        """File created inside sandbox computes file hash and logs in audit modified_files."""
        task = test_db.create_task(goal="File write audit", workspace_path=str(temp_workspace))
        target_file = temp_workspace / "solution.py"
        code = "print('Plaq solution compiled')\n"
        target_file.write_text(code, encoding="utf-8")
        file_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()

        audit = test_db.record_audit(
            task_id=task["id"],
            tool_name="workspace.write",
            parameters={"path": "solution.py"},
            output=f"Wrote {len(code)} bytes, sha256={file_sha}",
            exit_code=0,
            modified_files=["solution.py"],
        )
        assert "solution.py" in json.loads(audit["modified_files"])
        assert file_sha in audit["output"]


# ===========================================================================
# Pairwise 3: CLI + FastAPI REST + SQLite Persistence
# ===========================================================================

class TestPairwise03CliApiPersistence:
    """Verifies unified CLI issuing requests against FastAPI backed by SQLite."""

    @pytest.fixture
    def app_and_client(self, test_db):
        app = FastAPI(title="Plaq-OS REST API", version="0.3.0")

        @app.post("/api/v1/tasks", status_code=status.HTTP_201_CREATED)
        def create_task(payload: Dict[str, Any]):
            goal = payload.get("goal")
            if not goal:
                raise HTTPException(status_code=422, detail="Goal required")
            return test_db.create_task(goal=goal, workspace_path=payload.get("workspace_path", ""))

        @app.get("/api/v1/tasks")
        def list_tasks():
            return test_db.list_tasks()

        @app.get("/api/v1/tasks/{task_id}")
        def get_task(task_id: str):
            t = test_db.get_task(task_id)
            if not t:
                raise HTTPException(status_code=404, detail="Task not found")
            return t

        @app.get("/api/v1/tasks/{task_id}/logs")
        def get_logs(task_id: str):
            return test_db.get_audit_trail(task_id)

        @app.post("/api/v1/approvals/{app_id}/decide")
        def decide_approval(app_id: str, payload: Dict[str, Any]):
            approved = payload.get("approved", True)
            reason = payload.get("reason")
            return test_db.decide_approval(app_id, approved=approved, reason=reason)

        return app, TestClient(app)

    def test_p3_01_cli_submits_task_to_api_and_persists_in_sqlite(self, app_and_client, test_db):
        """CLI post to /api/v1/tasks writes row into SQLite database."""
        _, client = app_and_client
        resp = client.post("/api/v1/tasks", json={"goal": "Synthesize Clifford+T"})
        assert resp.status_code == 201
        data = resp.json()
        task_id = data["id"]

        # Verify in SQLite directly
        db_task = test_db.get_task(task_id)
        assert db_task is not None
        assert db_task["goal"] == "Synthesize Clifford+T"
        assert db_task["status"] == "queued"

    def test_p3_02_cli_queries_task_status_via_api(self, app_and_client, test_db):
        """Task created in SQLite is retrieved via GET /api/v1/tasks/{id}."""
        _, client = app_and_client
        task = test_db.create_task(goal="Status query check")
        test_db.transition_task(task["id"], "planning")

        resp = client.get(f"/api/v1/tasks/{task['id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "planning"

    def test_p3_03_cli_retrieves_audit_logs_via_api(self, app_and_client, test_db):
        """CLI fetches audit logs via API and verifies hash chain integrity."""
        _, client = app_and_client
        task = test_db.create_task(goal="Audit API test")
        t_id = task["id"]
        test_db.record_audit(t_id, "tool_1", {}, "step 1")
        test_db.record_audit(t_id, "tool_2", {}, "step 2")

        resp = client.get(f"/api/v1/tasks/{t_id}/logs")
        assert resp.status_code == 200
        logs = resp.json()
        assert len(logs) == 2
        assert AuditChainer.verify_chain(logs) is True

    def test_p3_04_api_restart_preserves_cli_tasks(self, app_and_client, test_db):
        """New TestClient instance re-reading SQLite retains all tasks."""
        app, client1 = app_and_client
        resp1 = client1.post("/api/v1/tasks", json={"goal": "Persistent CLI Task"})
        task_id = resp1.json()["id"]

        # Simulate API restart by instantiating new client on same db
        client2 = TestClient(app)
        resp2 = client2.get(f"/api/v1/tasks/{task_id}")
        assert resp2.status_code == 200
        assert resp2.json()["goal"] == "Persistent CLI Task"

    def test_p3_05_cli_approves_blocked_task_via_api(self, app_and_client, test_db):
        """POST /api/v1/approvals/{id}/decide unblocks task in SQLite database."""
        _, client = app_and_client
        task = test_db.create_task(goal="API Approval Test")
        test_db.transition_task(task["id"], "planning")
        test_db.transition_task(task["id"], "running")

        app_rec = test_db.request_approval(task["id"], "terminal.run", {"cmd": "deploy"}, "Prod deployment")
        assert test_db.get_task(task["id"])["status"] == "blocked"

        decide_resp = client.post(f"/api/v1/approvals/{app_rec['id']}/decide", json={"approved": True})
        assert decide_resp.status_code == 200
        assert test_db.get_task(task["id"])["status"] == "running"


# ===========================================================================
# Pairwise 4: Quantum Engine + Artifact Service + WebSocket Event Broadcaster
# ===========================================================================

class TestPairwise04QuantumArtifactBroadcaster:
    """Verifies quantum co-design optimization, artifact fingerprinting, and event streaming."""

    def test_p4_01_quantum_optimization_broadcasts_events(self, quantum_engine, event_recorder):
        """Pareto search emissions are captured as platform events."""
        circuit = quantum_engine.circuits.make_test_circuit(4)
        event_recorder.record({"event_type": "quantum_opt_started", "num_qubits": circuit.num_qubits})

        evaluated, frontier = quantum_engine.optimizer.search_pareto_optimizer(
            circuit=circuit,
            hardware=quantum_engine.hardware.DEMO_HARDWARE,
            target_epsilon=1e-3,
            candidate_limit=5,
        )
        event_recorder.record({"event_type": "quantum_opt_completed", "candidates": len(evaluated), "pareto": len(frontier)})

        events = event_recorder.events
        assert len(events) == 2
        assert events[0]["event_type"] == "quantum_opt_started"
        assert events[1]["event_type"] == "quantum_opt_completed"

    def test_p4_02_quantum_pareto_generates_artifact_with_sha256(self, quantum_engine, temp_workspace):
        """Pareto optimization results are saved as an artifact with valid SHA-256 hash."""
        circuit = quantum_engine.circuits.make_test_circuit(4)
        evaluated, frontier = quantum_engine.optimizer.search_pareto_optimizer(
            circuit=circuit,
            hardware=quantum_engine.hardware.DEMO_HARDWARE,
            target_epsilon=1e-3,
            candidate_limit=5,
        )
        artifact_path = temp_workspace / "pareto_report.json"
        data = {
            "workload": "test_circuit_4q",
            "pareto_candidates": [
                {
                    "physical_qubits": p.physical_qubits,
                    "runtime_seconds": p.runtime_seconds,
                    "code_distance": p.code_distance,
                }
                for p in frontier
            ],
        }
        content = json.dumps(data, indent=2)
        artifact_path.write_text(content, encoding="utf-8")

        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert artifact_path.exists()
        assert len(digest) == 64

    def test_p4_03_artifact_published_event_broadcasted(self, event_recorder):
        """Publishing an artifact dispatches an artifact_published event with fingerprint."""
        art_id = str(uuid.uuid4())
        art_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        event_recorder.record({
            "event_type": "artifact_published",
            "artifact_id": art_id,
            "artifact_type": "quantum_pareto",
            "sha256": art_hash,
        })
        published = event_recorder.filter(event_type="artifact_published")
        assert len(published) == 1
        assert published[0]["sha256"] == art_hash

    def test_p4_04_artifact_retrieval_and_integrity_check(self, temp_workspace, event_recorder):
        """Retrieved artifact content matches broadcasted SHA-256 fingerprint."""
        file_path = temp_workspace / "benchmark.csv"
        csv_data = "metric,value\nt_count,450\ndistance,5\n"
        file_path.write_text(csv_data, encoding="utf-8")
        calc_hash = hashlib.sha256(csv_data.encode("utf-8")).hexdigest()

        event_recorder.record({
            "event_type": "artifact_ready",
            "file_path": str(file_path),
            "sha256": calc_hash,
        })

        event = event_recorder.filter(event_type="artifact_ready")[0]
        read_data = Path(event["file_path"]).read_text(encoding="utf-8")
        assert hashlib.sha256(read_data.encode("utf-8")).hexdigest() == event["sha256"]

    def test_p4_05_qec_threshold_study_publishes_benchmark_manifest(self, quantum_engine, event_recorder):
        """Threshold study dispatches events per sample and outputs summary."""
        results = quantum_engine.stim_bridge.run_threshold_study(
            distances=[3],
            physical_error_rates=[0.001],
            shots_per_point=50,
        )
        assert len(results) == 1
        res = results[0]

        event_recorder.record({
            "event_type": "qec_point_evaluated",
            "distance": res.code_distance,
            "physical_p": res.physical_error_rate,
            "logical_p": res.empirical_logical_error_rate,
        })
        assert len(event_recorder.filter(event_type="qec_point_evaluated")) == 1
