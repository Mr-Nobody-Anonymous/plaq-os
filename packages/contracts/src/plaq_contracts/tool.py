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
