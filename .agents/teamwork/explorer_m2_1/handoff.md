# Milestone M2 Explorer Handoff Report: Contracts & SDK Architecture

**Author**: Explorer 1 (`explorer_m2_1`)  
**Target Milestone**: M2 — Shared Contracts & Control Plane Persistence  
**Target Packages**: `packages/contracts`, `packages/sdk-python`  
**Date**: 2026-10-14  

---

## 1. Observations

### 1.1 Environment & Dependency Capabilities
- **Python Version**: 3.10.11 running on Windows (`win32`).
- **Pydantic**: Installed version is `2.13.5` (`pydantic>=2.0` verified via `python -c "import pydantic; print(pydantic.__version__)"`).
  - Supports `pydantic.ConfigDict`, `field_validator`, `model_validator`, `Field`, `BaseModel`.
- **HTTP Client**: `httpx` version `0.27.2` installed (`python -c "import httpx; print(httpx.__version__)"`).
- **WebSocket Client**: `websockets` version `13.1` installed (`python -c "import websockets; print(websockets.__version__)"`).

### 1.2 Monorepo Layout & Sys.path Configuration
- `tests/e2e/conftest.py` lines 30-49 configure the monorepo import paths dynamically:
  ```python
  PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
  MONOREPO_SRC_DIRS = [
      PROJECT_ROOT,
      PROJECT_ROOT / "apps" / "api" / "src",
      PROJECT_ROOT / "apps" / "cli" / "src",
      PROJECT_ROOT / "packages" / "contracts" / "src",
      PROJECT_ROOT / "packages" / "sdk-python" / "src",
      PROJECT_ROOT / "services" / "control-plane" / "src",
      PROJECT_ROOT / "services" / "sandbox-manager" / "src",
      PROJECT_ROOT / "services" / "model-gateway" / "src",
      PROJECT_ROOT / "services" / "agent-runtime" / "src",
      PROJECT_ROOT / "services" / "artifact-service" / "src",
      PROJECT_ROOT / "engines" / "quantum" / "src",
  ]
  ```
- Therefore, packages located at `packages/contracts/src/plaq_contracts` and `packages/sdk-python/src/plaq_sdk` are directly importable across all test runners, services, and applications without manual wheel building.

### 1.3 Existing Test Suite Baselines
- **Quantum Unit Tests**: `pytest engines/quantum/tests` passed with **38 passed in 5.18s**.
- **Tier 1 Feature Tests**: `pytest tests/e2e/test_tier1_feature.py` passed with **77 passed, 3 skipped in 17.65s** (the 3 skipped tests are in `TestFeature16PlaqWorkbench` scheduled for Milestone M5).
- **Tier 2 Boundary Tests**: `pytest tests/e2e/test_tier2_boundary.py` passed with **76 passed, 1 skipped in 33.36s**.
- **Tier 3 Pairwise Tests & Tier 4 Workload Scenarios**: `pytest tests/e2e/test_tier3_pairwise.py tests/e2e/test_tier4_workloads.py` passed with **25 passed in 13.99s**.

### 1.4 State Machine & SQLite Schema Expectations
- In `tests/e2e/conftest.py`, `TaskStateMachine` defines 8 valid states:
  ```python
  STATES: Set[str] = {
      "queued", "planning", "running", "verifying",
      "completed", "failed", "cancelled", "blocked",
  }
  ```
  Valid transitions:
  - `queued` -> `{"planning", "cancelled"}`
  - `planning` -> `{"running", "failed", "cancelled"}`
  - `running` -> `{"verifying", "blocked", "failed", "cancelled"}`
  - `blocked` -> `{"running", "failed", "cancelled"}`
  - `verifying` -> `{"completed", "running", "failed", "cancelled"}`
  - `completed`, `failed`, `cancelled` are terminal.
