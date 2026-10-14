"""Plaq-OS Persistent Control Plane, State Engine & Audit Trail."""

from .audit import (
    AuditChainer,
    AuditEntry,
    AuditIntegrityError,
    AuditTrailManager,
)
from .db import (
    ControlPlaneDatabase,
    DatabaseEngine,
    SCHEMA_SQL,
)
from .models import (
    StepDTO,
    TaskDTO,
    UserDTO,
    WorkspaceDTO,
    row_to_dict,
    rows_to_dicts,
)
from .recovery import (
    CheckpointRecoveryManager,
    RecoveryManager,
    RehydratedTaskContext,
)
from .redact import (
    SecretRedactor,
    redact_sensitive_info,
)
from .repository import (
    ControlPlaneRepository,
)
from .state_machine import (
    InvalidStateTransitionError,
    StateTransitionError,
    TaskStateMachine,
)

__version__ = "0.1.0"

__all__ = [
    # DB
    "DatabaseEngine",
    "ControlPlaneDatabase",
    "SCHEMA_SQL",
    # State Machine
    "TaskStateMachine",
    "InvalidStateTransitionError",
    "StateTransitionError",
    # Repository
    "ControlPlaneRepository",
    # Audit
    "AuditTrailManager",
    "AuditChainer",
    "AuditIntegrityError",
    "AuditEntry",
    # Redaction
    "SecretRedactor",
    "redact_sensitive_info",
    # Recovery
    "CheckpointRecoveryManager",
    "RecoveryManager",
    "RehydratedTaskContext",
    # Models
    "TaskDTO",
    "StepDTO",
    "UserDTO",
    "WorkspaceDTO",
    "row_to_dict",
    "rows_to_dicts",
]
