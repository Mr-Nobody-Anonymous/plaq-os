"""Database Transfer Objects (DTOs) and row mappers for Plaq-OS Control Plane."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import sqlite3
from typing import Any, Dict, List, Optional

from plaq_contracts import (
    ApprovalRequest,
    ApprovalStatus,
    ArtifactRecord,
    ArtifactType,
    AuditRecord,
    PlanStep,
    StepStatus,
    Task,
    TaskStatus,
)


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Convert an sqlite3.Row object into a standard dictionary."""
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    """Convert a list of sqlite3.Row objects into standard dictionaries."""
    return [dict(r) for r in rows]


@dataclass
class UserDTO:
    id: str
    username: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> UserDTO:
        return cls(id=row["id"], username=row["username"], created_at=row["created_at"])


@dataclass
class ProjectDTO:
    id: str
    name: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ProjectDTO:
        return cls(id=row["id"], name=row["name"], created_at=row["created_at"])


@dataclass
class WorkspaceDTO:
    id: str
    project_id: Optional[str]
    path: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> WorkspaceDTO:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            path=row["path"],
            created_at=row["created_at"],
        )


@dataclass
class TaskDTO:
    id: str
    goal: str
    workspace_path: str
    status: str
    current_step_id: Optional[str]
    created_at: str
    updated_at: str
    completed_at: Optional[str]
    error: Optional[str]
    parameters: Optional[Dict[str, Any]]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TaskDTO:
        params = row["parameters"]
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        return cls(
            id=row["id"],
            goal=row["goal"],
            workspace_path=row["workspace_path"],
            status=row["status"],
            current_step_id=row["current_step_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            error=row["error"],
            parameters=params,
        )

    def to_contract(self) -> Task:
        return Task.model_validate(asdict(self))


@dataclass
class StepDTO:
    id: str
    task_id: str
    step_number: int
    step_name: str
    criteria: str
    status: str
    started_at: str
    completed_at: Optional[str]
    error: Optional[str]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> StepDTO:
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            step_number=row["step_number"],
            step_name=row["step_name"],
            criteria=row["criteria"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error=row["error"],
        )

    def to_contract(self) -> PlanStep:
        return PlanStep.model_validate(asdict(self))