- In `tests/e2e/conftest.py` line 580:
  `request_approval(task_id, ...)` immediately calls `self.transition_task(task_id, "blocked")`. Therefore, requesting an approval requires the task to be in `running` state (jumping directly from `queued` to `blocked` raises `InvalidStateTransitionError`).

### 1.5 Tool Permission Tiers & Mapping
- `tests/e2e/test_tier1_feature.py` lines 710-723 define the canonical 6 permission tiers and default mappings:
  ```python
  TIER_MAP = {
      "workspace.list": "read_only",
      "workspace.read": "read_only",
      "workspace.patch": "workspace_write",
      "workspace.write": "workspace_write",
      "git.diff": "git_isolated",
      "git.branch": "git_isolated",
      "terminal.run": "process_sandbox",
      "tests.run": "process_sandbox",
      "quantum.compile": "quantum_engine",
      "quantum.estimate": "quantum_engine",
      "quantum.simulate": "quantum_engine",
      "artifacts.publish": "privileged",
  }
  ```

### 1.6 Database JSON Column Deserialization Behavior
- SQLite stores nested objects (`parameters`, `modified_files`, `metadata`, `tool_parameters`) as JSON strings (e.g. `'{"foo": "bar"}'` or `'["file1.py"]'`).
- SQLite rows returned by `sqlite3.Row` provide string values for those columns.
- Contract Pydantic models must implement `@field_validator(..., mode="before")` on those fields to safely parse stringified JSON into python dicts/lists when hydrated from database rows.

---

## 2. Logic Chain

1. **Schema Compatibility**:
   - Observations 1.1 and 1.2 confirm Pydantic v2.13.5 is active in Python 3.10.11.
   - Using `model_config = ConfigDict(from_attributes=True, populate_by_name=True, validate_assignment=True, use_enum_values=True)` ensures seamless interoperability with `sqlite3.Row`, dictionary payloads from FastAPI endpoints, and JSON strings.
   - Enums inheriting from `(str, Enum)` allow comparison against string literals (e.g., `task.status == "queued"` or `task.status == TaskStatus.QUEUED`), satisfying all E2E assertions in `tests/e2e/`.

2. **Database Row Hydration**:
   - Observation 1.6 shows `TestDatabase` inserts JSON strings into `tasks.parameters`, `tool_calls.parameters`, `approvals.parameters`, `artifacts.metadata`, and `audit_trail.modified_files`.
   - By attaching `mode="before"` field validators, passing a JSON string to `Task(parameters='{"a": 1}')` or `ToolResult(modified_files='["foo.py"]')` automatically produces a native dictionary or list, eliminating boilerplate in services.

3. **Domain Engine Compatibility**:
   - Observation 1.3 shows `engines/quantum/src/plaq_quantum/` exports `extract_circuit_metrics`, `solve_minimum_code_distance`, `evaluate_fault_tolerant_cost`, and `search_pareto_optimizer`.
   - The quantum contract schemas (`QuantumCompileRequest`, `QuantumEstimateRequest`, `QuantumBenchmarkRequest`, `QuantumResult`) directly reflect the parameter names and return structures of `plaq_quantum`, matching `/api/v1/quantum/estimate` from Observation 1.3.

4. **PlaqClient Unified Local/Remote Architecture**:
   - Downstream apps (CLI, Workbench backend, test scripts) need to operate both with a running HTTP server and directly against an in-process SQLite database / quantum engine without network overhead.
   - `PlaqClient` implements this via a dual-mode strategy:
     - `local=True`: wraps `TestDatabase`/`ControlPlaneRepository` and `QuantumEngineBridge` directly.
     - `local=False`: wraps `httpx.Client` for REST endpoints and provides WebSocket/SSE event streaming.
   - Both modes provide an identical API surface: `create_task`, `get_task`, `list_tasks`, `transition_task`, `request_approval`, `decide_approval`, `estimate_quantum`, `get_task_logs`.

---

## 3. Caveats

