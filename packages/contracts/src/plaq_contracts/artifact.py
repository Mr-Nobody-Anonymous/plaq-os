"""Artifact manifests, SHA-256 fingerprinting, and publication models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, Optional
from pydantic import Field, field_validator

from .common import PlaqBaseModel, generate_id, utc_now


class ArtifactType(str, Enum):
    """Class of published artifact."""

    REPORT = "report"
    DIFF = "diff"
    CIRCUIT = "circuit"
    BENCHMARK = "benchmark"
    MANIFEST = "manifest"
    LOG = "log"
    PARETO_FRONTIER = "pareto_frontier"
    QUANTUM_PARETO = "quantum_pareto"
    QUANTUM_MANIFEST = "quantum_manifest"
    BENCHMARK_CSV = "benchmark_csv"
    CODE_PATCH = "code_patch"
    GENERIC = "generic"
    OTHER = "other"


class ArtifactRecord(PlaqBaseModel):
    """Fingerprinted artifact stored in control plane."""

    id: str = Field(default_factory=generate_id)
    task_id: str
    artifact_type: ArtifactType = Field(default=ArtifactType.REPORT)
    name: str = Field(..., min_length=1)
    file_path: str
    sha256_hash: str = Field(..., min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def parse_metadata_json(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        return v or {}


class ArtifactPublishRequest(PlaqBaseModel):
    """Request to publish a verified report, diff, or circuit artifact."""

    task_id: str
    name: str = Field(..., min_length=1)
    content: Optional[str] = None
    file_path: Optional[str] = None
    artifact_type: ArtifactType = Field(default=ArtifactType.REPORT)
    metadata: Dict[str, Any] = Field(default_factory=dict)
