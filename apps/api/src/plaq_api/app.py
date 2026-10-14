"""FastAPI application factory for Plaq-OS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from plaq_api.routers import approvals, artifacts, health, quantum, stream, tasks
from plaq_api.deps import set_repo, set_runtime
from plaq_control_plane.repository import ControlPlaneRepository
from plaq_agent_runtime.loop import AgentRuntime


def create_app(
    repository: Optional[ControlPlaneRepository] = None,
    runtime: Optional[AgentRuntime] = None,
    workbench_dir: Optional[Path] = None,
) -> FastAPI:
    """Create and configure the Plaq-OS FastAPI application instance."""
    if repository:
        set_repo(repository)
    if runtime:
        set_runtime(runtime)

    app = FastAPI(
        title="Plaq-OS API",
        description="Unified REST & WebSocket API for Plaq-OS Quantum Computing Workbench",
        version="0.3.0",
    )

    # CORS configuration for workbench frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    app.include_router(health.router)
    app.include_router(tasks.router)
    app.include_router(approvals.router)
    app.include_router(quantum.router)
    app.include_router(artifacts.router)
    app.include_router(stream.router)

    # Workbench UI static files mount
    if workbench_dir is None:
        workbench_dir = Path(__file__).resolve().parents[3] / "workbench"

    if workbench_dir.exists():
        css_dir = workbench_dir / "css"
        js_dir = workbench_dir / "js"
        assets_dir = workbench_dir / "assets"

        if css_dir.exists():
            app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
        if js_dir.exists():
            app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/", include_in_schema=False)
        def serve_workbench():
            index_file = workbench_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            return {"message": "Plaq-OS API v0.3.0 is running. Workbench index.html not yet built."}

    return app


# Default app instance for ASGI servers (uvicorn apps.api.src.plaq_api.app:app)
app = create_app()