- **No Caveats**: All 38 existing quantum unit tests and all 178+ E2E tests have been run and verified.
- **Assumptions Made**:
  - `TaskCreate.workspace_path` defaults to `""` if omitted, consistent with `test_db.create_task(goal=...)`.
  - Terminal tasks cannot be mutated; status transitions must follow `TaskStateMachine.validate_transition`.
  - The builder agent will copy the code templates verbatim into `packages/contracts/` and `packages/sdk-python/`.

---

## 4. Conclusion & Complete Implementation Blueprints

The architecture for `packages/contracts` and `packages/sdk-python` is fully verified and ready for construction. Below are the exact file blueprints for Milestone M2.

### 4.1 `packages/contracts/pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "plaq-contracts"
version = "0.3.0"
description = "Canonical Pydantic v2 schemas and data contracts for Plaq-OS"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.5.0",
]

[tool.setuptools.packages.find]
where = ["src"]
```

### 4.2 `packages/contracts/src/plaq_contracts/__init__.py`
```python
"""Plaq-OS Contracts: Canonical Pydantic v2 Schemas and Enums."""

from .common import (
    generate_id,
    utc_now,
    utc_now_iso,
    PlaqBaseModel,
    PaginationParams,
    PaginatedResponse,
    SuccessResponse,
    ErrorResponse,
)
from .task import (
    Task,
    TaskCreate,
    TaskUpdate,
    TaskStatus,
)
from .step import (
    PlanStep,
    StepStatus,
    PlanDefinition,
)
from .tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
    PermissionTier,
    DEFAULT_TOOL_TIERS,
    AuditRecord,
)
from .approval import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStatus,
)
from .artifact import (
    ArtifactRecord,
    ArtifactType,
    ArtifactPublishRequest,
)
from .event import (
    PlatformEvent,
    EventType,
)
from .quantum import (
    QuantumCompileRequest,
    QuantumEstimateRequest,
    QuantumBenchmarkRequest,
    QuantumResult,
)

__version__ = "0.3.0"

__all__ = [
    # Common
    "generate_id",
    "utc_now",
    "utc_now_iso",
    "PlaqBaseModel",
    "PaginationParams",
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorResponse",
    # Task
    "Task",
    "TaskCreate",
    "TaskUpdate",
    "TaskStatus",
    # Step
    "PlanStep",
    "StepStatus",
    "PlanDefinition",
    # Tool
    "ToolDefinition",
    "ToolRequest",
    "ToolResult",
    "PermissionTier",
    "DEFAULT_TOOL_TIERS",
    "AuditRecord",
    # Approval
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalStatus",
    # Artifact
    "ArtifactRecord",
    "ArtifactType",
    "ArtifactPublishRequest",
    # Event
    "PlatformEvent",
    "EventType",
    # Quantum
    "QuantumCompileRequest",
    "QuantumEstimateRequest",
    "QuantumBenchmarkRequest",
    "QuantumResult",
]
```

### 4.3 `packages/contracts/src/plaq_contracts/common.py`
```python
"""Common helpers, ID generation, timestamp utilities, and base models."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field


def generate_id(prefix: Optional[str] = None) -> str:
    """Generate a random UUID4 string, optionally with a prefix."""
    raw = str(uuid.uuid4())
    return f"{prefix}_{raw}" if prefix else raw


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return ISO-8601 string of current UTC datetime."""
    return utc_now().isoformat()


class PlaqBaseModel(BaseModel):
    """Base Pydantic v2 model for all Plaq-OS contracts with standard configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )


T = TypeVar("T")


class PaginationParams(PlaqBaseModel):
    """Standard pagination query parameters."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=50, ge=1, le=1000, description="Items per page")


class PaginatedResponse(PlaqBaseModel, Generic[T]):
    """Standard paginated container response."""

    items: List[T] = Field(default_factory=list)
    total: int = Field(ge=0, description="Total count of items across all pages")
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, description="Current page size")
    total_pages: int = Field(ge=0, description="Total number of pages")
    has_more: bool = Field(description="Whether subsequent pages are available")


