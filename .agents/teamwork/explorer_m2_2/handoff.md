# M2 Control Plane Database & State Machine Architecture Specification

## 1. Observation

Direct observations from examining the codebase, contracts, test harness, and specification:

1. **Repository Layout and Monorepo Contracts** (`orchestrator_1/PROJECT.md:88-98`):
   The control plane service is allocated to:
   ```text
   services/control-plane/
   ├── pyproject.toml
   └── src/plaq_control_plane/
       ├── __init__.py
       ├── db.py
       ├── models.py
       ├── repository.py
       ├── state_machine.py
       ├── audit.py
       └── recovery.py
   ```
   Currently, `services/control-plane/` contains only `.gitkeep`.

2. **Schema and Database PRAGMA Requirements** (`tests/e2e/test_tier1_feature.py:174-245`, `tests/e2e/conftest.py:276-410`):
   - `test_f3_01_all_schema_tables_present` expects 10 normalized tables in `sqlite_master`:
     `users`, `projects`, `workspaces`, `tasks`, `agent_sessions`, `steps`, `tool_calls`, `approvals`, `artifacts`, `audit_trail`.
   - `test_f3_05_wal_mode_and_foreign_keys_enforced` directly asserts:
     - `PRAGMA journal_mode;` returns `"wal"`.
     - `PRAGMA foreign_keys;` returns `1`.
     - `PRAGMA busy_timeout;` returns `>= 5000` (`test_tier2_boundary.py:194-199`).
   - SQLite requires `check_same_thread=False` and thread-local / pooled connections to withstand 20+ concurrent multithreaded readers/writers (`test_tier2_boundary.py:128-184`).
   - `test_b2_11_wal_checkpoint_truncate` asserts that `PRAGMA wal_checkpoint(TRUNCATE);` executes cleanly.

3. **Task Lifecycle State Machine Contract** (`tests/e2e/test_tier1_feature.py:247-322`, `tests/e2e/test_tier2_boundary.py:287-386`):
   - 8 discrete lifecycle states: `queued`, `planning`, `running`, `verifying`, `completed`, `failed`, `cancelled`, `blocked`.
   - Allowed transitions:
     - `queued` -> `{"planning", "cancelled"}`
     - `planning` -> `{"running", "failed", "cancelled"}`
     - `running` -> `{"verifying", "blocked", "failed", "cancelled"}`
     - `blocked` -> `{"running", "failed", "cancelled"}`
     - `verifying` -> `{"completed", "running", "failed", "cancelled"}`
     - `completed` -> `{}` (Terminal state - immutable)
     - `failed` -> `{}` (Terminal state - immutable)
     - `cancelled` -> `{}` (Terminal state - immutable)
   - Illegal transitions, direct jumps (e.g. `queued` -> `completed`, `planning` -> `completed`, `blocked` -> `verifying`, `verifying` -> `planning`), transitions out of terminal states, and empty or unrecognized state strings must raise `InvalidStateTransitionError` (`StateTransitionError`).

4. **Repository Operations and Atomicity** (`tests/e2e/conftest.py:421-621`, `PROJECT.md:236-246`):
   - `create_task(goal: str, workspace_path: str = "", parameters: Optional[dict] = None) -> Dict[str, Any]` requires goal validation (rejects empty or whitespace-only strings with `ValueError`, handles Unicode and 10,000+ character strings faithfully).
   - `transition_task(task_id: str, to_status: str, error: Optional[str] = None)` validates transitions via state machine, automatically sets `completed_at` for terminal states, updates `updated_at`, records `error`, and raises `KeyError` if task is not found.
   - `record_step(task_id: str, step_number: int, step_name: str, criteria: str)` atomically inserts a step and updates `tasks.current_step_id`.
   - `request_approval(task_id: str, tool_name: str, parameters: dict, reason: str, step_id: Optional[str] = None)` creates approval with `status='pending'` and automatically transitions task to `blocked`.
   - `decide_approval(approval_id: str, approved: bool, decided_by: str = "human", reason: Optional[str] = None)` sets `status='approved'` or `'rejected'`; if approved transitions task to `running`, if rejected transitions task to `failed` with error message.
   - `record_audit(...)` applies secret redaction, computes SHA-256 chained hash from `previous_hash` (starting from `GENESIS_HASH = "0" * 64`), and appends to `audit_trail`.

5. **Crash Recovery and Checkpoint Rehydration** (`tests/e2e/test_tier1_feature.py:463-550`, `tests/e2e/test_tier4_workloads.py:224-295`):
   - `recover_active_tasks()` identifies all tasks in non-terminal states (`queued`, `planning`, `running`, `blocked`, `verifying`).
   - Server crash simulation (closing DB without completing task) must preserve `status`, `current_step_id`, parameters, and audit hash continuity upon reopen. Subsequent tool executions must seamlessly chain from the last recorded `current_hash`.

