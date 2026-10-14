"""Prototype validation script for Milestone M2 Pydantic v2 Schemas and PlaqClient."""

from datetime import datetime, timezone
import json
import uuid
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================================
# Common
# ============================================================================

def generate_id(prefix: Optional[str] = None) -> str:
    raw = str(uuid.uuid4())
    return f"{prefix}_{raw}" if prefix else raw


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class PlaqBaseModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )


T = TypeVar("T")


class PaginationParams(PlaqBaseModel):
    page: int = Field(default=1, ge=1, description="Page number, 1-indexed")
    page_size: int = Field(default=50, ge=1, le=1000, description="Items per page")


class PaginatedResponse(PlaqBaseModel, Generic[T]):
    items: List[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    has_more: bool


class SuccessResponse(PlaqBaseModel):
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(PlaqBaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


# ============================================================================
# Task
# ============================================================================

class TaskStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskCreate(PlaqBaseModel):
    goal: str = Field(..., min_length=1, description="Task goal or objective")
    workspace_path: Optional[str] = Field(default="", description="Path to target workspace")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom parameters")
    project_id: Optional[str] = None
    user_id: Optional[str] = None


class TaskUpdate(PlaqBaseModel):
    status: Optional[TaskStatus] = None
    current_step_id: Optional[str] = None
    error: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class Task(PlaqBaseModel):
    id: str = Field(default_factory=generate_id)
    goal: str = Field(..., min_length=1)
    workspace_path: str = Field(default="")
    status: TaskStatus = Field(default=TaskStatus.QUEUED)
    current_step_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("parameters", mode="before")
    @classmethod
    def parse_parameters_json(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v or {}


# ============================================================================
# Step
# ============================================================================

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(PlaqBaseModel):
    id: str = Field(default_factory=generate_id)
    task_id: str
    step_number: int = Field(..., ge=1)
    step_name: str = Field(..., min_length=1)
    criteria: str = Field(default="", description="Verifiable completion criteria")
    status: StepStatus = Field(default=StepStatus.PENDING)
    tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result_summary: Optional[str] = None

    @field_validator("tool_parameters", mode="before")
    @classmethod
    def parse_tool_params_json(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else None
            except Exception:
                return None
        return v


class PlanDefinition(PlaqBaseModel):
    task_id: str
    goal: str
    steps: List[PlanStep] = Field(default_factory=list)
    estimated_duration_sec: Optional[float] = None
    created_at: datetime = Field(default_factory=utc_now)


# ============================================================================
# Tool
# ============================================================================

class PermissionTier(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    GIT_ISOLATED = "git_isolated"
    PROCESS_SANDBOX = "process_sandbox"
    QUANTUM_ENGINE = "quantum_engine"
    PRIVILEGED = "privileged"


DEFAULT_TOOL_TIERS: Dict[str, PermissionTier] = {
    "workspace.list": PermissionTier.READ_ONLY,
    "workspace.read": PermissionTier.READ_ONLY,
    "workspace.patch": PermissionTier.WORKSPACE_WRITE,
    "workspace.write": PermissionTier.WORKSPACE_WRITE,
    "git.diff": PermissionTier.GIT_ISOLATED,
    "git.branch": PermissionTier.GIT_ISOLATED,
    "terminal.run": PermissionTier.PROCESS_SANDBOX,
    "tests.run": PermissionTier.PROCESS_SANDBOX,
    "quantum.compile": PermissionTier.QUANTUM_ENGINE,
    "quantum.estimate": PermissionTier.QUANTUM_ENGINE,
    "quantum.simulate": PermissionTier.QUANTUM_ENGINE,
    "artifacts.publish": PermissionTier.PRIVILEGED,
}


class ToolDefinition(PlaqBaseModel):
    name: str = Field(..., min_length=1)
    description: str
    tier: PermissionTier
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    timeout_sec: float = Field(default=30.0, gt=0)


class ToolRequest(PlaqBaseModel):
    tool_name: str = Field(..., min_length=1)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    task_id: str
    step_id: Optional[str] = None
    request_id: str = Field(default_factory=generate_id)


class ToolResult(PlaqBaseModel):
    success: bool
    output: str = Field(default="")
    error: Optional[str] = None
    duration_ms: float = Field(default=0.0, ge=0)
    exit_code: Optional[int] = 0
    modified_files: List[str] = Field(default_factory=list)

    @field_validator("modified_files", mode="before")
    @classmethod
    def parse_files_json(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else []
            except Exception:
                return []
        return v or []


# ============================================================================
# Approval
# ============================================================================

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(PlaqBaseModel):
    id: str = Field(default_factory=generate_id)
    task_id: str
    step_id: Optional[str] = None
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    reason: str
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None

    @field_validator("parameters", mode="before")
    @classmethod
    def parse_params_json(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v or {}


class ApprovalDecision(PlaqBaseModel):
    approval_id: str
    approved: bool
    reason: Optional[str] = None
    decided_by: str = "human"
    decided_at: datetime = Field(default_factory=utc_now)


# ============================================================================
# Artifact
# ============================================================================

class ArtifactType(str, Enum):
    REPORT = "report"
    DIFF = "diff"
    CIRCUIT = "circuit"
    BENCHMARK = "benchmark"
    MANIFEST = "manifest"
    LOG = "log"
    PARETO_FRONTIER = "pareto_frontier"
    OTHER = "other"


class ArtifactRecord(PlaqBaseModel):
    id: str = Field(default_factory=generate_id)
    task_id: str
    artifact_type: ArtifactType = Field(default=ArtifactType.REPORT)
    name: str = Field(..., min_length=1)
    file_path: str
    sha256_hash: str = Field(..., min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def parse_metadata_json(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v or {}


class ArtifactPublishRequest(PlaqBaseModel):
    task_id: str
    name: str = Field(..., min_length=1)
    content: Optional[str] = None
    file_path: Optional[str] = None
    artifact_type: ArtifactType = Field(default=ArtifactType.REPORT)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Event
# ============================================================================

class EventType(str, Enum):
    TASK_CREATED = "task_created"
    TASK_TRANSITIONED = "task_transitioned"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    TOOL_INVOKED = "tool_invoked"
    TOOL_COMPLETED = "tool_completed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    ARTIFACT_PUBLISHED = "artifact_published"
    QUANTUM_OPT_STARTED = "quantum_opt_started"
    QUANTUM_OPT_PROGRESS = "quantum_opt_progress"
    QUANTUM_OPT_COMPLETED = "quantum_opt_completed"
    AUDIT_RECORDED = "audit_recorded"
    ERROR = "error"


class PlatformEvent(PlaqBaseModel):
    event_id: str = Field(default_factory=generate_id)
    event_type: EventType
    task_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)
    payload: Dict[str, Any] = Field(default_factory=dict)
    source: str = "plaq-os"

    @field_validator("payload", mode="before")
    @classmethod
    def parse_payload_json(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v or {}


# ============================================================================
# Quantum
# ============================================================================

class QuantumCompileRequest(PlaqBaseModel):
    workload: Optional[str] = Field(default="test_circuit", description="Name of quantum benchmark or workload")
    qubits: int = Field(default=4, ge=1, le=1000)
    bitstring: Optional[str] = None
    depth: Optional[int] = None
    qasm: Optional[str] = None
    target_hardware: Optional[str] = "superconducting_heron"
    optimization_level: int = Field(default=1, ge=0, le=3)


class QuantumEstimateRequest(PlaqBaseModel):
    qubits: int = Field(default=4, ge=1, le=1000)
    physical_error_rate: float = Field(default=0.001, gt=0.0, lt=1.0)
    error_budget: float = Field(default=1e-3, gt=0.0, lt=1.0)
    threshold: float = Field(default=0.01, gt=0.0, lt=1.0)
    spacetime_volume: Optional[float] = None
    hardware_profile: Optional[str] = "superconducting_heron"
    circuit_name: Optional[str] = None


class QuantumBenchmarkRequest(PlaqBaseModel):
    workloads: List[str] = Field(default_factory=lambda: ["qaoa", "qft", "bv"])
    hardware_profiles: List[str] = Field(default_factory=lambda: ["superconducting_heron", "trapped_ion_quantinuum"])
    search_methods: List[str] = Field(default_factory=lambda: ["greedy", "simulated_annealing", "pareto"])
    budget_evaluations: int = Field(default=50, ge=1)


class QuantumResult(PlaqBaseModel):
    request_id: str = Field(default_factory=generate_id)
    num_qubits: int
    code_distance: int
    physical_qubits: Optional[int] = None
    t_count: int = 0
    circuit_depth: int = 0
    estimated_runtime_sec: float = 0.0
    feasible: bool = True
    pareto_points: Optional[List[Dict[str, Any]]] = None
    metrics: Optional[Dict[str, Any]] = None
    manifest: Optional[Dict[str, Any]] = None


# ============================================================================
# Test Runner
# ============================================================================

def run_tests():
    print("Testing Task models...")
    tc = TaskCreate(goal="Test Task", workspace_path="/tmp/ws", parameters={"foo": "bar"})
    assert tc.goal == "Test Task"
    
    t = Task(
        goal=tc.goal,
        workspace_path=tc.workspace_path,
        parameters=tc.parameters,
    )
    assert t.status == TaskStatus.QUEUED
    assert t.status == "queued"
    
    # Test JSON string parsing from SQLite
    t_from_sqlite = Task(
        id="test-id-1",
        goal="SQLite Loaded",
        parameters='{"from_db": true}',
    )
    assert t_from_sqlite.parameters["from_db"] is True

    print("Testing Step models...")
    step = PlanStep(
        task_id=t.id,
        step_number=1,
        step_name="Step 1",
        criteria="criteria 1",
    )
    assert step.status == StepStatus.PENDING
    plan = PlanDefinition(task_id=t.id, goal=t.goal, steps=[step])
    assert len(plan.steps) == 1

    print("Testing Tool models...")
    assert DEFAULT_TOOL_TIERS["workspace.list"] == PermissionTier.READ_ONLY
    assert DEFAULT_TOOL_TIERS["artifacts.publish"] == PermissionTier.PRIVILEGED
    tool_req = ToolRequest(tool_name="workspace.list", parameters={"path": "."}, task_id=t.id)
    tool_res = ToolResult(success=True, output="files: [README.md]", duration_ms=12.4, modified_files=["README.md"])
    assert tool_res.modified_files == ["README.md"]

    print("Testing Approval models...")
    app = ApprovalRequest(
        task_id=t.id,
        tool_name="terminal.run",
        parameters='{"cmd": "rm -rf"}',
        reason="Danger",
    )
    assert app.parameters["cmd"] == "rm -rf"
    assert app.status == ApprovalStatus.PENDING

    print("Testing Artifact models...")
    art = ArtifactRecord(
        task_id=t.id,
        name="report.json",
        file_path="/tmp/report.json",
        sha256_hash="a" * 64,
        size_bytes=1024,
    )
    assert art.artifact_type == ArtifactType.REPORT

    print("Testing Event models...")
    ev = PlatformEvent(
        event_type=EventType.TASK_CREATED,
        task_id=t.id,
        payload={"task_id": t.id},
    )
    assert ev.event_type == "task_created"

    print("Testing Quantum models...")
    qest = QuantumEstimateRequest(qubits=8, physical_error_rate=0.001)
    qres = QuantumResult(
        num_qubits=qest.qubits,
        code_distance=3,
        t_count=80,
        estimated_runtime_sec=1.25,
    )
    assert qres.num_qubits == 8
    assert qres.code_distance == 3

    print("ALL PROTOTYPE MODEL TESTS PASSED CLEANLY!")


if __name__ == "__main__":
    run_tests()
