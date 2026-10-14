"""Control Plane Repository providing CRUD, transactions, approval gating, and audit chaining."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from plaq_control_plane.audit import AuditChainer, AuditTrailManager
from plaq_control_plane.db import DatabaseEngine
from plaq_control_plane.redact import SecretRedactor
from plaq_control_plane.state_machine import TaskStateMachine


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class ControlPlaneRepository:
    """Data access repository for all control plane entities."""

    def __init__(self, db: Union[DatabaseEngine, sqlite3.Connection, str, Path]):
        if isinstance(db, (str, Path)):
            self.db = DatabaseEngine(str(db))
        elif hasattr(db, "connection") and hasattr(db, "transaction"):
            self.db = db
        else:
            # Wrapped single connection
            class _SingleConnAdapter:
                def __init__(self, c: sqlite3.Connection):
                    self._c = c
                def get_connection(self):
                    return self._c
                @property
                def conn(self):
                    return self._c
                def connection(self):
                    from contextlib import contextmanager
                    @contextmanager
                    def _ctx():
                        yield self._c
                    return _ctx()
                def transaction(self):
                    from contextlib import contextmanager
                    @contextmanager
                    def _ctx():
                        self._c.execute("BEGIN IMMEDIATE;")
                        try:
                            yield self._c
                            self._c.execute("COMMIT;")
                        except Exception:
                            self._c.execute("ROLLBACK;")
                            raise
                    return _ctx()
                def close(self):
                    self._c.close()
            self.db = _SingleConnAdapter(db)

        self._audit_manager = AuditTrailManager(self.db)

    def close(self) -> None:
        if hasattr(self.db, "close"):
            self.db.close()

    # -----------------------------------------------------------------------
    # Task Operations
    # -----------------------------------------------------------------------

    def create_task(
        self,
        goal: str,
        workspace_path: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new task with initial queued status."""
        if not goal or not str(goal).strip():
            raise ValueError("Goal cannot be empty or whitespace only")

        task_id = str(uuid.uuid4())
        now = _utc_now_iso()
        params_json = json.dumps(parameters or {})

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, goal, workspace_path, status, created_at, updated_at, parameters)
                VALUES (?, ?, ?, 'queued', ?, ?, ?)
                """,
                (task_id, goal, workspace_path, now, now, params_json),
            )
        return self.get_task(task_id)  # type: ignore

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve task by ID, returning None if not found."""
        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List tasks, optionally filtered by lifecycle status."""
        with self.db.connection() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC",
                    (status,),
                )
            else:
                cursor = conn.execute("SELECT * FROM tasks ORDER BY created_at ASC")
            return [dict(r) for r in cursor.fetchall()]

    def transition_task(
        self,
        task_id: str,
        to_status: str,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically transition task status with strict state machine validation."""
        current = self.get_task(task_id)
        if not current:
            raise KeyError(f"Task '{task_id}' not found.")

        current_status = current["status"]
        TaskStateMachine.validate_transition(current_status, to_status)

        now = _utc_now_iso()
        completed_at = now if TaskStateMachine.is_terminal(to_status) else None

        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = ?,
                    updated_at = ?,
                    completed_at = COALESCE(?, completed_at),
                    error = COALESCE(?, error)
                WHERE id = ?
                """,
                (to_status, now, completed_at, error, task_id),
            )
        return self.get_task(task_id)  # type: ignore

    # -----------------------------------------------------------------------
    # Step Operations
    # -----------------------------------------------------------------------

    def record_step(
        self,
        task_id: str,
        step_number: int,
        step_name: str,
        criteria: str,
    ) -> Dict[str, Any]:
        """Atomically insert step and advance task current_step_id."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        step_id = str(uuid.uuid4())
        now = _utc_now_iso()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO steps (id, task_id, step_number, step_name, criteria, status, started_at)
                VALUES (?, ?, ?, ?, ?, 'running', ?)
                """,
                (step_id, task_id, step_number, step_name, criteria, now),
            )
            conn.execute(
                "UPDATE tasks SET current_step_id = ?, updated_at = ? WHERE id = ?",
                (step_id, now, task_id),
            )

        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM steps WHERE id = ?", (step_id,))
            return dict(cursor.fetchone())

    def get_step(self, step_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve step by ID."""
        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM steps WHERE id = ?", (step_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_steps(self, task_id: str) -> List[Dict[str, Any]]:
        """List all steps for a task ordered by step_number."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM steps WHERE task_id = ? ORDER BY step_number ASC",
                (task_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def update_step(
        self,
        step_id: str,
        status: Optional[str] = None,
        error: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update step execution status and error."""
        step = self.get_step(step_id)
        if not step:
            raise KeyError(f"Step '{step_id}' not found.")

        now = _utc_now_iso()
        if status in {"completed", "failed"} and completed_at is None:
            completed_at = now

        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE steps
                SET status = COALESCE(?, status),
                    error = COALESCE(?, error),
                    completed_at = COALESCE(?, completed_at)
                WHERE id = ?
                """,
                (status, error, completed_at, step_id),
            )
        return self.get_step(step_id)  # type: ignore

    # -----------------------------------------------------------------------
    # Tool Call Operations
    # -----------------------------------------------------------------------

    def record_tool_call(
        self,
        task_id: str,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        exit_code: Optional[int] = None,
        modified_files: Optional[List[str]] = None,
        step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record execution details of an invoked tool."""
        call_id = str(uuid.uuid4())
        now = _utc_now_iso()
        params_str = json.dumps(parameters or {})
        files_str = json.dumps(modified_files or [])

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tool_calls (
                    id, step_id, task_id, tool_name, parameters, output, error,
                    duration_ms, exit_code, modified_files, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (call_id, step_id, task_id, tool_name, params_str, output, error, duration_ms, exit_code, files_str, now),
            )
        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM tool_calls WHERE id = ?", (call_id,))
            return dict(cursor.fetchone())

    # -----------------------------------------------------------------------
    # Approval Operations
    # -----------------------------------------------------------------------

    def request_approval(
        self,
        task_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        reason: str,
        step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create pending approval request and automatically transition task to blocked."""
        approval_id = str(uuid.uuid4())
        now = _utc_now_iso()
        params_str = json.dumps(parameters or {})

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO approvals (id, task_id, step_id, tool_name, parameters, reason, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (approval_id, task_id, step_id, tool_name, params_str, reason, now),
            )

        # Transition task to blocked
        self.transition_task(task_id, "blocked")

        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            return dict(cursor.fetchone())

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        decided_by: str = "human",
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Decide pending approval and resume or fail task accordingly."""
        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            row = cursor.fetchone()
            if not row:
                raise KeyError(f"Approval '{approval_id}' not found.")
            app_row = dict(row)

        task_id = app_row["task_id"]
        status = "approved" if approved else "rejected"
        now = _utc_now_iso()

        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status = ?, decided_at = ?, decided_by = ?, decision_reason = ?
                WHERE id = ?
                """,
                (status, now, decided_by, reason, approval_id),
            )

        if approved:
            self.transition_task(task_id, "running")
        else:
            rejection_err = f"Approval rejected: {reason or 'Denied by user'}"
            self.transition_task(task_id, "failed", error=rejection_err)

        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            return dict(cursor.fetchone())

    def list_approvals(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List approvals, optionally filtered by task_id."""
        with self.db.connection() as conn:
            if task_id:
                cursor = conn.execute(
                    "SELECT * FROM approvals WHERE task_id = ? ORDER BY created_at DESC",
                    (task_id,),
                )
            else:
                cursor = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC")
            return [dict(r) for r in cursor.fetchall()]

    # -----------------------------------------------------------------------
    # Audit Trail & Chaining
    # -----------------------------------------------------------------------

    def record_audit(
        self,
        task_id: str,
        tool_name: str,
        parameters: Any,
        output: str,
        exit_code: int = 0,
        duration_ms: float = 10.0,
        modified_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Record an append-only audit entry with secret redaction and SHA-256 hash chaining."""
        return self._audit_manager.record_audit(
            task_id=task_id,
            tool_name=tool_name,
            parameters=parameters,
            output=output,
            exit_code=exit_code,
            duration_ms=duration_ms,
            modified_files=modified_files,
        )

    def get_audit_trail(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve audit entries for task ordered by sequence_number."""
        return self._audit_manager.get_audit_trail(task_id)

    def verify_audit_trail(self, task_id: str) -> bool:
        """Validate unbroken cryptographic hash chain from genesis to latest record."""
        return self._audit_manager.verify_audit_trail(task_id)

    # -----------------------------------------------------------------------
    # Artifact Tracking
    # -----------------------------------------------------------------------

    def record_artifact(
        self,
        task_id: str,
        artifact_type: str,
        name: str,
        file_path: str,
        sha256_hash: str,
        size_bytes: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register published artifact record in the database."""
        artifact_id = str(uuid.uuid4())
        now = _utc_now_iso()
        meta_str = json.dumps(metadata or {})

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    id, task_id, artifact_type, name, file_path, sha256_hash,
                    size_bytes, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, task_id, artifact_type, name, file_path, sha256_hash, size_bytes, now, meta_str),
            )
        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
            return dict(cursor.fetchone())

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve artifact record by ID."""
        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_artifacts(
        self,
        task_id: Optional[str] = None,
        artifact_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List artifacts with optional filtering."""
        with self.db.connection() as conn:
            query = "SELECT * FROM artifacts WHERE 1=1"
            params: List[Any] = []
            if task_id:
                query += " AND task_id = ?"
                params.append(task_id)
            if artifact_type:
                query += " AND artifact_type = ?"
                params.append(artifact_type)
            query += " ORDER BY created_at DESC"
            cursor = conn.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    # -----------------------------------------------------------------------
    # Recovery Scan
    # -----------------------------------------------------------------------

    def recover_active_tasks(self) -> List[Dict[str, Any]]:
        """Retrieve all in-flight tasks eligible for crash recovery."""
        active_statuses = ("queued", "planning", "running", "blocked", "verifying")
        placeholders = ",".join("?" for _ in active_statuses)
        with self.db.connection() as conn:
            cursor = conn.execute(
                f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY created_at ASC",
                active_statuses,
            )
            return [dict(r) for r in cursor.fetchall()]