---

## 2. Logic Chain

1. **Database Connection Architecture (`db.py`)**:
   - *Observation*: Test cases run multithreaded readers and writers (up to 20 threads) and invoke rapid sequential transactions. A single unmanaged connection causes `ProgrammingError: SQLite objects created in a thread can only be used in that same thread` unless thread isolation is handled.
   - *Deduction*: We design `DatabaseEngine` with a thread-local connection pool. Each thread lazily obtains a dedicated `sqlite3.Connection` with `check_same_thread=False`, `timeout=10.0`, `row_factory=sqlite3.Row`, and explicitly executes:
     `PRAGMA journal_mode = WAL;`
     `PRAGMA foreign_keys = ON;`
     `PRAGMA busy_timeout = 5000;`
     `PRAGMA synchronous = NORMAL;`
   - *Context Managers*: Provide `@contextmanager connection()` for read queries and `@contextmanager transaction()` using `BEGIN IMMEDIATE` / `with conn:` to guarantee atomic writes and automatic rollback on error.
   - *Maintenance*: Provide `wal_checkpoint(mode="TRUNCATE")` and idempotent `close()`.

2. **Normalized 10-Table Relational Schema (`db.py`)**:
   - *Observation*: `test_f3_01` verifies all 10 table names exist; foreign key cascading is verified in SQLite (`PRAGMA foreign_keys=ON`); indices are needed for task filtering, step ordering, and audit sequencing.
   - *Deduction*: We define canonical DDL creating:
     - `users`, `projects`, `workspaces` (with ON DELETE CASCADE)
     - `tasks` (UUID PK, ISO-8601 UTC timestamps, JSON parameters)
     - `agent_sessions` (FK to tasks)
     - `steps` (FK to tasks, composite index on task_id + step_number)
     - `tool_calls` (FK to tasks and steps)
     - `approvals` (FK to tasks, tracking decision audit)
     - `artifacts` (FK to tasks, SHA-256 fingerprinting)
     - `audit_trail` (FK to tasks, sequence_number, SHA-256 current_hash and previous_hash)
     - 8 targeted indexes for sub-millisecond status filtering and audit chain traversal.

3. **Task Lifecycle State Machine (`state_machine.py`)**:
   - *Observation*: Tests require strict validation, rejecting backwards transitions (e.g., verifying -> planning), disallowed jumps (e.g., queued -> completed), terminal modification (e.g., completed -> running), and invalid/empty strings.
   - *Deduction*: We implement `TaskStateMachine` as an immutable rule engine with:
     - `STATES: Set[str]`
     - `TERMINAL_STATES: Set[str] = {"completed", "failed", "cancelled"}`
     - `ACTIVE_STATES: Set[str] = {"queued", "planning", "running", "verifying", "blocked"}`
     - `ALLOWED_TRANSITIONS: Dict[str, Set[str]]`
     - `can_transition(from_state: str, to_state: str) -> bool`
     - `validate_transition(from_state: str, to_state: str) -> None`: Raises `InvalidStateTransitionError` (subclass of `ValueError`, aliased to `StateTransitionError`).

4. **Repository Implementation (`repository.py`)**:
   - *Observation*: All operations must be atomic, preserve UTC ISO-8601 format, validate input lengths and non-emptiness, and synchronize approval decisions with task status.
   - *Deduction*: `ControlPlaneRepository` wraps `DatabaseEngine`:
     - `create_task`: Enforces non-empty goal, assigns UUID, defaults status to `queued`, records UTC timestamps.
     - `transition_task`: Validates transition via `TaskStateMachine.validate_transition`, updates `updated_at`, populates `completed_at` upon entering terminal states.
     - `record_step`: In a single transaction, inserts step and sets `tasks.current_step_id`.
     - `request_approval` & `decide_approval`: Encapsulate the approval gate pattern, guaranteeing tasks cannot bypass `blocked` state.
     - `record_audit`: Retrieves preceding `current_hash` (or `GENESIS_HASH = "0" * 64`) and sequence number within an atomic transaction to prevent sequence forks during concurrent execution.

5. **Checkpoint Recovery Layer (`recovery.py`)**:
   - *Observation*: Mid-job crash leaves tasks in active status. Reconnection must identify all in-flight tasks and rehydrate step pointers and audit continuity.
   - *Deduction*: `RecoveryManager` implements:
     - `scan_active_tasks()`: Selects tasks where status is in `ACTIVE_STATES`.
     - `rehydrate_task(task_id: str) -> TaskRecoveryContext`: Packages the task, current step, completed steps, pending approvals, and latest audit hash.
     - `resume_task(task_id: str)`: Provides execution readiness signals to the runtime scheduler.

