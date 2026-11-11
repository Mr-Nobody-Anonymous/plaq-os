"""Background job router for Plaq-OS API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from plaq_api.deps import get_repo
from plaq_control_plane.repository import ControlPlaneRepository

router = APIRouter(prefix="/api/v1", tags=["Jobs"])


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")
    return job


@router.get("/jobs")
def list_jobs(
    task_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    repo: ControlPlaneRepository = Depends(get_repo),
) -> List[Dict[str, Any]]:
    return repo.list_jobs(task_id=task_id, status=status_filter)
