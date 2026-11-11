"""Lightweight SQLite migration runner for the Plaq-OS control plane.

Migrations are numbered integers applied exactly once and recorded in
``schema_migrations``. ``CREATE TABLE IF NOT EXISTS`` in ``SCHEMA_SQL`` still
bootstraps a fresh database; this runner covers upgrades of existing files.
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Callable, List, Sequence, Tuple

MigrationFn = Callable[[sqlite3.Connection], None]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_registry(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _m001_jobs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'execute',
            status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
            result_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_task_id ON jobs(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")


MIGRATIONS: Sequence[Tuple[int, str, MigrationFn]] = (
    (1, "jobs_table", _m001_jobs),
)


def applied_versions(conn: sqlite3.Connection) -> List[int]:
    _ensure_registry(conn)
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [int(r[0]) for r in rows]


def apply_migrations(conn: sqlite3.Connection) -> List[int]:
    """Apply pending migrations. Returns the versions that were applied."""
    _ensure_registry(conn)
    done = set(applied_versions(conn))
    applied: List[int] = []
    for version, name, fn in MIGRATIONS:
        if version in done:
            continue
        fn(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, _utc_now_iso()),
        )
        applied.append(version)
    return applied