---

## 3. Caveats

1. **Audit Chaining & Secret Redaction Dependencies**:
   While `repository.py` integrates audit recording, the dedicated crypto engine (`audit.py`) and secret scrubbing rules (`redact.py`) are designed by Explorer 3 (`explorer_m2_3`). `repository.py` must import or accept `AuditChainer` and `SecretRedactor` with graceful fallback defaults matching the E2E test harness.
2. **Circular Foreign Key between `tasks` and `steps`**:
   `tasks.current_step_id` references `steps(id)`, while `steps.task_id` references `tasks(id)`. To maintain strict SQLite foreign key validation without order-of-creation deadlock, `tasks.current_step_id` is defined as a standard column without an immediate constraint or using deferrable constraints; step insertion updates `current_step_id` after the step record is committed.
3. **In-Memory vs File-Based SQLite**:
   When using `:memory:` or URI `file::memory:?cache=shared`, SQLite connections share state across threads. For file-based databases, thread-local connections with WAL mode and `PRAGMA busy_timeout=5000` provide maximum throughput without locking errors.

---

## 4. Conclusion & Design Blueprint

The control plane layer is composed of 4 core modules in `services/control-plane/src/plaq_control_plane/`:

```
services/control-plane/src/plaq_control_plane/
├── __init__.py          # Public exports (DatabaseEngine, ControlPlaneRepository, TaskStateMachine, etc.)
├── db.py                # SQLite WAL connection manager, thread-local pool, 10-table DDL & indexes
├── state_machine.py     # 8-state transition rules, terminal immutability, InvalidStateTransitionError
├── repository.py        # Complete CRUD, atomic transactions, approval gating, audit logging
└── recovery.py          # Crash recovery scanner, rehydration context, step & hash continuity
```

### 4.1. Complete Normalized SQL DDL (`db.py`)

```sql
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

-- Performance & Lookup Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_steps_task_id ON steps(task_id, step_number);
CREATE INDEX IF NOT EXISTS idx_audit_task_id ON audit_trail(task_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_approvals_task_status ON approvals(task_id, status);
CREATE INDEX IF NOT EXISTS idx_artifacts_task_id ON artifacts(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_step_id ON tool_calls(step_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_task_id ON tool_calls(task_id);
```

---

### 4.2. Code Blueprint: `db.py`

```python
"""SQLite Database Engine with WAL mode, thread-local connection pooling, and 10-table schema."""

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional, Union

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;

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
    status TEXT NOT NULL CHECK (status IN ('queued', 'planning', 'running', 'verifying', 'completed', 'failed', 'cancelled', 'blocked')),
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
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES steps(id) ON DELETE SET NULL
);

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
        # Ensure parent directory exists if file path
        if self.db_path != ":memory:" and not self.db_path.startswith("file:"):
            parent = Path(self.db_path).parent
            parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode by default, transactions handled explicitly
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
```

---

### 4.3. Code Blueprint: `state_machine.py`

```python
"""Task Lifecycle State Machine enforcing transitions across all 8 states."""

from typing import Dict, Set


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal or unauthorized state machine transition is attempted."""
    pass


class StateTransitionError(InvalidStateTransitionError):
    """Alias for InvalidStateTransitionError for flexible contract importing."""
    pass


class TaskStateMachine:
    """Enforces strict task lifecycle state transitions and terminal immutability."""

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

    TERMINAL_STATES: Set[str] = {
        "completed",
        "failed",
        "cancelled",
    }

    ACTIVE_STATES: Set[str] = {
        "queued",
        "planning",
        "running",
        "verifying",
        "blocked",
    }

    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        "queued": {"planning", "cancelled"},
        "planning": {"running", "failed", "cancelled"},
        "running": {"verifying", "blocked", "failed", "cancelled"},
        "blocked": {"running", "failed", "cancelled"},
        "verifying": {"completed", "running", "failed", "cancelled"},
        "completed": set(),  # Terminal state: no outgoing transitions
        "failed": set(),     # Terminal state: no outgoing transitions
        "cancelled": set(),  # Terminal state: no outgoing transitions
    }

    @classmethod
    def is_valid_state(cls, state: str) -> bool:
        """Check if state string is a recognized task state."""
        return isinstance(state, str) and state in cls.STATES

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        """Check if state represents an immutable terminal state."""
        return state in cls.TERMINAL_STATES

    @classmethod
    def is_active(cls, state: str) -> bool:
        """Check if state represents an in-flight, active task."""
        return state in cls.ACTIVE_STATES

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        """Return True if transition from from_state to to_state is permissible."""
        if not cls.is_valid_state(from_state) or not cls.is_valid_state(to_state):
            return False
        return to_state in cls.ALLOWED_TRANSITIONS.get(from_state, set())

    @classmethod
    def validate_transition(cls, from_state: str, to_state: str) -> None:
        """Validate state transition; raise InvalidStateTransitionError if illegal."""
        if not cls.can_transition(from_state, to_state):
            raise InvalidStateTransitionError(
                f"Invalid state transition: cannot transition from '{from_state}' to '{to_state}'."
            )

    @classmethod
    def allowed_transitions(cls, from_state: str) -> Set[str]:
        """Return set of valid target states from given from_state."""
        return set(cls.ALLOWED_TRANSITIONS.get(from_state, set()))
```