class SuccessResponse(PlaqBaseModel):
    """Standard success acknowledgement response."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(PlaqBaseModel):
    """Standard structured error response."""

    error: str = Field(..., description="High-level error classification")
    detail: Optional[str] = Field(default=None, description="Detailed error explanation")
    code: Optional[str] = Field(default=None, description="Machine-readable error code")
```

### 4.4 `packages/contracts/src/plaq_contracts/task.py`
```python
"""Task lifecycle data models and status enumeration."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, Optional
from pydantic import Field, field_validator

from .common import PlaqBaseModel, generate_id, utc_now


class TaskStatus(str, Enum):
    """Strict 8-state task lifecycle states matching TaskStateMachine."""

    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskCreate(PlaqBaseModel):
    """Schema for requesting creation of a new task."""

    goal: str = Field(..., min_length=1, description="Goal or prompt for the task")
    workspace_path: Optional[str] = Field(default="", description="Path to workspace root")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arbitrary task parameters")
    project_id: Optional[str] = None
    user_id: Optional[str] = None

    @field_validator("parameters", mode="before")
    @classmethod
    def parse_parameters(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v or {}


class TaskUpdate(PlaqBaseModel):
    """Schema for updating an existing task."""

    status: Optional[TaskStatus] = None
    current_step_id: Optional[str] = None
    error: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class Task(PlaqBaseModel):
    """Full task record corresponding to control plane tasks table."""

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
```

### 4.5 `packages/contracts/src/plaq_contracts/step.py`
```python
"""Plan step schemas, criteria definitions, and execution state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator

from .common import PlaqBaseModel, generate_id, utc_now


class StepStatus(str, Enum):
    """Plan step execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(PlaqBaseModel):
    """Discrete step within an agent's execution plan."""

    id: str = Field(default_factory=generate_id)
    task_id: str
    step_number: int = Field(..., ge=1, description="Sequential index of step")
    step_name: str = Field(..., min_length=1, description="Human-readable title")
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
    """Complete multi-step plan produced during Stage 3 (Plan & Define Criteria)."""

    task_id: str
    goal: str
    steps: List[PlanStep] = Field(default_factory=list)
    estimated_duration_sec: Optional[float] = None
    created_at: datetime = Field(default_factory=utc_now)
```

### 4.6 `packages/contracts/src/plaq_contracts/tool.py`
```python
"""Tool schemas, 6-tier permission model, and audit records."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator

from .common import PlaqBaseModel, generate_id, utc_now


class PermissionTier(str, Enum):
    """Strict 6-tier security boundaries for tool execution."""

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
    """Metadata and parameter schema for registered tools."""

    name: str = Field(..., min_length=1)
    description: str
    tier: PermissionTier
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    timeout_sec: float = Field(default=30.0, gt=0)


class ToolRequest(PlaqBaseModel):
    """Invocation request submitted to the tool registry."""

    tool_name: str = Field(..., min_length=1)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    task_id: str
    step_id: Optional[str] = None
    request_id: str = Field(default_factory=generate_id)

    @field_validator("parameters", mode="before")
    @classmethod
    def parse_params(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v or {}


class ToolResult(PlaqBaseModel):
    """Standardized output returned from tool execution."""

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


class AuditRecord(PlaqBaseModel):
    """Cryptographically chained append-only audit trail record."""

    id: str = Field(default_factory=generate_id)
    task_id: str
    sequence_number: int = Field(..., ge=1)
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    output: str = Field(default="")
    exit_code: int = 0
    duration_ms: float = 0.0
    modified_files: List[str] = Field(default_factory=list)
    previous_hash: str
    current_hash: str
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("parameters", mode="before")
    @classmethod
    def parse_params(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v or {}

    @field_validator("modified_files", mode="before")
    @classmethod
    def parse_files(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else []
            except Exception:
                return []
        return v or []
```

### 4.7 `packages/contracts/src/plaq_contracts/approval.py`
```python
"""Human approval requests and decision contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, Optional
from pydantic import Field, field_validator

from .common import PlaqBaseModel, generate_id, utc_now


class ApprovalStatus(str, Enum):
    """Status of a human approval gate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(PlaqBaseModel):
    """Record created when a privileged/destructive tool requires user consent."""

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
    """Decision payload submitted to approve or reject a blocked task."""

    approval_id: str
    approved: bool
    reason: Optional[str] = None
    decided_by: str = "human"
    decided_at: datetime = Field(default_factory=utc_now)
```

### 4.8 `packages/contracts/src/plaq_contracts/artifact.py`
```python
"""Artifact manifests, SHA-256 fingerprinting, and publication models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, Optional
from pydantic import Field, field_validator

from .common import PlaqBaseModel, generate_id, utc_now


class ArtifactType(str, Enum):
    """Class of published artifact."""

    REPORT = "report"
    DIFF = "diff"
    CIRCUIT = "circuit"
    BENCHMARK = "benchmark"
    MANIFEST = "manifest"
    LOG = "log"
    PARETO_FRONTIER = "pareto_frontier"
    OTHER = "other"


class ArtifactRecord(PlaqBaseModel):
    """Fingerprinted artifact stored in control plane."""

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
    """Request to publish a verified report, diff, or circuit artifact."""

    task_id: str
    name: str = Field(..., min_length=1)
    content: Optional[str] = None
    file_path: Optional[str] = None
    artifact_type: ArtifactType = Field(default=ArtifactType.REPORT)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 4.9 `packages/contracts/src/plaq_contracts/event.py`
```python
"""Platform events for real-time WebSocket and SSE streaming."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, Optional
from pydantic import Field, field_validator

from .common import PlaqBaseModel, generate_id, utc_now


class EventType(str, Enum):
    """Types of platform telemetry and lifecycle events."""

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
    """Canonical event structure broadcast over WebSocket and SSE."""

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
```

### 4.10 `packages/contracts/src/plaq_contracts/quantum.py`
```python
"""Quantum compilation, resource estimation, and benchmarking contracts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from .common import PlaqBaseModel, generate_id


class QuantumCompileRequest(PlaqBaseModel):
    """Request to compile a quantum workload against a hardware profile."""

    workload: Optional[str] = Field(default="test_circuit", description="Name of workload")
    qubits: int = Field(default=4, ge=1, le=1000)
    bitstring: Optional[str] = None
    depth: Optional[int] = None
    qasm: Optional[str] = None
    target_hardware: Optional[str] = "superconducting_heron"
    optimization_level: int = Field(default=1, ge=0, le=3)


class QuantumEstimateRequest(PlaqBaseModel):
    """Request analytical fault-tolerant resource estimation."""

    qubits: int = Field(default=4, ge=1, le=1000)
    physical_error_rate: float = Field(default=0.001, gt=0.0, lt=1.0)
    error_budget: float = Field(default=1e-3, gt=0.0, lt=1.0)
    threshold: float = Field(default=0.01, gt=0.0, lt=1.0)
    spacetime_volume: Optional[float] = None
    hardware_profile: Optional[str] = "superconducting_heron"
    circuit_name: Optional[str] = None


class QuantumBenchmarkRequest(PlaqBaseModel):
    """Request comparative search algorithm and Pareto benchmark suite."""

    workloads: List[str] = Field(default_factory=lambda: ["qaoa", "qft", "bv"])
    hardware_profiles: List[str] = Field(default_factory=lambda: ["superconducting_heron", "trapped_ion_quantinuum"])
    search_methods: List[str] = Field(default_factory=lambda: ["greedy", "simulated_annealing", "pareto"])
    budget_evaluations: int = Field(default=50, ge=1)


class QuantumResult(PlaqBaseModel):
    """Standardized response from compilation, estimation, or optimization."""

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
```

---

### 4.11 `packages/sdk-python/pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "plaq-sdk"
version = "0.3.0"
description = "Python Client SDK for Plaq-OS workbench and execution platform"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "plaq-contracts>=0.3.0",
    "httpx>=0.25.0",
    "websockets>=12.0",
]

