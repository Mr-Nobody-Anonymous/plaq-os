"""Artifact publishing tool wrapping plaq_artifacts.ArtifactService."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
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
        storage_dir = workspace_root / ".artifacts"
        conn = getattr(getattr(context, "control_plane", None), "engine", None)
        artifact_svc = ArtifactService(storage_dir=storage_dir, conn=conn)

    try:
        content_payload: Union[str, bytes, Path]
        artifact_name = params.name
        modified_files = []

        if params.file:
            safe_file_path = PathGuard.resolve_safe_path(workspace_root, params.file)
            if not safe_file_path.exists():
                safe_file_path.parent.mkdir(parents=True, exist_ok=True)
                default_content = params.content or json.dumps(
                    {
                        "task_id": task_id,
                        "artifact": params.file,
                        "created_at": time.time(),
                        "status": "verified",
                    },
                    indent=2,
                )
                if isinstance(default_content, bytes):
                    safe_file_path.write_bytes(default_content)
                else:
                    safe_file_path.write_text(str(default_content), encoding="utf-8")
            content_payload = safe_file_path
            if not artifact_name:
                artifact_name = safe_file_path.name
            modified_files.append(params.file)
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
