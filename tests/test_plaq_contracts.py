"""Comprehensive unit tests for plaq_contracts package."""

import json
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from plaq_contracts import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ArtifactPublishRequest,
    ArtifactRecord,
    ArtifactType,
    AuditRecord,
    DEFAULT_TOOL_TIERS,
    ErrorResponse,
    EventType,
    PaginatedResponse,
    PaginationParams,
    PermissionTier,
    PlanDefinition,
    PlanStep,
    PlatformEvent,
    QuantumBenchmarkRequest,
    QuantumCompileRequest,
    QuantumEstimateRequest,
    QuantumResult,
    StepStatus,
    SuccessResponse,
    Task,
    TaskCreate,
    TaskStatus,
    TaskUpdate,
    generate_id,
    utc_now,
    utc_now_iso,
)


class TestCommonContracts:
    def test_id_generation(self):
        raw_id = generate_id()
        assert len(raw_id) >= 32
        prefixed = generate_id("task")
        assert prefixed.startswith("task_")

    def test_utc_now_format(self):
        now = utc_now()
        assert now.tzinfo is not None
        iso_str = utc_now_iso()
        assert isinstance(iso_str, str)
        assert "T" in iso_str

    def test_pagination_and_responses(self):
        params = PaginationParams(page=2, page_size=25)
        assert params.page == 2
        assert params.page_size == 25

        resp = PaginatedResponse(
            items=["item1", "item2"],
            total=50,
            page=1,
            page_size=2,
            total_pages=25,
            has_more=True,
        )
        assert len(resp.items) == 2
        assert resp.has_more is True

        succ = SuccessResponse(data={"key": "val"})
        assert succ.success is True
        assert succ.data["key"] == "val"

        err = ErrorResponse(error="NotFoundError", detail="Missing item", code="E404")
        assert err.error == "NotFoundError"
        assert err.code == "E404"


class TestTaskContracts:
    def test_task_create_and_validation(self):
        tc = TaskCreate(goal="Test goal", parameters='{"param1": "val1"}')
        assert tc.goal == "Test goal"
        assert tc.parameters == {"param1": "val1"}

        with pytest.raises(ValidationError):
            TaskCreate(goal="")

    def test_task_row_hydration(self):
        task = Task(
            goal="Hydration test",
            status="running",
            parameters='{"d": 3, "shots": 1000}',
        )
        assert task.status == TaskStatus.RUNNING
        assert task.parameters["d"] == 3
        assert task.parameters["shots"] == 1000


class TestStepAndToolContracts:
    def test_step_contract(self):
        step = PlanStep(
            task_id="t1",
            step_number=1,
            step_name="Step 1",
            criteria="Pass tests",
            tool_parameters='{"arg": 42}',
        )
        assert step.step_number == 1
        assert step.tool_parameters == {"arg": 42}
        assert step.status == StepStatus.PENDING

    def test_tool_definitions_and_tiers(self):
        assert DEFAULT_TOOL_TIERS["workspace.read"] == PermissionTier.READ_ONLY
        assert DEFAULT_TOOL_TIERS["terminal.run"] == PermissionTier.PROCESS_SANDBOX
        assert DEFAULT_TOOL_TIERS["quantum.compile"] == PermissionTier.QUANTUM_ENGINE

        rec = AuditRecord(
            task_id="t-1",
            sequence_number=1,
            tool_name="workspace.list",
            parameters='{"dir": "/tmp"}',
            output="ok",
            previous_hash="0" * 64,
            current_hash="a" * 64,
            modified_files='["a.txt", "b.txt"]',
        )
        assert rec.parameters == {"dir": "/tmp"}
        assert rec.modified_files == ["a.txt", "b.txt"]


class TestApprovalAndArtifactContracts:
    def test_approval_contracts(self):
        req = ApprovalRequest(
            task_id="t-1",
            tool_name="terminal.run",
            parameters='{"cmd": "rm -rf"}',
            reason="Dangerous",
        )
        assert req.status == ApprovalStatus.PENDING
        assert req.parameters == {"cmd": "rm -rf"}

        dec = ApprovalDecision(
            approval_id=req.id,
            approved=True,
            reason="Authorized",
        )
        assert dec.approved is True

    def test_artifact_contracts(self):
        art = ArtifactRecord(
            task_id="t-1",
            name="pareto.json",
            file_path="/data/pareto.json",
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            size_bytes=1024,
            metadata='{"points": 5}',
        )
        assert art.artifact_type == ArtifactType.REPORT
        assert art.metadata == {"points": 5}


class TestQuantumContracts:
    def test_quantum_contracts(self):
        req = QuantumEstimateRequest(qubits=8, physical_error_rate=0.002)
        assert req.qubits == 8
        assert req.physical_error_rate == 0.002

        res = QuantumResult(
            num_qubits=8,
            code_distance=5,
            t_count=80,
            circuit_depth=120,
            estimated_runtime_sec=0.45,
            feasible=True,
        )
        assert res.num_qubits == 8
        assert res.code_distance == 5
        assert res.feasible is True
