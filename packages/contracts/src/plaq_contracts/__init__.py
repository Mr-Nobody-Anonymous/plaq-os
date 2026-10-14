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

__version__ = "0.1.0"

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
