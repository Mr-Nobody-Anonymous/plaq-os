"""SQLite Database Engine with WAL mode, thread-local connection pooling, and 10-table schema."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Generator, List, Optional, Union

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);

-- 2. Projects Table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 3. Workspaces Table
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 4. Tasks Table
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    workspace_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'planning', 'running', 'verifying', 'completed', 'failed', 'cancelled', 'blocked')),
    current_step_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT,
    parameters TEXT
);

-- 5. Agent Sessions Table
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- 6. Steps Table
CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    step_name TEXT NOT NULL,
    criteria TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- 7. Tool Calls Table
CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    step_id TEXT,
    task_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    parameters TEXT,
    output TEXT,
    error TEXT,
    duration_ms REAL NOT NULL DEFAULT 0.0,
    exit_code INTEGER,
    modified_files TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES steps(id) ON DELETE SET NULL
);

-- 8. Approvals Table
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_id TEXT,
    tool_name TEXT NOT NULL,
    parameters TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,
    decision_reason TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES steps(id) ON DELETE SET NULL
);

-- 9. Artifacts Table
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- 10. Append-Only Audit Trail Table
CREATE TABLE IF NOT EXISTS audit_trail (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    parameters TEXT,
    output TEXT,
    exit_code INTEGER NOT NULL,
    duration_ms REAL NOT NULL,
    modified_files TEXT,
    previous_hash TEXT NOT NULL,
    current_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_steps_task_id ON steps(task_id, step_number);
CREATE INDEX IF NOT EXISTS idx_audit_task_id ON audit_trail(task_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_approvals_task_status ON approvals(task_id, status);
CREATE INDEX IF NOT EXISTS idx_artifacts_task_id ON artifacts(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_step_id ON tool_calls(step_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_task_id ON tool_calls(task_id);
"""


class DatabaseEngine:
    """Manages SQLite connections with WAL mode, busy timeout, and thread-local isolation."""

    def __init__(self, db_path: Union[str, Path] = "plaq_control_plane.db", timeout: float = 10.0):
        self.db_path = str(db_path)
        self.timeout = timeout
        self._local = threading.local()
        self._all_connections: List[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self.init_schema()

    def _create_connection(self) -> sqlite3.Connection:
        """Create and configure a new SQLite connection with mandatory PRAGMAs."""
        if self.db_path != ":memory:" and not self.db_path.startswith("file:"):
            parent = Path(self.db_path).parent
            parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode by default; transactions managed explicitly
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")

        with self._lock:
            self._all_connections.append(conn)
        return conn

    def get_connection(self) -> sqlite3.Connection:
        """Retrieve thread-local SQLite connection, creating it if needed."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._create_connection()
            self._local.conn = conn
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Property for direct connection access compatible with test harness."""
        return self.get_connection()

    def init_schema(self) -> None:
        """Initialize all 10 schema tables and performance indexes."""
        conn = self.get_connection()
        conn.executescript(SCHEMA_SQL)

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding the active connection."""
        yield self.get_connection()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager executing block inside an atomic BEGIN IMMEDIATE transaction."""
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def wal_checkpoint(self, mode: str = "TRUNCATE") -> None:
        """Flush WAL log to disk using PRAGMA wal_checkpoint."""
        valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
        mode_upper = mode.upper()
        if mode_upper not in valid_modes:
            raise ValueError(f"Invalid WAL checkpoint mode: '{mode}'. Must be one of {valid_modes}")
        conn = self.get_connection()
        conn.execute(f"PRAGMA wal_checkpoint({mode_upper});")

    def close(self) -> None:
        """Idempotently close all connections opened across threads."""
        with self._lock:
            for c in self._all_connections:
                try:
                    c.close()
                except Exception:
                    pass
            self._all_connections.clear()
        self._local.conn = None


class ControlPlaneDatabase(DatabaseEngine):
    """ControlPlaneDatabase alias providing unified repository and database capabilities."""
    pass
