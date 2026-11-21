"""Artifact publishing tool wrapping plaq_artifacts.ArtifactService."""

from __future__ import annotations

from pathlib import Path
import os
import time
from typing import Any, Dict, Optional, Union

from pydantic import Field
from plaq_contracts.common import PlaqBaseModel
from plaq_contracts.tool import ToolResult
from plaq_artifacts.service import ArtifactService
from plaq_sandbox.guard import PathGuard


class ArtifactPublishParams(PlaqBaseModel):
    """Parameters for artifacts.publish."""
    file: Optional[str] = Field(default=None, description="Path to file in workspace to publish as artifact")
    name: Optional[str] = Field(default=None, description="Display name for published artifact")
    previous_output: bool = Field(default=False, description="Publish the preceding successful tool output")
    content: Optional[Union[str, bytes]] = Field(default=None, description="Direct text or bytes content")
    artifact_type: str = Field(default="report", description="Artifact classification (report, diff, manifest, benchmark)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Structured metadata dictionary")


def artifacts_publish(params: ArtifactPublishParams, context: Any) -> ToolResult:
    """Publish artifact to content-addressable storage and record in control plane."""
    t0 = time.perf_counter()
    workspace_root = Path(getattr(context, "workspace_path", ".")).resolve()
    task_id = getattr(context, "task_id", "default_task")

    artifact_svc: Optional[ArtifactService] = getattr(context, "artifact_service", None)
    if artifact_svc is None:
        # Default storage directory under workspace or system temp
        storage_dir = Path(os.environ.get("PLAQ_ARTIFACT_DIR", workspace_root / ".artifacts")).expanduser()
        conn = getattr(getattr(context, "control_plane", None), "db", None)
        artifact_svc = ArtifactService(storage_dir=storage_dir, conn=conn)

    try:
        content_payload: Union[str, bytes, Path]
        artifact_name = params.name
        modified_files = []

        if params.file:
            safe_file_path = PathGuard.resolve_safe_path(workspace_root, params.file)
            if not safe_file_path.is_file():
                raise FileNotFoundError(f"Artifact file not found: {params.file}")
            content_payload = safe_file_path
            if not artifact_name:
                artifact_name = safe_file_path.name
        elif params.previous_output:
            repo = getattr(context, "control_plane", None)
            if repo is None:
                raise ValueError("Previous output requires a control plane")
            with repo.db.connection() as conn:
                row = conn.execute(
                    "SELECT output FROM tool_calls WHERE task_id = ? AND exit_code = 0 ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                ).fetchone()
            if not row or not row["output"]:
                raise ValueError("No previous successful tool output to publish")
            content_payload = row["output"]
            if not artifact_name:
                artifact_name = "tool-output.json"
        elif params.content is not None:
            content_payload = params.content
            if not artifact_name:
                artifact_name = f"artifact_{int(time.time())}.txt"
        else:
            return ToolResult(
                success=False,
                output="",
                error="Either 'file' or 'content' must be specified to publish an artifact",
                duration_ms=(time.perf_counter() - t0) * 1000,
                exit_code=1,
                modified_files=[],
            )

        record = artifact_svc.publish_artifact(
            task_id=task_id,
            artifact_type=params.artifact_type,
            name=artifact_name,
            content=content_payload,
            metadata=params.metadata,
        )

        output_str = (
            f"Artifact published: id={record.id}, name={record.name}, "
            f"sha256={record.sha256_hash}, size_bytes={record.size_bytes}"
        )

        return ToolResult(
            success=True,
            output=output_str,
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=0,
            modified_files=modified_files,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            output="",
            error=str(exc),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )
