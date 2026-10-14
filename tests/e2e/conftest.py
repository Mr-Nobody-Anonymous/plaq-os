"""Shared Test Fixtures and Harness for Plaq-OS E2E Test Suite.

Provides:
- sys.path configuration for all monorepo directories
- temp_workspace: isolated git-initialized temporary workspace
- test_db: SQLite WAL-mode database with complete 9-table schema and CRUD helpers
- event_recorder: event capture for sync/async event streams
- quantum_engine: dynamic loader for quantum co-design engine
- Contract helpers: SecretRedactor, PathGuard, TaskStateMachine, AuditChainer
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pytest

# Ensure all monorepo paths are available on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MONOREPO_SRC_DIRS = [
    PROJECT_ROOT,
    PROJECT_ROOT / "apps" / "api" / "src",
    PROJECT_ROOT / "apps" / "cli" / "src",
    PROJECT_ROOT / "packages" / "contracts" / "src",
    PROJECT_ROOT / "packages" / "sdk-python" / "src",
    PROJECT_ROOT / "services" / "control-plane" / "src",
    PROJECT_ROOT / "services" / "sandbox-manager" / "src",
    PROJECT_ROOT / "services" / "model-gateway" / "src",
    PROJECT_ROOT / "services" / "agent-runtime" / "src",
    PROJECT_ROOT / "services" / "artifact-service" / "src",
    PROJECT_ROOT / "engines" / "quantum" / "src",
]

for src_dir in MONOREPO_SRC_DIRS:
    str_dir = str(src_dir)
    if str_dir not in sys.path:
        sys.path.insert(0, str_dir)

# Starlette 1.x compatibility shim for FastAPI 0.109.x
try:
    import starlette.routing
    _orig_router_init = starlette.routing.Router.__init__
    def _patched_router_init(self, *args, **kwargs):
        kwargs.pop("on_startup", None)
        kwargs.pop("on_shutdown", None)
        return _orig_router_init(self, *args, **kwargs)
    starlette.routing.Router.__init__ = _patched_router_init
except Exception:
    pass

try:
    import fastapi
    setattr(fastapi.FastAPI, "max_body_size", None)
except Exception:
    pass


# ---------------------------------------------------------------------------
# Exceptions & Contract Definitions
# ---------------------------------------------------------------------------

class PathTraversalError(ValueError):
    """Raised when a path attempts to escape the designated workspace root."""
    pass


class InvalidStateTransitionError(ValueError):
    """Raised when a task attempts an unauthorized state machine transition."""
    pass


class AuditIntegrityError(ValueError):
    """Raised when an append-only audit trail hash chain has been tampered with."""
    pass


# ---------------------------------------------------------------------------
# Contract Helper: Secret Redactor
# ---------------------------------------------------------------------------

class SecretRedactor:
    """Scrubs sensitive tokens, passwords, AWS keys, and credentials from logs."""

    PATTERNS = [
        # Bearer tokens (JWTs or arbitrary alphanumeric tokens)
        (re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
        # GitHub Personal Access Tokens
        (re.compile(r"\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{36,})\b"), "[REDACTED_GH_TOKEN]"),
        # Slack Tokens
        (re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{20,})\b"), "[REDACTED_SLACK_TOKEN]"),
        # Basic Auth URLs (http://user:password@host)
        (re.compile(r"(https?://[^:\s]+:)([^@\s]+)(@)", re.IGNORECASE), r"\1[REDACTED]\3"),
        # AWS Access Key IDs
        (re.compile(r"\b((?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
        # AWS Secret Access Keys
        (re.compile(r"((?:aws_secret_access_key|aws_secret)\s*[:=]\s*['\"]?)([A-Za-z0-9/+=]{16,})(['\"]?)", re.IGNORECASE), r"\1[REDACTED_SECRET_KEY]\3"),
        # Generic API keys and passwords in assignments / queries
        (re.compile(r"((?:api[_-]?key|password|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?)([^\s'\"&,;]+)(['\"]?)", re.IGNORECASE), r"\1[REDACTED]\3"),
        # Multiline private key headers
        (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    ]

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Redact sensitive patterns from arbitrary text."""
        if not isinstance(text, str):
            return str(text)
        redacted = text
        for pattern, replacement in cls.PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    @classmethod
    def redact_json(cls, data: Any) -> Any:
        """Recursively redact dictionary/list structures."""
        sensitive_roots = {"password", "secret", "token", "apikey", "authorization", "privatekey", "accesskey"}
        if isinstance(data, dict):
            new_dict = {}
            for k, v in data.items():
                k_norm = k.lower().replace("_", "").replace("-", "")
                if any(sk in k_norm for sk in sensitive_roots):
                    new_dict[k] = "[REDACTED]"
                else:
                    new_dict[k] = cls.redact_json(v)
            return new_dict
        elif isinstance(data, list):
            return [cls.redact_json(item) for item in data]
        elif isinstance(data, str):
            return cls.redact_text(data)
        return data


