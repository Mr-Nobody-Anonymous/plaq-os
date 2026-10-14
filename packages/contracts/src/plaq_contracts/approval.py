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
