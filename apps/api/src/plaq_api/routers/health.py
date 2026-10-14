"""Healthcheck router for Plaq-OS API."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["Health"])


@router.get("/health")
def get_health() -> Dict[str, Any]:
    """System health endpoint."""
    return {
        "status": "ok",
        "version": "0.3.0",
        "mode": "standalone",
        "components": {
            "control_plane": "ok",
            "quantum_engine": "ok",
            "agent_runtime": "ok",
            "sandbox_manager": "ok",
        },
    }


@router.get("/healthz")
def get_healthz() -> Dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "ok"}
