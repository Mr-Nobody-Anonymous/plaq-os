"""SQLite migration runner."""

from __future__ import annotations

from pathlib import Path

from plaq_control_plane.db import DatabaseEngine, resolve_db_path
from plaq_control_plane.migrations import MIGRATIONS, applied_versions, apply_migrations


def test_fresh_db_applies_migrations():
    engine = DatabaseEngine(":memory:")
    conn = engine.conn
    versions = applied_versions(conn)
    assert 1 in versions
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "jobs" in tables
    assert "schema_migrations" in tables
    # Idempotent
    again = apply_migrations(conn)
    assert again == []
    engine.close()


def test_resolve_db_path_expands_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("PLAQ_DB_PATH", raising=False)
    expanded = Path(resolve_db_path("~/nested/plaq.db"))
    assert expanded == tmp_path / "nested" / "plaq.db"
    monkeypatch.setenv("PLAQ_DB_PATH", str(tmp_path / "from-env.db"))
    assert Path(resolve_db_path()) == tmp_path / "from-env.db"


def test_database_engine_expands_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    engine = DatabaseEngine("~/engine.db")
    assert Path(engine.db_path) == tmp_path / "engine.db"
    engine.close()


def test_migration_catalog_is_sorted():
    versions = [v for v, _, _ in MIGRATIONS]
    assert versions == sorted(versions)
    assert versions[0] == 1
