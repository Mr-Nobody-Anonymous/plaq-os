"""FastAPI application factory for Plaq-OS."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import sys

from plaq_api.auth import SESSION_COOKIE, is_authorized, resolve_api_key
from plaq_api.routers import approvals, artifacts, health, jobs, quantum, stream, tasks, workspace
from plaq_api.deps import get_repo, get_runtime, set_repo, set_runtime
from plaq_control_plane.repository import ControlPlaneRepository
from plaq_agent_runtime.loop import AgentRuntime


class LoginPayload(BaseModel):
    key: str


def _cors_origins() -> list[str]:
    """Return CORS allow-list from PLAQ_CORS_ORIGINS (comma-separated).

    Defaults to localhost workbench origins. Set PLAQ_CORS_ORIGINS="*" to
    allow any origin (credentials are then disabled, per spec).
    """
    raw = os.environ.get("PLAQ_CORS_ORIGINS")
    if raw is None:
        raw = "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:8500,http://localhost:8500"
    raw = raw.strip()
    if raw == "*":
        return ["*"]
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://127.0.0.1:8000"]


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

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        import asyncio
        from plaq_api.deps import get_broadcaster
        get_broadcaster().bind_loop(asyncio.get_running_loop())
        if os.environ.get("PLAQ_QUEUE", "1").strip().lower() not in {"0", "false", "off"} and "pytest" not in sys.modules:
            from plaq_agent_runtime.queue import get_queue

            get_queue(get_repo(), get_runtime())
        yield
        try:
            from plaq_agent_runtime.queue import reset_queues

            reset_queues()
        except Exception:
            pass

    app = FastAPI(
        title="Plaq-OS API",
        description="Unified REST & WebSocket API for Plaq-OS Quantum Computing Workbench",
        version="0.3.0",
        lifespan=lifespan,
    )

    # CORS configuration for workbench frontend.
    # NOTE: allow_origins=["*"] with allow_credentials=True is invalid per
    # the Fetch spec (browsers reject it). We use an explicit allow-list
    # and only enable credentials for non-wildcard origins.
    origins = _cors_origins()
    allow_credentials = "*" not in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # API-key auth is ON by default for real servers (key is loaded or
    # generated next to the control-plane DB). pytest and PLAQ_AUTH=off
    # keep the suite / local docker open. Health + docs stay public.
    api_key = resolve_api_key(generate=True)

    @app.post("/api/v1/session", include_in_schema=False)
    def login(payload: LoginPayload, request: Request):
        if not api_key or not is_authorized(api_key, authorization="Bearer " + payload.key):
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        response = JSONResponse({"ok": True})
        response.set_cookie(SESSION_COOKIE, api_key, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", path="/")
        response.headers["Cache-Control"] = "no-store"
        return response

    if api_key:

        @app.middleware("http")
        async def _api_key_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
            path = request.url.path
            public = {
                "/api/v1/health",
                "/api/v1/healthz",
                "/api/v1/session",
                "/docs",
                "/redoc",
                "/openapi.json",
            }
            if path.startswith("/api/v1/") and path not in public:
                if not is_authorized(
                    api_key,
                    authorization=request.headers.get("authorization", ""),
                    cookie=request.cookies.get(SESSION_COOKIE, ""),
                ):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Missing or invalid API key"},
                    )
            # Cookie authentication must not authorize cross-origin state changes.
            if request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get(SESSION_COOKIE):
                origin = request.headers.get("origin")
                if origin and origin != str(request.base_url).rstrip("/"):
                    return JSONResponse(status_code=403, content={"detail": "Cross-origin request rejected"})
            return await call_next(request)

    # Register API routers
    app.include_router(health.router)
    app.include_router(tasks.router)
    app.include_router(approvals.router)
    app.include_router(quantum.router)
    app.include_router(artifacts.router)
    app.include_router(stream.router)
    app.include_router(jobs.router)
    app.include_router(workspace.router)

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
                response = FileResponse(index_file)
                return response
            return {"message": "Plaq-OS API v0.3.0 is running. Workbench index.html not yet built."}

    return app


# Default app instance for ASGI servers (uvicorn apps.api.src.plaq_api.app:app)
app = create_app()