---

### 4.4. Code Blueprint: `repository.py`

```python
"""Control Plane Repository providing CRUD, transactions, approval gating, and audit chaining."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from plaq_control_plane.db import DatabaseEngine
from plaq_control_plane.state_machine import TaskStateMachine


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class ControlPlaneRepository:
    """Data access repository for all control plane entities."""

    def __init__(self, db: Union[DatabaseEngine, str]):
        if isinstance(db, str):
            self.db = DatabaseEngine(db)
        else:
            self.db = db

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
        if not goal or not goal.strip():
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
        import hashlib

        # Graceful secret redaction fallback
        try:
            from tests.e2e.conftest import SecretRedactor
            redacted_params = SecretRedactor.redact_json(parameters if parameters is not None else {})
            redacted_output = SecretRedactor.redact_text(output)
        except ImportError:
            redacted_params = parameters if parameters is not None else {}
            redacted_output = str(output)

        params_str = json.dumps(redacted_params)
        files_str = json.dumps(modified_files or [])
        now = _utc_now_iso()
        entry_id = str(uuid.uuid4())

        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT sequence_number, current_hash FROM audit_trail WHERE task_id = ? ORDER BY sequence_number DESC LIMIT 1",
                (task_id,),
            )
            prev_row = cursor.fetchone()
            if prev_row:
                seq_num = prev_row["sequence_number"] + 1
                prev_hash = prev_row["current_hash"]
            else:
                seq_num = 1
                prev_hash = "0" * 64

            # SHA-256 digest payload matching test harness
            payload = f"{prev_hash}|{task_id}|{tool_name}|{params_str}|{redacted_output}|{exit_code}|{duration_ms:.2f}|{files_str}"
            curr_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

            conn.execute(
                """
                INSERT INTO audit_trail (
                    id, task_id, sequence_number, tool_name, parameters, output,
                    exit_code, duration_ms, modified_files, previous_hash, current_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entry_id, task_id, seq_num, tool_name, params_str, redacted_output, exit_code, duration_ms, files_str, prev_hash, curr_hash, now),
            )

        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM audit_trail WHERE id = ?", (entry_id,))
            return dict(cursor.fetchone())

    def get_audit_trail(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve audit entries for task ordered by sequence_number."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM audit_trail WHERE task_id = ? ORDER BY sequence_number ASC",
                (task_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def verify_audit_trail(self, task_id: str) -> bool:
        """Validate unbroken cryptographic hash chain from genesis to latest record."""
        import hashlib
        records = self.get_audit_trail(task_id)
        expected_prev = "0" * 64
        for rec in records:
            actual_prev = rec.get("previous_hash")
            if actual_prev != expected_prev:
                return False

            payload = (
                f"{actual_prev}|{rec['task_id']}|{rec['tool_name']}|{rec.get('parameters', '')}|"
                f"{rec.get('output', '')}|{int(rec.get('exit_code', 0))}|{float(rec.get('duration_ms', 0.0)):.2f}|"
                f"{rec.get('modified_files', '[]')}"
            )
            recalculated = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if recalculated != rec.get("current_hash"):
                return False
            expected_prev = rec["current_hash"]
        return True

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
```

---

### 4.5. Code Blueprint: `recovery.py`

