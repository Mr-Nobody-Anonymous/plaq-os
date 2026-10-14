"""Dependency providers for Plaq-OS FastAPI backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from plaq_control_plane.repository import ControlPlaneRepository
from plaq_agent_runtime.loop import AgentRuntime
from plaq_api.events import EventBroadcaster, broadcaster

_default_repo: Optional[ControlPlaneRepository] = None
_default_runtime: Optional[AgentRuntime] = None


def get_default_db_path() -> str:
    """Return configured or default SQLite database path."""
    env_path = os.environ.get("PLAQ_DB_PATH")
    if env_path:
        return env_path
    data_dir = Path.home() / ".plaq"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "plaq.db")


def get_repo() -> ControlPlaneRepository:
    """Dependency provider for ControlPlaneRepository."""
    global _default_repo
    if _default_repo is None:
        db_path = get_default_db_path()
        _default_repo = ControlPlaneRepository(db_path)
    return _default_repo


def set_repo(repo: ControlPlaneRepository) -> None:
    """Override repository (e.g. for testing with in-memory or fixture database)."""
    global _default_repo
    _default_repo = repo


def get_broadcaster() -> EventBroadcaster:
    """Dependency provider for EventBroadcaster."""
    return broadcaster


def get_runtime() -> AgentRuntime:
    """Dependency provider for AgentRuntime."""
    global _default_runtime
    if _default_runtime is None:
        repo = get_repo()
        _default_runtime = AgentRuntime(repository=repo)
    return _default_runtime


def set_runtime(runtime: AgentRuntime) -> None:
    """Override runtime (e.g. for testing)."""
    global _default_runtime
    _default_runtime = runtime
