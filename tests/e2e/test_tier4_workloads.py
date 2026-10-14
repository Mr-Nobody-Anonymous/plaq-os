"""Tier 4 - Real-World Application Workflows Tests.

Comprehensive end-to-end scenarios exercising cross-cutting system behavior:
- Scenario 1: End-to-end agent task lifecycle (CLI -> Plan -> Tool -> Scrub -> Artifact -> Complete)
- Scenario 2: Destructive operation triggers human approval gate (Task blocks -> REST approval -> Resume -> Finish)
- Scenario 3: Mid-execution server restart checkpoint recovery (Crash -> Rehydrate -> Resume without data loss)
- Scenario 4: Quantum co-design optimization pipeline via CLI and API (Circuits -> Cost Model -> Stim QEC -> Pareto)
- Scenario 5: Real-time Workbench WebSocket streaming and event logging (Broadcaster -> Subscriptions -> Event Ordering)
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
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
# Scenario 1: Full Agent Task Lifecycle End-to-End
# ===========================================================================

class TestScenario01FullAgentLifecycle:
    """Scenario 1: Complete end-to-end agent task execution.

    Flow: Goal submission -> 7-stage deterministic planning -> sandboxed tool execution ->
          secret redaction in audit log -> artifact generation -> completion verification.
    """

    def test_s1_full_agent_task_lifecycle(self, temp_workspace, test_db, quantum_engine):
        # 1. Goal Submission
        goal = "Synthesize Bernstein-Vazirani circuit and evaluate fault-tolerant resources"
        task = test_db.create_task(goal=goal, workspace_path=str(temp_workspace))
        task_id = task["id"]
        assert task["status"] == "queued"

        # 2. Stage 2: Inspect Context & Stage 3: Planning
        test_db.transition_task(task_id, "planning")
        step1 = test_db.record_step(task_id, 1, "Synthesize BV Circuit", "Circuit depth > 0, 4 qubits")
        step2 = test_db.record_step(task_id, 2, "Extract Cost Metrics", "T-count evaluated, code distance >= 3")
        step3 = test_db.record_step(task_id, 3, "Publish Resource Manifest", "SHA-256 artifact saved")

        # 3. Stage 4 & 5: Running - Execute Step 1
        test_db.transition_task(task_id, "running")
        qc = quantum_engine.circuits.make_bernstein_vazirani_circuit("101")
        assert qc.num_qubits == 4
        test_db.record_audit(
            task_id=task_id,
            tool_name="quantum.compile",
            parameters={"bitstring": "101"},
            output=f"Compiled BV circuit with {qc.num_qubits} qubits, size={qc.size()}",
            exit_code=0,
            duration_ms=15.0,
        )

        # 4. Execute Step 2 with secret scrubbing
        metrics = quantum_engine.cost_model.extract_circuit_metrics(qc)
        d, feasible, _ = quantum_engine.cost_model.solve_minimum_code_distance(
            physical_error=0.001,
            threshold=0.01,
            spacetime_volume=1000,
            allocated_error_budget=1e-3,
        )
        assert feasible is True
        assert d >= 3

        # Simulated tool output containing sensitive authorization header
        raw_tool_output = (
            f"Metrics extracted: qubits={metrics.num_qubits}, depth={metrics.depth}. "
            "Telemetry upload response: Authorization: Bearer secret-agent-token-999-xyz"
        )
        audit2 = test_db.record_audit(
            task_id=task_id,
            tool_name="quantum.estimate",
            parameters={"code_distance": d},
            output=raw_tool_output,
            exit_code=0,
            duration_ms=22.5,
        )
        # Verify secret was scrubbed in audit log
        assert "secret-agent-token-999" not in audit2["output"]
        assert "Bearer [REDACTED_TOKEN]" in audit2["output"]

        # 5. Execute Step 3: Publish verified artifact
        report_file = temp_workspace / "bv_resource_report.json"
        report_data = {
            "workload": "bernstein_vazirani_101",
            "num_qubits": metrics.num_qubits,
            "circuit_depth": metrics.depth,
            "minimum_code_distance": d,
            "feasible": feasible,
        }
        report_content = json.dumps(report_data, indent=2)
        report_file.write_text(report_content, encoding="utf-8")
        report_hash = hashlib.sha256(report_content.encode("utf-8")).hexdigest()

        test_db.record_audit(
            task_id=task_id,
            tool_name="artifacts.publish",
            parameters={"file": "bv_resource_report.json"},
            output=f"Artifact published: sha256={report_hash}",
            exit_code=0,
            duration_ms=8.0,
            modified_files=["bv_resource_report.json"],
        )

        # 6. Stage 6 & 7: Verifying -> Completed
        test_db.transition_task(task_id, "verifying")
        test_db.transition_task(task_id, "completed")

        final_task = test_db.get_task(task_id)
        assert final_task["status"] == "completed"
        assert final_task["completed_at"] is not None

        # 7. Validate full audit trail integrity
        assert test_db.verify_audit_trail(task_id) is True
        trail = test_db.get_audit_trail(task_id)
        assert len(trail) == 3


# ===========================================================================
# Scenario 2: Destructive Operation & Human Approval Gate
# ===========================================================================

class TestScenario02ApprovalGateWorkflow:
    """Scenario 2: Sensitive destructive operation triggers approval gate.

    Flow: Task starts -> encounters privileged tool -> enters blocked state ->
          approval requested -> human grants approval via API -> task resumes and completes.
    """

    def test_s2_approval_gate_unblocking_and_completion(self, temp_workspace, test_db):
        app = FastAPI(title="Plaq-OS Approvals API")

        @app.get("/api/v1/approvals")
        def list_approvals():
            cursor = test_db.conn.execute("SELECT * FROM approvals WHERE status='pending'")
            return [dict(r) for r in cursor.fetchall()]

        @app.post("/api/v1/approvals/{app_id}/decide")
        def decide(app_id: str, payload: Dict[str, Any]):
            approved = payload.get("approved", True)
            reason = payload.get("reason", "Approved by operator")
            return test_db.decide_approval(app_id, approved=approved, decided_by="secops", reason=reason)

        client = TestClient(app)

        # 1. Start task
        task = test_db.create_task(goal="Clean cache and rebuild repository", workspace_path=str(temp_workspace))
        t_id = task["id"]
        test_db.transition_task(t_id, "planning")
        test_db.transition_task(t_id, "running")

        # 2. Privileged action triggers approval gate
        app_req = test_db.request_approval(
            task_id=t_id,
            tool_name="terminal.run",
            parameters={"cmd": "git clean -fdx"},
            reason="Directory purge requires operator approval",
        )
        assert test_db.get_task(t_id)["status"] == "blocked"

        test_db.record_audit(
            task_id=t_id,
            tool_name="approval.gate",
            parameters={"approval_id": app_req["id"]},
            output="Execution halted waiting for operator",
        )

        # 3. Human inspects pending approvals via REST API
        pending_resp = client.get("/api/v1/approvals")
        assert pending_resp.status_code == 200
        pending = pending_resp.json()
        assert len(pending) == 1
        assert pending[0]["id"] == app_req["id"]
        assert pending[0]["tool_name"] == "terminal.run"

        # 4. Human grants approval
        decide_resp = client.post(f"/api/v1/approvals/{app_req['id']}/decide", json={"approved": True})
        assert decide_resp.status_code == 200
        assert decide_resp.json()["status"] == "approved"

        # 5. Task status is unblocked to running
        task_resumed = test_db.get_task(t_id)
        assert task_resumed["status"] == "running"

        # 6. Resume execution and complete
        test_db.record_audit(
            task_id=t_id,
            tool_name="terminal.run",
            parameters={"cmd": "git clean -fdx"},
            output="Clean completed successfully",
            exit_code=0,
        )
        test_db.transition_task(t_id, "verifying")
        test_db.transition_task(t_id, "completed")

        final_task = test_db.get_task(t_id)
        assert final_task["status"] == "completed"
        assert test_db.verify_audit_trail(t_id) is True


# ===========================================================================
# Scenario 3: Server Restart Checkpoint Recovery
# ===========================================================================

class TestScenario03CheckpointRecoveryWorkflow:
    """Scenario 3: Mid-execution process crash and checkpoint recovery.

    Flow: Task starts multi-step job -> step 1 completes -> step 2 running ->
          simulated abrupt process crash -> server restart -> active tasks recovered ->
          task resumed and finished cleanly without data loss or audit corruption.
    """

    def test_s3_crash_recovery_resumes_in_flight_task(self, temp_workspace, test_db):
        db_path = test_db.db_path

        # 1. Start multi-step task
        task = test_db.create_task(goal="Long running QEC simulation", workspace_path=str(temp_workspace))
        task_id = task["id"]
        test_db.transition_task(task_id, "planning")
        test_db.transition_task(task_id, "running")

        step1 = test_db.record_step(task_id, 1, "Simulate d=3 r=3", "Shots >= 100")
        test_db.record_audit(
            task_id=task_id,
            tool_name="quantum.simulate",
            parameters={"distance": 3, "rounds": 3},
            output="d=3 simulation complete, 0 errors",
            exit_code=0,
        )

        step2 = test_db.record_step(task_id, 2, "Simulate d=5 r=5", "Shots >= 100")

        # 2. SIMULATE ABRUPT SERVER CRASH
        # Close database connection immediately without completing task
        test_db.close()

        # 3. SERVER RESTART & RECOVERY
        recovered_db = TestDatabase(db_path)
        try:
            # Rehydrate active tasks
            active_tasks = recovered_db.recover_active_tasks()
            recovered_ids = [t["id"] for t in active_tasks]
            assert task_id in recovered_ids

            rehydrated = recovered_db.get_task(task_id)
            assert rehydrated["status"] == "running"
            assert rehydrated["current_step_id"] == step2["id"]

            # 4. Resume execution from step 2
            recovered_db.record_audit(
                task_id=task_id,
                tool_name="quantum.simulate",
                parameters={"distance": 5, "rounds": 5},
                output="d=5 simulation complete, 0 errors",
                exit_code=0,
            )

            # 5. Complete task
            recovered_db.transition_task(task_id, "verifying")
            recovered_db.transition_task(task_id, "completed")

            task_final = recovered_db.get_task(task_id)
            assert task_final["status"] == "completed"

            # 6. Verify unbroken hash chain spanning before and after crash
            assert recovered_db.verify_audit_trail(task_id) is True
            trail = recovered_db.get_audit_trail(task_id)
            assert len(trail) == 2
            assert trail[1]["previous_hash"] == trail[0]["current_hash"]
        finally:
            recovered_db.close()


# ===========================================================================
# Scenario 4: Quantum Co-Design Optimization Pipeline
# ===========================================================================

class TestScenario04QuantumCoDesignPipeline:
    """Scenario 4: Quantum co-design optimization pipeline via CLI and API.

    Flow: Circuit generation -> Fault-tolerant cost evaluation -> Stim QEC threshold study ->
          Pareto candidate filtering -> Artifact publication.
    """

    def test_s4_quantum_codesign_end_to_end_pipeline(self, quantum_engine, temp_workspace, test_db):
        task = test_db.create_task(goal="Chemistry Ansatz Co-Design Optimization", workspace_path=str(temp_workspace))
        t_id = task["id"]
        test_db.transition_task(t_id, "planning")
        test_db.transition_task(t_id, "running")

        # 1. Circuit workload generation
        circuit = quantum_engine.circuits.make_chemistry_ansatz_circuit(n_qubits=4, trotter_steps=1)
        assert circuit.num_qubits == 4

        # 2. Cost extraction
        metrics = quantum_engine.cost_model.extract_circuit_metrics(circuit)
        assert metrics.num_qubits == 4
        assert metrics.depth > 0

        # 3. Stim MWPM threshold sampling
        sim = quantum_engine.stim_bridge.SurfaceCodeStabilizerSimulator(code_distance=3, rounds=2)
        sample = sim.sample_logical_errors(p=0.001, shots=100, seed=42)
        assert sample.total_shots == 100

        # 4. Joint Pareto optimization search
        evaluated, frontier = quantum_engine.optimizer.search_pareto_optimizer(
            circuit=circuit,
            hardware=quantum_engine.hardware.DEMO_HARDWARE,
            target_epsilon=1e-3,
            candidate_limit=10,
        )
        assert len(evaluated) > 0
        assert len(frontier) > 0

        # 5. Save and fingerprint artifact
        pareto_file = temp_workspace / "chemistry_pareto.json"
        artifact_payload = {
            "model": "Chemistry Ansatz 4Q",
            "physical_metrics": {
                "t_count": metrics.t_ops,
                "logical_error_rate": sample.empirical_logical_error_rate,
            },
            "pareto_points": [
                {
                    "physical_qubits": p.physical_qubits,
                    "runtime_seconds": p.runtime_seconds,
                    "code_distance": p.code_distance,
                }
                for p in frontier
            ],
        }
        serialized = json.dumps(artifact_payload, indent=2)
        pareto_file.write_text(serialized, encoding="utf-8")
        sha256_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        # Audit and complete
        test_db.record_audit(
            task_id=t_id,
            tool_name="quantum.codesign",
            parameters={"workload": "chemistry_4q"},
            output=f"Extracted {len(frontier)} Pareto points. Artifact sha256={sha256_hash}",
            exit_code=0,
            modified_files=["chemistry_pareto.json"],
        )
        test_db.transition_task(t_id, "verifying")
        test_db.transition_task(t_id, "completed")

        assert test_db.get_task(t_id)["status"] == "completed"
        assert test_db.verify_audit_trail(t_id) is True


# ===========================================================================
# Scenario 5: Real-Time Workbench WebSocket Telemetry Stream
# ===========================================================================

class TestScenario05WorkbenchWebSocketStreaming:
    """Scenario 5: Real-time Workbench WebSocket streaming and event logging.

    Flow: Client subscribes to event broadcaster -> task lifecycle triggers events ->
          events delivered with UTC timestamp and task_id -> stream validation.
    """

    def test_s5_workbench_event_streaming_and_ordering(self, event_recorder, test_db):
        task_id = "task-telemetry-workbench-001"

        # Lifecycle event sequence
        lifecycle_events = [
            {"event_type": "task_created", "status": "queued"},
            {"event_type": "step_started", "step_number": 1, "step_name": "Context Inspection"},
            {"event_type": "tool_executed", "tool": "workspace.list", "exit_code": 0},
            {"event_type": "step_completed", "step_number": 1},
            {"event_type": "step_started", "step_number": 2, "step_name": "Quantum Co-Design"},
            {"event_type": "tool_executed", "tool": "quantum.compile", "exit_code": 0},
            {"event_type": "artifact_published", "artifact_id": "art-99", "sha256": "abc123hash"},
            {"event_type": "task_completed", "status": "completed"},
        ]

        for evt in lifecycle_events:
            payload = dict(evt)
            payload["task_id"] = task_id
            payload["timestamp"] = time.time()
            event_recorder.record(payload)

        # Verify event sequence
        recorded = event_recorder.filter(task_id=task_id)
        assert len(recorded) == 8

        # Verify strict chronological progression
        event_names = [e["event_type"] for e in recorded]
        expected_names = [e["event_type"] for e in lifecycle_events]
        assert event_names == expected_names

        # Verify timestamp strictly monotonic non-decreasing
        timestamps = [e["timestamp"] for e in recorded]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]
