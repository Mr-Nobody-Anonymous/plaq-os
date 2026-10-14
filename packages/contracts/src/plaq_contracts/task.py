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

    @field_validator("parameters", mode="before")
    @classmethod
    def parse_parameters(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v


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
