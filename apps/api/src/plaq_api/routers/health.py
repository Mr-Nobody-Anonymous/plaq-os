"""Healthcheck router for Plaq-OS API."""

from __future__ import annotations

import platform
import sys
from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["Health"])


def _probe(mod: str) -> str:
    try:
        __import__(mod)
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def component_status() -> Dict[str, str]:
    comps = {
        "control_plane": _probe("plaq_control_plane"),
        "agent_runtime": _probe("plaq_agent_runtime"),
        "sandbox_manager": _probe("plaq_sandbox"),
        "quantum_engine": _probe("plaq_quantum"),
    }
    try:
        import plaq_quantum.stim_bridge as sb  # type: ignore

        if comps["quantum_engine"] == "ok" and not (getattr(sb, "HAS_STIM", False) and getattr(sb, "HAS_PYMATCHING", False)):
            comps["quantum_engine"] = "degraded (install stim + pymatching for QEC)"
    except Exception:
        pass
    return comps


@router.get("/health")
def get_health() -> Dict[str, Any]:
    """System health endpoint."""
    comps = component_status()
    values = list(comps.values())
    if any(v.startswith("error") for v in values):
        status = "error"
    elif any(v.startswith("degraded") for v in values):
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "version": "0.3.0",
        "mode": "standalone",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
        "components": comps,
    }


@router.get("/healthz")
def get_healthz() -> Dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "ok"}
