"""Unit tests for plaq_agent_runtime package (ToolRegistry, 12 tools, ApprovalManager, AgentRuntime)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import pytest

from plaq_contracts.common import utc_now_iso
from plaq_contracts.event import EventType, PlatformEvent
from plaq_contracts.step import StepStatus
from plaq_contracts.task import TaskStatus
from plaq_contracts.tool import (
    DEFAULT_TOOL_TIERS,
    PermissionTier,
    ToolDefinition,
    ToolRequest,
    ToolResult,
)
from plaq_control_plane import (
    ControlPlaneDatabase,
    ControlPlaneRepository,
    DatabaseEngine,
)
from plaq_sandbox.guard import PathGuard, PathTraversalError
from plaq_model_gateway import DeterministicPlanner, ModelGateway
from plaq_agent_runtime import (
    AgentRuntime,
    ApprovalManager,
    TaskResult,
    ToolContext,
    ToolRegistry,
    create_default_tool_registry,
)


@pytest.fixture
def test_repo():
    """In-memory ControlPlaneRepository."""
    engine = DatabaseEngine(":memory:")
    repo = ControlPlaneRepository(engine)
    yield repo
    engine.close()


@pytest.fixture
def temp_workspace():
    """Temporary workspace with initialized git repository."""
    with tempfile.TemporaryDirectory(prefix="plaq_runtime_ws_") as tmp:
        ws = Path(tmp).resolve()
        (ws / "src").mkdir()
        (ws / "README.md").write_text("# Plaq Test\n", encoding="utf-8")
        subprocess.run(["git", "init", str(ws)], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.email", "test@plaq.ai"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(ws), "config", "user.name", "Tester"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(ws), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(ws), "commit", "-m", "Initial commit"], capture_output=True, check=True)
        yield ws


class TestToolRegistryAndTiers:
    """Verifies ToolRegistry tier mapping, authorization, validation, and secret scrubbing."""

    def test_default_registry_all_12_tools_registered(self):
        registry = create_default_tool_registry()
        tier_map = registry.get_tier_map()
        assert len(tier_map) == 12

        assert tier_map["workspace.list"] == "read_only"
        assert tier_map["workspace.read"] == "read_only"
        assert tier_map["workspace.write"] == "workspace_write"
        assert tier_map["workspace.patch"] == "workspace_write"
        assert tier_map["git.diff"] == "git_isolated"
        assert tier_map["git.branch"] == "git_isolated"
        assert tier_map["terminal.run"] == "process_sandbox"
        assert tier_map["tests.run"] == "process_sandbox"
        assert tier_map["quantum.compile"] == "quantum_engine"
        assert tier_map["quantum.estimate"] == "quantum_engine"
        assert tier_map["quantum.simulate"] == "quantum_engine"
        assert tier_map["artifacts.publish"] == "privileged"

    def test_tier_enforcement_denies_unauthorized_tier(self, temp_workspace, test_repo):
        registry = create_default_tool_registry()
        task = test_repo.create_task("Test Tier Enforcement", workspace_path=str(temp_workspace))

        # Context allows only READ_ONLY
        ctx = ToolContext(
            workspace_path=temp_workspace,
            task_id=task["id"],
            control_plane=test_repo,
            allowed_tiers={PermissionTier.READ_ONLY},
        )

        # Calling workspace.write (WORKSPACE_WRITE) should be denied
        req = ToolRequest(
            tool_name="workspace.write",
            parameters={"path": "forbidden.txt", "content": "secret"},
            task_id=task["id"],
        )
        res = registry.execute(req, ctx)
        assert res.success is False
        assert "Permission denied" in res.error
        assert res.exit_code == 1

    def test_parameter_validation_failure(self, temp_workspace, test_repo):
        registry = create_default_tool_registry()
        task = test_repo.create_task("Test Validation", workspace_path=str(temp_workspace))
        ctx = ToolContext(workspace_path=temp_workspace, task_id=task["id"], control_plane=test_repo)

        # workspace.list with invalid parameter type
        req = ToolRequest(
            tool_name="workspace.list",
            parameters={"max_depth": "invalid_not_an_int"},
            task_id=task["id"],
        )
        res = registry.execute(req, ctx)
        assert res.success is False
        assert "Parameter validation failed" in res.error

    def test_secret_scrubbing_in_audit_logging(self, temp_workspace, test_repo):
        registry = create_default_tool_registry()
        task = test_repo.create_task("Secret Scrubbing Task", workspace_path=str(temp_workspace))
        ctx = ToolContext(workspace_path=temp_workspace, task_id=task["id"], control_plane=test_repo)

        # Run command with sensitive token in output and param
        req = ToolRequest(
            tool_name="terminal.run",
            parameters={
                "cmd": [sys.executable, "-c", "print('Bearer secret-token-xyz-987')"],
                "api_key": "top-secret-password-123",
            },
            task_id=task["id"],
        )
        res = registry.execute(req, ctx)
        assert res.success is True

        # Inspect audit trail in control plane
        audits = test_repo.get_audit_trail(task["id"])
        assert len(audits) >= 1
        last_audit = audits[-1]
        params_str = last_audit["parameters"]
        output_str = last_audit["output"]

        # Secrets must be redacted
        assert "top-secret-password-123" not in params_str
        assert "[REDACTED]" in params_str
        assert "secret-token-xyz-987" not in output_str
        assert "[REDACTED_TOKEN]" in output_str


class TestBuiltinToolsExecution:
    """Verifies execution of all 12 tools through ToolRegistry."""

    def test_workspace_tools_lifecycle(self, temp_workspace, test_repo):
        registry = create_default_tool_registry()
        task = test_repo.create_task("Workspace Tools Test", workspace_path=str(temp_workspace))
        ctx = ToolContext(workspace_path=temp_workspace, task_id=task["id"], control_plane=test_repo)

        # 1. workspace.write
        w_req = ToolRequest(
            tool_name="workspace.write",
            parameters={"path": "notes.txt", "content": "Hello Plaq-OS!"},
            task_id=task["id"],
        )
        w_res = registry.execute(w_req, ctx)
        assert w_res.success is True
        assert "sha256=" in w_res.output
        assert "notes.txt" in w_res.modified_files

        # 2. workspace.read
        r_req = ToolRequest(
            tool_name="workspace.read",
            parameters={"path": "notes.txt"},
            task_id=task["id"],
        )
        r_res = registry.execute(r_req, ctx)
        assert r_res.success is True
        assert r_res.output == "Hello Plaq-OS!"

        # 3. workspace.patch
        p_req = ToolRequest(
            tool_name="workspace.patch",
            parameters={"path": "notes.txt", "target": "Plaq-OS", "replacement": "Quantum Computing"},
            task_id=task["id"],
        )
        p_res = registry.execute(p_req, ctx)
        assert p_res.success is True
        assert (temp_workspace / "notes.txt").read_text() == "Hello Quantum Computing!"

        # 4. workspace.list
        l_req = ToolRequest(
            tool_name="workspace.list",
            parameters={"path": "."},
            task_id=task["id"],
        )
        l_res = registry.execute(l_req, ctx)
        assert l_res.success is True
        entries = json.loads(l_res.output)
        names = [e["name"] for e in entries]
        assert "notes.txt" in names

    def test_git_tools_execution(self, temp_workspace, test_repo):
        registry = create_default_tool_registry()
        task = test_repo.create_task("Git Tools Test", workspace_path=str(temp_workspace))
        ctx = ToolContext(workspace_path=temp_workspace, task_id=task["id"], control_plane=test_repo)

        # git.branch list
        b_req = ToolRequest(tool_name="git.branch", parameters={"action": "list"}, task_id=task["id"])
        b_res = registry.execute(b_req, ctx)
        assert b_res.success is True

        # git.diff
        (temp_workspace / "README.md").write_text("# Plaq Modified\n", encoding="utf-8")
        d_req = ToolRequest(tool_name="git.diff", parameters={}, task_id=task["id"])
        d_res = registry.execute(d_req, ctx)
        assert d_res.success is True
        assert "Plaq Modified" in d_res.output

    def test_terminal_and_tests_tools(self, temp_workspace, test_repo):
        registry = create_default_tool_registry()
        task = test_repo.create_task("Terminal Tools Test", workspace_path=str(temp_workspace))
        ctx = ToolContext(workspace_path=temp_workspace, task_id=task["id"], control_plane=test_repo)

        # terminal.run
        t_req = ToolRequest(
            tool_name="terminal.run",
            parameters={"cmd": [sys.executable, "-c", "print('terminal_ok')"]},
            task_id=task["id"],
        )
        t_res = registry.execute(t_req, ctx)
        assert t_res.success is True
        assert "terminal_ok" in t_res.output

        # tests.run
        ts_req = ToolRequest(
            tool_name="tests.run",
            parameters={"args": ["--version"]},
            task_id=task["id"],
        )
        ts_res = registry.execute(ts_req, ctx)
        assert ts_res.exit_code == 0

    def test_quantum_tools_execution(self, temp_workspace, test_repo):
        registry = create_default_tool_registry()
        task = test_repo.create_task("Quantum Tools Test", workspace_path=str(temp_workspace))
        ctx = ToolContext(workspace_path=temp_workspace, task_id=task["id"], control_plane=test_repo)

        # 1. quantum.compile
        c_req = ToolRequest(
            tool_name="quantum.compile",
            parameters={"workload": "bv", "bitstring": "101"},
            task_id=task["id"],
        )
        c_res = registry.execute(c_req, ctx)
        assert c_res.success is True
        c_data = json.loads(c_res.output)
        assert c_data["num_qubits"] == 4

        # 2. quantum.estimate
        e_req = ToolRequest(
            tool_name="quantum.estimate",
            parameters={"hardware_profile": "superconducting_heron", "code_distance": 3},
            task_id=task["id"],
        )
        e_res = registry.execute(e_req, ctx)
        assert e_res.success is True
        e_data = json.loads(e_res.output)
        assert e_data["code_distance"] == 3

        # 3. quantum.simulate
        s_req = ToolRequest(
            tool_name="quantum.simulate",
            parameters={"code_distance": 3, "shots": 100},
            task_id=task["id"],
        )
        s_res = registry.execute(s_req, ctx)
        assert s_res.success is True
        s_data = json.loads(s_res.output)
        assert s_data["code_distance"] == 3
        assert s_data["total_shots"] == 100

        # Reject invalid even distance
        s_bad = ToolRequest(
            tool_name="quantum.simulate",
            parameters={"code_distance": 4, "shots": 10},
            task_id=task["id"],
        )
        s_bad_res = registry.execute(s_bad, ctx)
        assert s_bad_res.success is False
        assert s_bad_res.exit_code == 1

    def test_artifacts_publish_tool(self, temp_workspace, test_repo):
        registry = create_default_tool_registry()
        task = test_repo.create_task("Artifact Tool Test", workspace_path=str(temp_workspace))
        ctx = ToolContext(workspace_path=temp_workspace, task_id=task["id"], control_plane=test_repo)

        # Create report in workspace
        report_file = temp_workspace / "quantum_report.json"
        report_file.write_text(json.dumps({"experiment": "BV-101", "t_count": 0}), encoding="utf-8")

        a_req = ToolRequest(
            tool_name="artifacts.publish",
            parameters={"file": "quantum_report.json", "artifact_type": "report"},
            task_id=task["id"],
        )
        a_res = registry.execute(a_req, ctx)
        assert a_res.success is True
        assert "Artifact published" in a_res.output
        assert "sha256=" in a_res.output


class TestApprovalManager:
    """Verifies approval gate detection, blocking task state, and decision handling."""

    def test_safe_action_does_not_require_approval(self, test_repo):
        mgr = ApprovalManager(repository=test_repo)
        req, _ = mgr.is_approval_required("workspace.read", {"path": "README.md"})
        assert req is False

    def test_destructive_command_requires_approval(self, test_repo):
        mgr = ApprovalManager(repository=test_repo)
        req, reason = mgr.is_approval_required("terminal.run", {"cmd": "rm -rf build/"})
        assert req is True
        assert "deletion" in reason.lower()

        req_clean, reason_clean = mgr.is_approval_required("terminal.run", {"cmd": "git clean -fdx"})
        assert req_clean is True

        req_drop, reason_drop = mgr.is_approval_required("terminal.run", {"cmd": "dropdb test_db"})
        assert req_drop is True

    def test_protected_file_mutation_requires_approval(self, test_repo):
        mgr = ApprovalManager(repository=test_repo)
        req, reason = mgr.is_approval_required("workspace.patch", {"file": "critical.py"})
        assert req is True
        assert "protected file" in reason.lower()

        req_env, reason_env = mgr.is_approval_required("workspace.write", {"path": ".env"})
        assert req_env is True

    def test_approval_lifecycle_blocking_and_granting(self, test_repo):
        mgr = ApprovalManager(repository=test_repo)
        task = test_repo.create_task("Approval Lifecycle Test")
        test_repo.transition_task(task["id"], "planning")
        test_repo.transition_task(task["id"], "running")

        # Request approval
        app = mgr.request_approval(
            task_id=task["id"],
            tool_name="terminal.run",
            parameters={"cmd": "git clean -fdx"},
            reason="Purge working directory",
        )
        assert app["status"] == "pending"

        # Task must now be blocked
        assert test_repo.get_task(task["id"])["status"] == "blocked"

        # List pending
        pending = mgr.list_pending_approvals(task["id"])
        assert len(pending) == 1
        assert pending[0]["id"] == app["id"]

        # Decide: Approved
        mgr.decide_approval(app["id"], approved=True, decided_by="admin")

        # Task transitions back to running
        assert test_repo.get_task(task["id"])["status"] == "running"

    def test_approval_lifecycle_denial_fails_task(self, test_repo):
        mgr = ApprovalManager(repository=test_repo)
        task = test_repo.create_task("Approval Denial Test")
        test_repo.transition_task(task["id"], "planning")
        test_repo.transition_task(task["id"], "running")

        app = mgr.request_approval(
            task_id=task["id"],
            tool_name="terminal.run",
            parameters={"cmd": "dropdb"},
            reason="Database deletion",
        )
        mgr.decide_approval(app["id"], approved=False, reason="Destructive operations forbidden")

        # Task transitions to failed
        task_record = test_repo.get_task(task["id"])
        assert task_record["status"] == "failed"
        assert "Destructive operations forbidden" in task_record["error"]


class TestAgentExecutionLoop:
    """Verifies full 7-stage deterministic execution, cancellation, and recovery."""

    def test_e2e_quantum_task_execution(self, temp_workspace, test_repo):
        events_captured = []
        runtime = AgentRuntime(
            repository=test_repo,
            event_broadcaster=lambda ev: events_captured.append(ev),
        )

        task = test_repo.create_task(
            goal="Synthesize Bernstein-Vazirani 101 circuit and evaluate resources",
            workspace_path=str(temp_workspace),
        )

        res = runtime.execute_task(task["id"])
        assert res.status == "completed"
        assert res.summary is not None
        assert "Delivery Summary" in res.summary

        # Verify task final status in DB
        db_task = test_repo.get_task(task["id"])
        assert db_task["status"] == "completed"
        assert db_task["completed_at"] is not None

        # Verify steps were executed and completed
        steps = test_repo.list_steps(task["id"])
        assert len(steps) == 3
        for s in steps:
            assert s["status"] == "completed"

        # Verify platform events emitted chronologically
        event_types = [e.event_type for e in events_captured]
        assert EventType.TASK_CREATED in event_types
        assert EventType.TASK_TRANSITIONED in event_types
        assert EventType.STEP_STARTED in event_types
        assert EventType.TOOL_COMPLETED in event_types
        assert EventType.STEP_COMPLETED in event_types
        assert EventType.TASK_COMPLETED in event_types

    def test_task_cancellation(self, temp_workspace, test_repo):
        events = []
        runtime = AgentRuntime(
            repository=test_repo,
            event_broadcaster=lambda ev: events.append(ev),
        )

        task = test_repo.create_task("Task To Cancel", workspace_path=str(temp_workspace))
        cancelled = runtime.cancel_task(task["id"])
        assert cancelled is True

        assert test_repo.get_task(task["id"])["status"] == "cancelled"
        assert any(e.event_type == EventType.TASK_CANCELLED for e in events)

        # Cancelling already terminal task returns False
        assert runtime.cancel_task(task["id"]) is False

    def test_approval_gate_suspends_loop_and_resumption_completes(self, temp_workspace, test_repo):
        runtime = AgentRuntime(
            repository=test_repo,
        )

        task = test_repo.create_task(
            goal="Clean cache and workspace purge",
            workspace_path=str(temp_workspace),
        )

        # Step 1 is "terminal.run" with "git clean -fdx", which triggers approval gate
        res = runtime.execute_task(task["id"])
        assert res.status == "blocked"
        assert test_repo.get_task(task["id"])["status"] == "blocked"

        # Check pending approval
        pending = runtime.approval_manager.list_pending_approvals(task["id"])
        assert len(pending) == 1
        app_id = pending[0]["id"]

        # Operator approves
        runtime.approval_manager.decide_approval(app_id, approved=True, decided_by="lead_dev")

        # Resume execution
        resume_res = runtime.resume_task(task["id"])
        assert resume_res.status == "completed"
        assert test_repo.get_task(task["id"])["status"] == "completed"