# ---------------------------------------------------------------------------
# Contract Helper: PathGuard Resolver
# ---------------------------------------------------------------------------

class PathGuard:
    """Enforces workspace boundary confinement, rejecting traversal attacks."""

    @staticmethod
    def resolve_safe_path(workspace_root: str, relative_path: str) -> Path:
        """Resolve path and verify it stays inside workspace_root."""
        if not relative_path:
            return Path(workspace_root).resolve()

        # Reject null byte injection
        if "\0" in relative_path:
            raise PathTraversalError(f"Null byte detected in path: {relative_path!r}")

        # Decode URL-encoded traversal patterns
        import urllib.parse
        decoded = urllib.parse.unquote(relative_path).replace("%2e", ".").replace("%2f", "/").replace("%5c", "\\")

        root_canonical = Path(workspace_root).resolve()
        target = (root_canonical / decoded).resolve()

        try:
            target.relative_to(root_canonical)
        except ValueError as exc:
            raise PathTraversalError(
                f"Path traversal detected: '{relative_path}' resolves to '{target}', which escapes '{root_canonical}'"
            ) from exc

        return target


# ---------------------------------------------------------------------------
# Contract Helper: Task State Machine
# ---------------------------------------------------------------------------

class TaskStateMachine:
    """Enforces 8-state task lifecycle transitions."""

    STATES: Set[str] = {
        "queued",
        "planning",
        "running",
        "verifying",
        "completed",
        "failed",
        "cancelled",
        "blocked",
    }

    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        "queued": {"planning", "cancelled"},
        "planning": {"running", "failed", "cancelled"},
        "running": {"verifying", "blocked", "failed", "cancelled"},
        "blocked": {"running", "failed", "cancelled"},
        "verifying": {"completed", "running", "failed", "cancelled"},
        "completed": set(),  # Terminal state
        "failed": set(),     # Terminal state
        "cancelled": set(),  # Terminal state
    }

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        if from_state not in cls.STATES or to_state not in cls.STATES:
            return False
        return to_state in cls.ALLOWED_TRANSITIONS.get(from_state, set())

    @classmethod
    def validate_transition(cls, from_state: str, to_state: str) -> None:
        if not cls.can_transition(from_state, to_state):
            raise InvalidStateTransitionError(
                f"Invalid state transition: cannot transition from '{from_state}' to '{to_state}'."
            )


# ---------------------------------------------------------------------------
# Contract Helper: Append-Only Audit Chainer
# ---------------------------------------------------------------------------

class AuditChainer:
    """Manages SHA-256 cryptographic hash chaining for audit logs."""

    GENESIS_HASH = "0" * 64

    @classmethod
    def compute_record_hash(
        cls,
        previous_hash: str,
        task_id: str,
        tool_name: str,
        parameters: str,
        output: str,
        exit_code: int,
        duration_ms: float,
        modified_files: str,
    ) -> str:
        """Compute SHA-256 digest chaining the previous block's hash."""
        payload = f"{previous_hash}|{task_id}|{tool_name}|{parameters}|{output}|{exit_code}|{duration_ms:.2f}|{modified_files}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def verify_chain(cls, records: List[Dict[str, Any]]) -> bool:
        """Verify unbroken chain of hashes across all audit records."""
        expected_prev = cls.GENESIS_HASH
        for rec in records:
            actual_prev = rec.get("previous_hash")
            if actual_prev != expected_prev:
                return False

            recalculated = cls.compute_record_hash(
                previous_hash=actual_prev,
                task_id=rec["task_id"],
                tool_name=rec["tool_name"],
                parameters=rec.get("parameters", ""),
                output=rec.get("output", ""),
                exit_code=int(rec.get("exit_code", 0)),
                duration_ms=float(rec.get("duration_ms", 0.0)),
                modified_files=rec.get("modified_files", "[]"),
            )
            if recalculated != rec.get("current_hash"):
                return False

            expected_prev = rec["current_hash"]
        return True


# ---------------------------------------------------------------------------
# SQLite Test Database Engine Wrapper
# ---------------------------------------------------------------------------