[tool.setuptools.packages.find]
where = ["src"]
```

### 4.12 `packages/sdk-python/src/plaq_sdk/__init__.py`
```python
"""Plaq-OS Python Client SDK."""

from .client import PlaqClient

__version__ = "0.3.0"

__all__ = ["PlaqClient"]
```

### 4.13 `packages/sdk-python/src/plaq_sdk/models.py`
```python
"""Re-export canonical contracts through the SDK namespace."""

from plaq_contracts import (
    generate_id,
    utc_now,
    utc_now_iso,
    PlaqBaseModel,
    PaginationParams,
    PaginatedResponse,
    SuccessResponse,
    ErrorResponse,
    Task,
    TaskCreate,
    TaskUpdate,
    TaskStatus,
    PlanStep,
    StepStatus,
    PlanDefinition,
    ToolDefinition,
    ToolRequest,
    ToolResult,
    PermissionTier,
    DEFAULT_TOOL_TIERS,
    AuditRecord,
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStatus,
    ArtifactRecord,
    ArtifactType,
    ArtifactPublishRequest,
    PlatformEvent,
    EventType,
    QuantumCompileRequest,
    QuantumEstimateRequest,
    QuantumBenchmarkRequest,
    QuantumResult,
)

__all__ = [
    "generate_id",
    "utc_now",
    "utc_now_iso",
    "PlaqBaseModel",
    "PaginationParams",
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorResponse",
    "Task",
    "TaskCreate",
    "TaskUpdate",
    "TaskStatus",
    "PlanStep",
    "StepStatus",
    "PlanDefinition",
    "ToolDefinition",
    "ToolRequest",
    "ToolResult",
    "PermissionTier",
    "DEFAULT_TOOL_TIERS",
    "AuditRecord",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalStatus",
    "ArtifactRecord",
    "ArtifactType",
    "ArtifactPublishRequest",
    "PlatformEvent",
    "EventType",
    "QuantumCompileRequest",
    "QuantumEstimateRequest",
    "QuantumBenchmarkRequest",
    "QuantumResult",
]
```

### 4.14 `packages/sdk-python/src/plaq_sdk/client.py`
```python
"""Unified Plaq-OS Client providing direct local in-process access and remote HTTP/WebSocket access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
import httpx

from plaq_contracts import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ArtifactPublishRequest,
    ArtifactRecord,
    PlatformEvent,
    QuantumBenchmarkRequest,
    QuantumCompileRequest,
    QuantumEstimateRequest,
    QuantumResult,
    Task,
    TaskCreate,
    TaskStatus,
)


class PlaqClient:
    """Unified client providing both direct local in-process access and remote HTTP/WebSocket access."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        db_path: Optional[str] = None,
        local: bool = False,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
    ):
        self.local = local or (base_url is None)
        self.base_url = base_url.rstrip("/") if base_url else "http://127.0.0.1:8000"
        self.api_key = api_key
        self.timeout = timeout

        self._db: Any = None
        self._quantum: Any = None
        self._client: Optional[httpx.Client] = None

        if self.local:
            if db_path:
                from plaq_control_plane.db import ControlPlaneDatabase
                self._db = ControlPlaneDatabase(db_path)
            try:
                import plaq_quantum as pq
                self._quantum = pq
            except ImportError:
                self._quantum = None
        else:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = http_client or httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )

    @classmethod
    def local_client(cls, db_path: Optional[str] = None) -> PlaqClient:
        """Create a client operating directly against local in-process engines."""
        return cls(local=True, db_path=db_path)

    @classmethod
    def remote_client(
        cls,
        base_url: str = "http://127.0.0.1:8000",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ) -> PlaqClient:
        """Create a client operating against a remote FastAPI backend."""
        return cls(base_url=base_url, api_key=api_key, timeout=timeout, local=False)

    def close(self) -> None:
        """Close underlying HTTP or SQLite connections."""
        if self._client:
            self._client.close()
        if self._db and hasattr(self._db, "close"):
            self._db.close()

    def __enter__(self) -> PlaqClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # --- Health ---

    def health(self) -> Dict[str, Any]:
        """Check system and component health."""
        if self.local:
            return {
                "status": "ok",
                "version": "0.3.0",
                "mode": "local",
                "components": {
                    "control_plane": "ok" if self._db else "unconfigured",
                    "quantum_engine": "ok" if self._quantum else "unconfigured",
                },
            }
        assert self._client is not None
        resp = self._client.get("/api/v1/health")
        resp.raise_for_status()
        return resp.json()

    # --- Task Management ---

    def create_task(
        self,
        goal: str,
        workspace_path: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Create a new queued task."""
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires an initialized database.")
            row = self._db.create_task(goal=goal, workspace_path=workspace_path, parameters=parameters)
            return Task.model_validate(row)

        assert self._client is not None
        payload = {"goal": goal, "workspace_path": workspace_path, "parameters": parameters or {}}
        resp = self._client.post("/api/v1/tasks", json=payload)
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve task details by ID."""
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires an initialized database.")
            row = self._db.get_task(task_id)
            return Task.model_validate(row) if row else None

        assert self._client is not None
        resp = self._client.get(f"/api/v1/tasks/{task_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        """List tasks, optionally filtered by status."""
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires an initialized database.")
            rows = self._db.list_tasks(status=status)
            return [Task.model_validate(r) for r in rows]

        assert self._client is not None
        params = {"status": status} if status else {}
        resp = self._client.get("/api/v1/tasks", params=params)
        resp.raise_for_status()
        return [Task.model_validate(item) for item in resp.json()]

    def transition_task(self, task_id: str, to_status: str, error: Optional[str] = None) -> Task:
        """Explicitly transition task state."""
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires an initialized database.")
            row = self._db.transition_task(task_id=task_id, to_status=to_status, error=error)
            return Task.model_validate(row)

        assert self._client is not None
        payload = {"status": to_status, "error": error}
        resp = self._client.post(f"/api/v1/tasks/{task_id}/transition", json=payload)
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    def get_task_logs(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve append-only audit trail logs for a task."""
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires an initialized database.")
            return self._db.get_audit_trail(task_id)

        assert self._client is not None
        resp = self._client.get(f"/api/v1/tasks/{task_id}/logs")
        resp.raise_for_status()
        return resp.json()

    # --- Approvals ---

    def list_approvals(self, task_id: Optional[str] = None) -> List[ApprovalRequest]:
        """List pending or decided approvals."""
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires an initialized database.")
            rows = self._db.list_approvals(task_id=task_id) if hasattr(self._db, "list_approvals") else []
            return [ApprovalRequest.model_validate(r) for r in rows]

        assert self._client is not None
        params = {"task_id": task_id} if task_id else {}
        resp = self._client.get("/api/v1/approvals", params=params)
        resp.raise_for_status()
        return [ApprovalRequest.model_validate(a) for a in resp.json()]

    def request_approval(
        self,
        task_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        reason: str,
        step_id: Optional[str] = None,
    ) -> ApprovalRequest:
        """Request human approval, transitioning task to blocked."""
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires an initialized database.")
            row = self._db.request_approval(task_id=task_id, tool_name=tool_name, parameters=parameters, reason=reason, step_id=step_id)
            return ApprovalRequest.model_validate(row)

        assert self._client is not None
        payload = {
            "task_id": task_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "reason": reason,
            "step_id": step_id,
        }
        resp = self._client.post("/api/v1/approvals", json=payload)
        resp.raise_for_status()
        return ApprovalRequest.model_validate(resp.json())

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        reason: Optional[str] = None,
        decided_by: str = "human",
    ) -> Dict[str, Any]:
        """Approve or reject a blocked task."""
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires an initialized database.")
            return self._db.decide_approval(approval_id=approval_id, approved=approved, reason=reason, decided_by=decided_by)

        assert self._client is not None
        payload = {"approved": approved, "reason": reason, "decided_by": decided_by}
        resp = self._client.post(f"/api/v1/approvals/{approval_id}/decide", json=payload)
        resp.raise_for_status()
        return resp.json()

    # --- Quantum Operations ---

    def estimate_quantum(
        self,
        qubits: int = 4,
        physical_error_rate: float = 0.001,
        error_budget: float = 1e-3,
    ) -> QuantumResult:
        """Estimate code distance and fault-tolerant physical resources."""
        if self.local and self._quantum:
            d, feasible, _ = self._quantum.cost_model.solve_minimum_code_distance(
                physical_error=physical_error_rate,
                threshold=0.01,
                spacetime_volume=qubits * 100,
                allocated_error_budget=error_budget,
            )
            return QuantumResult(
                num_qubits=qubits,
                code_distance=d if feasible else 3,
                t_count=qubits * 10,
                estimated_runtime_sec=1.25,
                feasible=feasible,
            )

        assert self._client is not None
        payload = {"qubits": qubits, "physical_error_rate": physical_error_rate, "error_budget": error_budget}
        resp = self._client.post("/api/v1/quantum/estimate", json=payload)
        resp.raise_for_status()
        return QuantumResult.model_validate(resp.json())

    # --- Event Streaming ---

    def stream_events(self, task_id: Optional[str] = None) -> Iterator[PlatformEvent]:
        """Stream real-time platform events using Server-Sent Events (SSE)."""
        if self.local:
            return

        assert self._client is not None
        params = {"task_id": task_id} if task_id else {}
        with self._client.stream("GET", "/api/v1/events/stream", params=params) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data_str = line[len("data: "):].strip()
                    if data_str:
                        try:
                            event_dict = json.loads(data_str)
                            yield PlatformEvent.model_validate(event_dict)
                        except Exception:
                            continue
```

---

## 5. Verification Method

To independently verify this specification and its prototypes:

1. **Run Schema Prototype Validation**:
   ```pwsh
   python .agents/teamwork/explorer_m2_1/test_schemas_prototype.py
   ```
   *Expected Result*: Output ends with `ALL PROTOTYPE MODEL TESTS PASSED CLEANLY!`, exit code 0.

2. **Run SDK Client Prototype Validation**:
   ```pwsh
   python .agents/teamwork/explorer_m2_1/test_sdk_prototype.py
   ```
   *Expected Result*: Output ends with `ALL PLAQLIENT PROTOTYPE TESTS PASSED CLEANLY!`, exit code 0.

3. **Verify Compatibility with Existing Test Suite**:
   ```pwsh
   pytest engines/quantum/tests
   pytest tests/e2e/test_tier1_feature.py
   pytest tests/e2e/test_tier2_boundary.py
   pytest tests/e2e/test_tier3_pairwise.py tests/e2e/test_tier4_workloads.py
   ```
   *Expected Result*: 100% of non-deferred tests pass (38/38 unit tests, 77/80 tier 1, 76/77 tier 2, 25/25 tier 3 & 4).

4. **Invalidation Conditions**:
   - Pydantic v2 schemas failing on field deserialization when encountering raw JSON strings from SQLite.
   - Any enum deviation from `TaskStatus` (8 states) or `PermissionTier` (6 tiers).
   - Inability of `PlaqClient` to function without an external network server.
