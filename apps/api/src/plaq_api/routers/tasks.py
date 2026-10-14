"""Task management router for Plaq-OS API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from plaq_contracts.task import Task
from plaq_control_plane.repository import ControlPlaneRepository
from plaq_control_plane.state_machine import InvalidStateTransitionError
from plaq_api.deps import get_repo, get_runtime
from plaq_agent_runtime.loop import AgentRuntime

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


class TaskCreatePayload(BaseModel):
    goal: str = Field(..., description="High-level goal for the task")
    workspace_path: Optional[str] = Field(default="", description="Workspace root path")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Optional parameters dict")


class TaskTransitionPayload(BaseModel):
    status: str = Field(..., description="Target lifecycle status")
    error: Optional[str] = Field(default=None, description="Error message if transitioned to failed")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreatePayload,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Create a new task with initial 'queued' status."""
    goal_str = payload.goal.strip() if payload.goal else ""
    if not goal_str:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Goal cannot be empty",
        )
    try:
        task_dict = repo.create_task(
            goal=goal_str,
            workspace_path=payload.workspace_path or "",
            parameters=payload.parameters,
        )
        return task_dict
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("")
def list_tasks(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    repo: ControlPlaneRepository = Depends(get_repo),
) -> List[Dict[str, Any]]:
    """List tasks, optionally filtered by status."""
    return repo.list_tasks(status=status)


@router.get("/{task_id}")
def get_task(
    task_id: str,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Retrieve task details by ID."""
    t = repo.get_task(task_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
    return t


@router.post("/{task_id}/transition")
def transition_task(
    task_id: str,
    payload: TaskTransitionPayload,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Transition task status with strict validation."""
    try:
        return repo.transition_task(task_id=task_id, to_status=payload.status, error=payload.error)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
    except (InvalidStateTransitionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{task_id}/logs")
def get_task_logs(
    task_id: str,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> List[Dict[str, Any]]:
    """Retrieve audit trail logs for task."""
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
    return repo.get_audit_trail(task_id)


@router.post("/{task_id}/cancel")
def cancel_task(
    task_id: str,
    runtime: AgentRuntime = Depends(get_runtime),
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Cancel an in-flight or queued task."""
    try:
        success = runtime.cancel_task(task_id)
        task = repo.get_task(task_id)
        return {"cancelled": success, "task": task}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")


@router.post("/{task_id}/resume")
def resume_task(
    task_id: str,
    runtime: AgentRuntime = Depends(get_runtime),
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Resume a blocked or interrupted task."""
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
    try:
        result = runtime.resume_task(task_id)
        return {
            "task_id": result.task_id,
            "status": result.status,
            "summary": result.summary,
            "artifacts": result.artifacts,
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