class TestDatabase:
    """Relational SQLite test database backing the control plane schema in WAL mode."""
    __test__ = False

    SCHEMA_SQL = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        workspace_path TEXT NOT NULL,
        status TEXT NOT NULL,
        current_step_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        error TEXT,
        parameters TEXT
    );

    CREATE TABLE IF NOT EXISTS agent_sessions (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    );

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
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        step_id TEXT,
        tool_name TEXT NOT NULL,
        parameters TEXT,
        reason TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        decided_at TEXT,
        decided_by TEXT,
        decision_reason TEXT,
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    );

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

    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_steps_task_id ON steps(task_id);
    CREATE INDEX IF NOT EXISTS idx_audit_task_id ON audit_trail(task_id, sequence_number);
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, timeout=10.0, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA busy_timeout = 5000;")
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(self.SCHEMA_SQL)
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def create_task(self, goal: str, workspace_path: str = "", parameters: Optional[dict] = None) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        params_json = json.dumps(parameters or {})
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO tasks (id, goal, workspace_path, status, created_at, updated_at, parameters)
                VALUES (?, ?, ?, 'queued', ?, ?, ?)
                """,
                (task_id, goal, workspace_path, now, now, params_json),
            )
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            cursor = self.conn.execute("SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC", (status,))
        else:
            cursor = self.conn.execute("SELECT * FROM tasks ORDER BY created_at ASC")
        return [dict(r) for r in cursor.fetchall()]

    def transition_task(self, task_id: str, to_status: str, error: Optional[str] = None) -> Dict[str, Any]:
        current = self.get_task(task_id)
        if not current:
            raise KeyError(f"Task '{task_id}' not found.")

        current_status = current["status"]
        TaskStateMachine.validate_transition(current_status, to_status)

        now = datetime.now(timezone.utc).isoformat()
        completed_at = now if to_status in {"completed", "failed", "cancelled"} else None

        with self.conn:
            self.conn.execute(
                """
                UPDATE tasks
                SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at), error = COALESCE(?, error)
                WHERE id = ?
                """,
                (to_status, now, completed_at, error, task_id),
            )
        return self.get_task(task_id)

    def record_step(self, task_id: str, step_number: int, step_name: str, criteria: str) -> Dict[str, Any]:
        step_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO steps (id, task_id, step_number, step_name, criteria, status, started_at)
                VALUES (?, ?, ?, ?, ?, 'running', ?)
                """,
                (step_id, task_id, step_number, step_name, criteria, now),
            )
            self.conn.execute("UPDATE tasks SET current_step_id = ? WHERE id = ?", (step_id, task_id))
        cursor = self.conn.execute("SELECT * FROM steps WHERE id = ?", (step_id,))
        return dict(cursor.fetchone())

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
        """Record an append-only audit entry with secret redaction and hash chaining."""
        redacted_params = SecretRedactor.redact_json(parameters if parameters is not None else {})
        redacted_output = SecretRedactor.redact_text(output)
        params_str = json.dumps(redacted_params)
        files_str = json.dumps(modified_files or [])

        # Get previous sequence number and hash
        cursor = self.conn.execute(
            "SELECT sequence_number, current_hash FROM audit_trail WHERE task_id = ? ORDER BY sequence_number DESC LIMIT 1",
            (task_id,),
        )
        prev_row = cursor.fetchone()
        if prev_row:
            seq_num = prev_row["sequence_number"] + 1
            prev_hash = prev_row["current_hash"]
        else:
            seq_num = 1
            prev_hash = AuditChainer.GENESIS_HASH

        curr_hash = AuditChainer.compute_record_hash(
            previous_hash=prev_hash,
            task_id=task_id,
            tool_name=tool_name,
            parameters=params_str,
            output=redacted_output,
            exit_code=exit_code,
            duration_ms=duration_ms,
            modified_files=files_str,
        )

        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO audit_trail (
                    id, task_id, sequence_number, tool_name, parameters, output,
                    exit_code, duration_ms, modified_files, previous_hash, current_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    task_id,
                    seq_num,
                    tool_name,
                    params_str,
                    redacted_output,
                    exit_code,
                    duration_ms,
                    files_str,
                    prev_hash,
                    curr_hash,
                    now,
                ),
            )

        cursor = self.conn.execute("SELECT * FROM audit_trail WHERE id = ?", (entry_id,))
        return dict(cursor.fetchone())

    def get_audit_trail(self, task_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM audit_trail WHERE task_id = ? ORDER BY sequence_number ASC",
            (task_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def verify_audit_trail(self, task_id: str) -> bool:
        records = self.get_audit_trail(task_id)
        return AuditChainer.verify_chain(records)

    def request_approval(self, task_id: str, tool_name: str, parameters: dict, reason: str, step_id: Optional[str] = None) -> Dict[str, Any]:
        approval_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        params_str = json.dumps(parameters)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO approvals (id, task_id, step_id, tool_name, parameters, reason, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (approval_id, task_id, step_id, tool_name, params_str, reason, now),
            )
            # Blocking the task upon approval request
            self.transition_task(task_id, "blocked")
        cursor = self.conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        return dict(cursor.fetchone())

    def decide_approval(self, approval_id: str, approved: bool, decided_by: str = "human", reason: Optional[str] = None) -> Dict[str, Any]:
        cursor = self.conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        app_row = cursor.fetchone()
        if not app_row:
            raise KeyError(f"Approval '{approval_id}' not found.")

        task_id = app_row["task_id"]
        status = "approved" if approved else "rejected"
        now = datetime.now(timezone.utc).isoformat()

        with self.conn:
            self.conn.execute(
                """
                UPDATE approvals
                SET status = ?, decided_at = ?, decided_by = ?, decision_reason = ?
                WHERE id = ?
                """,
                (status, now, decided_by, reason, approval_id),
            )
            # Unblock or fail task
            if approved:
                self.transition_task(task_id, "running")
            else:
                self.transition_task(task_id, "failed", error=f"Approval rejected: {reason or 'Denied by user'}")

        cursor = self.conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        return dict(cursor.fetchone())

    def recover_active_tasks(self) -> List[Dict[str, Any]]:
        """Identify non-terminal tasks eligible for crash recovery."""
        active_statuses = ("queued", "planning", "running", "blocked", "verifying")
        placeholders = ",".join("?" for _ in active_statuses)
        cursor = self.conn.execute(
            f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY created_at ASC",
            active_statuses,
        )
        return [dict(r) for r in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Event Recorder Fixture Class
# ---------------------------------------------------------------------------

class EventRecorder:
    """Records real-time platform events emitted during tests."""

    def __init__(self):
        self._events: List[Dict[str, Any]] = []

    def record(self, event: Dict[str, Any]) -> None:
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._events.append(event)

    @property
    def events(self) -> List[Dict[str, Any]]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()

    def filter(self, event_type: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        results = self._events
        if event_type:
            results = [e for e in results if e.get("event_type") == event_type or e.get("type") == event_type]
        if task_id:
            results = [e for e in results if e.get("task_id") == task_id]
        return results

    def wait_for(self, predicate: Callable[[Dict[str, Any]], bool], timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        start = time.time()
        while time.time() - start < timeout:
            for event in self._events:
                if predicate(event):
                    return event
            time.sleep(0.05)
        return None


# ---------------------------------------------------------------------------
# Quantum Engine Dynamic Bridge
# ---------------------------------------------------------------------------

class QuantumEngineBridge:
    """Provides access to circuits, cost models, Stim simulation, and Pareto optimization."""

    def __init__(self):
        try:
            import plaq_quantum.circuits as circuits
            import plaq_quantum.cost_model as cost_model
            import plaq_quantum.hardware as hardware
            import plaq_quantum.stim_bridge as stim_bridge
            import plaq_quantum.optimizer as optimizer
            import plaq_quantum.baselines as baselines
            import plaq_quantum.search_algorithms as search_algorithms
            self.circuits = circuits
            self.cost_model = cost_model
            self.hardware = hardware
            self.stim_bridge = stim_bridge
            self.optimizer = optimizer
            self.baselines = baselines
            self.search_algorithms = search_algorithms
        except (ImportError, AttributeError):
            # Fallback to root modules
            import circuits
            import cost_model
            import hardware
            import stim_bridge
            import optimizer
            import baselines
            import search_algorithms
            self.circuits = circuits
            self.cost_model = cost_model
            self.hardware = hardware
            self.stim_bridge = stim_bridge
            self.optimizer = optimizer
            self.baselines = baselines
            self.search_algorithms = search_algorithms


# ---------------------------------------------------------------------------
# Pytest Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_workspace():
    """Create a temporary directory with an initialized git repository."""
    tmp_dir = tempfile.mkdtemp(prefix="plaq_test_workspace_")
    path = Path(tmp_dir).resolve()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=str(path), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Plaq Tester"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "tester@plaq.local"], cwd=str(path), check=True)

    # Initial file commit
    readme = path / "README.md"
    readme.write_text("# Test Workspace\nInitialized for Plaq-OS testing.\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(path), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    yield path

    # Cleanup with retry for Windows file locks
    for _ in range(5):
        try:
            shutil.rmtree(tmp_dir, ignore_errors=False)
            break
        except Exception:
            time.sleep(0.1)


@pytest.fixture
def test_db():
    """Create an isolated temporary SQLite database configured in WAL mode."""
    fd, path = tempfile.mkstemp(prefix="plaq_test_db_", suffix=".db")
    os.close(fd)
    db = TestDatabase(path)

    yield db

    db.close()
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except Exception:
            pass


@pytest.fixture
def event_recorder():
    """Fixture providing event capture and inspection."""
    return EventRecorder()


@pytest.fixture
def quantum_engine():
    """Fixture providing loaded quantum co-design engine modules."""
    return QuantumEngineBridge()
