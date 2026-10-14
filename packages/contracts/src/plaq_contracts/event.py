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
