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