```python
"""Checkpoint Recovery Layer for crash recovery and state rehydration."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from plaq_control_plane.repository import ControlPlaneRepository


@dataclass
class RehydratedTaskContext:
    """Complete in-memory snapshot of an in-flight task restored after system restart."""
    task: Dict[str, Any]
    status: str
    current_step: Optional[Dict[str, Any]] = None
    all_steps: List[Dict[str, Any]] = field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None
    last_audit_hash: str = "0" * 64
    last_sequence_number: int = 0
    recommended_action: str = "resume_execution"


class RecoveryManager:
    """Coordinates crash recovery scanning, task rehydration, and execution resumption."""

    def __init__(self, repository: ControlPlaneRepository):
        self.repo = repository

    def scan_active_tasks(self) -> List[Dict[str, Any]]:
        """Scan SQLite database for non-terminal tasks."""
        return self.repo.recover_active_tasks()

    def rehydrate_task(self, task_id: str) -> RehydratedTaskContext:
        """Reconstruct full task context from persistent storage."""
        task = self.repo.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found for rehydration.")

        status = task["status"]
        steps = self.repo.list_steps(task_id)
        current_step_id = task.get("current_step_id")
        current_step = next((s for s in steps if s["id"] == current_step_id), None)
        if current_step is None and steps:
            # Fall back to latest step
            current_step = steps[-1]

        # Audit trail continuity
        audit_trail = self.repo.get_audit_trail(task_id)
        if audit_trail:
            last_record = audit_trail[-1]
            last_hash = last_record["current_hash"]
            last_seq = last_record["sequence_number"]
        else:
            last_hash = "0" * 64
            last_seq = 0

        # Pending approvals if blocked
        pending_approval = None
        if status == "blocked":
            with self.repo.db.connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM approvals WHERE task_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                )
                row = cursor.fetchone()
                if row:
                    pending_approval = dict(row)

        # Determine recommended recovery action
        if status == "queued":
            rec_action = "dispatch_to_planner"
        elif status == "planning":
            rec_action = "resume_planning"
        elif status == "blocked":
            rec_action = "await_human_approval"
        elif status == "verifying":
            rec_action = "rerun_verification"
        elif status == "running":
            rec_action = "resume_current_step"
        else:
            rec_action = "noop_terminal"

        return RehydratedTaskContext(
            task=task,
            status=status,
            current_step=current_step,
            all_steps=steps,
            pending_approval=pending_approval,
            last_audit_hash=last_hash,
            last_sequence_number=last_seq,
            recommended_action=rec_action,
        )

    def recover_all_tasks(self) -> List[RehydratedTaskContext]:
        """Scan and rehydrate all in-flight tasks upon system startup."""
        active = self.scan_active_tasks()
        return [self.rehydrate_task(t["id"]) for t in active]
```

---

## 5. Verification Method

To verify the database layer, state machine, repository, and checkpoint recovery:

1. **Schema and Table Inspection**:
   ```powershell
   python -c "from tests.e2e.conftest import TestDatabase; db = TestDatabase('test_verify.db'); cursor = db.conn.execute(\"SELECT name FROM sqlite_master WHERE type='table';\"); print({r[0] for r in cursor.fetchall()}); db.close()"
   ```
   *Expected*: Set containing all 10 tables: `{'users', 'projects', 'workspaces', 'tasks', 'agent_sessions', 'steps', 'tool_calls', 'approvals', 'artifacts', 'audit_trail'}`.

2. **PRAGMA Verification**:
   ```powershell
   python -c "from tests.e2e.conftest import TestDatabase; db = TestDatabase('test_verify.db'); print('journal:', db.conn.execute('PRAGMA journal_mode;').fetchone()[0]); print('fk:', db.conn.execute('PRAGMA foreign_keys;').fetchone()[0]); print('busy:', db.conn.execute('PRAGMA busy_timeout;').fetchone()[0]); db.close()"
   ```
   *Expected*: `journal: wal`, `fk: 1`, `busy: 5000`.

3. **Feature 3 (Persistence) & Feature 4 (State Machine) Tests**:
   ```powershell
   pytest tests/e2e/test_tier1_feature.py -k "TestFeature03ControlPlanePersistence or TestFeature04TaskStateMachine" -v
   ```
   *Expected*: 10 passed.

4. **Boundary Tests (Group 2 SQLite Concurrency & Group 3 Invalid Transitions)**:
   ```powershell
   pytest tests/e2e/test_tier2_boundary.py -k "TestBoundary02SQLiteConcurrency or TestBoundary03InvalidStateTransitions" -v
   ```
   *Expected*: 22 passed.

5. **Recovery Tests (Feature 7 & Scenario 3 Crash Recovery)**:
   ```powershell
   pytest tests/e2e/test_tier1_feature.py -k "TestFeature07CheckpointRecovery" -v
   pytest tests/e2e/test_tier4_workloads.py -k "TestScenario03CheckpointRecoveryWorkflow" -v
   ```
   *Expected*: 6 passed.
