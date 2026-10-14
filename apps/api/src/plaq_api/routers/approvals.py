"""Human approval gate management router for Plaq-OS API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from plaq_control_plane.repository import ControlPlaneRepository
from plaq_api.deps import get_repo

router = APIRouter(prefix="/api/v1/approvals", tags=["Approvals"])


class ApprovalCreatePayload(BaseModel):
    task_id: str
    tool_name: str
    parameters: Dict[str, Any]
    reason: str
    step_id: Optional[str] = None


class ApprovalDecisionPayload(BaseModel):
    approved: bool
    reason: Optional[str] = None
    decided_by: Optional[str] = "human"


@router.get("")
def list_approvals(
    task_id: Optional[str] = Query(default=None, description="Filter by task ID"),
    repo: ControlPlaneRepository = Depends(get_repo),
) -> List[Dict[str, Any]]:
    """List pending and decided approval requests."""
    return repo.list_approvals(task_id=task_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def request_approval(
    payload: ApprovalCreatePayload,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Create a pending approval request and transition task to blocked."""
    try:
        return repo.request_approval(
            task_id=payload.task_id,
            tool_name=payload.tool_name,
            parameters=payload.parameters,
            reason=payload.reason,
            step_id=payload.step_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{approval_id}/decide")
def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionPayload,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Approve or reject a pending approval request."""
    try:
        return repo.decide_approval(
            approval_id=approval_id,
            approved=payload.approved,
            reason=payload.reason,
            decided_by=payload.decided_by or "human",
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found",
        )
