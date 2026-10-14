"""Artifact storage and inspection router for Plaq-OS API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from plaq_control_plane.repository import ControlPlaneRepository
from plaq_artifacts.service import ArtifactService
from plaq_api.deps import get_repo

router = APIRouter(prefix="/api/v1/artifacts", tags=["Artifacts"])


@router.get("")
def list_artifacts(
    task_id: Optional[str] = Query(default=None, description="Filter by task ID"),
    artifact_type: Optional[str] = Query(default=None, description="Filter by type"),
    repo: ControlPlaneRepository = Depends(get_repo),
) -> List[Dict[str, Any]]:
    """List published artifacts."""
    return repo.list_artifacts(task_id=task_id, artifact_type=artifact_type)


@router.get("/{artifact_id}")
def get_artifact(
    artifact_id: str,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Retrieve artifact metadata by ID."""
    art = repo.get_artifact(artifact_id)
    if not art:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    return art


@router.get("/{artifact_id}/content")
def get_artifact_content(
    artifact_id: str,
    repo: ControlPlaneRepository = Depends(get_repo),
) -> Response:
    """Retrieve raw artifact content bytes."""
    art = repo.get_artifact(artifact_id)
    if not art:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    file_path = Path(art["file_path"])
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact payload file missing from storage: {file_path}",
        )
    content = file_path.read_bytes()
    media_type = "application/json" if art["name"].endswith(".json") else "text/plain"
    return Response(content=content, media_type=media_type)
