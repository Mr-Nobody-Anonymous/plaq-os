# Architectural & Technical Stack Blueprint for Plaq-OS

**Author**: Explorer 3 (Architecture & Tech Stack Explorer)  
**Working Directory**: `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_survey_2`  
**Target Milestone**: Plaq-OS Full Architecture, Control Plane, Runtime, UI Workbench & E2E Testing Strategy  
**Status**: Complete  

---

## 1. Observation

### 1.1 Host Environment & Core Python Runtime
A direct probe of the system environment via PowerShell command execution revealed the following concrete runtime details:
- **Operating System**: Windows 10 (Build 10.0.26300, AMD64 architecture)
- **Python Runtime**: `Python 3.10.11 (tags/v3.10.11:7d4cc5a, Apr 5 2023, 00:38:17) [MSC v.1929 64 bit (AMD64)]`
- **Git Version**: `git version 2.49.0.windows.1`
- **SQLite Engine**: SQLite version `3.40.1` built into standard library `sqlite3` (`threadsafety: 1`). Supports WAL mode, JSON1 functions (`json_extract`, `json_array`, `json_object`), generated columns, CTEs, and foreign key constraints.

### 1.2 Installed Package Versions & Compatibility Audit
Direct execution of package introspection (`python -c "import <pkg>; ..."`):
- **FastAPI**: `0.109.0` (Starlette 0.35.x/0.36.x, fully compatible with async routing, WebSockets, and Pydantic v2).
- **Uvicorn**: `0.52.4` (High-performance ASGI server supporting WebSockets and HTTP/1.1).
- **Pydantic**: `2.13.5` (Pydantic v2). *Crucial finding*: Code must utilize Pydantic v2 syntax (`model_dump()`, `model_validate()`, `Field()`, `model_config = ConfigDict(...)`) rather than deprecated v1 methods (`.dict()`, `.parse_obj()`).
- **Click**: `8.4.2` & **Typer**: `0.27.0` (Both installed and available for building the unified `plaq` CLI).
- **Pytest**: `9.1.1` & **pytest-asyncio**: `0.23.3`. *Crucial finding*: Existing `pytest.ini` currently configures `addopts = -p no:asyncio`. Test runner architecture should run synchronous fixtures and utilize Starlette's `TestClient` or explicit `asyncio.run()` in tests to avoid test runner collisions.
- **HTTPX**: `0.27.2` (Modern async HTTP client with ASGI transport support for in-memory FastAPI testing).
- **Websockets**: `13.1` (Asynchronous WebSocket implementation).
- **Quantum Stack**:
  - `stim: 1.16.0` (Topological stabilizer circuit simulation and detector error modeling).
  - `pymatching: 2.4.0` (MWPM graph decoding).
  - `qiskit: 2.5.2` (Quantum circuit synthesis and transpilation).
  - `numpy: 2.2.6`, `scipy: 1.15.3`, `pandas: 2.3.3`, `matplotlib: 3.10.7`, `networkx: 3.1`.

### 1.3 Baseline Test Suite Execution
Execution of the existing test suite via `pytest` confirmed:
```text
tests\test_baselines.py ..                                               [  5%]
tests\test_circuits.py .........                                         [ 28%]
tests\test_cost_model.py ......                                          [ 44%]
tests\test_hardware.py ......                                            [ 60%]
tests\test_optimizer.py .....                                            [ 73%]
tests\test_search_algorithms.py .....                                    [ 86%]
tests\test_stim_bridge.py .....                                          [100%]
============================= 38 passed in 19.29s =============================
```
All 38 existing unit tests pass cleanly without modifications.

### 1.4 Existing Codebase Architecture & Limitations
- **Current Imports**: All test files in `tests/test_*.py` and CLI scripts (`main.py`, `benchmark.py`) import quantum modules as flat top-level modules (`from circuits import ...`, `from hardware import ...`, `from optimizer import ...`).
- **Current Server**: `server.py` implements a basic `http.server.HTTPServer` with `SimpleHTTPRequestHandler`. It does not support asynchronous execution, WebSocket streams, task persistence, or background agent loops.
- **Current UI**: `ui/index.html` (942 lines) contains a futuristic cyber-quantum visual theme (neon cyan `#00f0ff`, purple `#a855f7`, dark slate `#070a13`), but lacks the required 4-panel OS workbench layout, code editor, git diff inspector, agent loop monitor, terminal output, and approval modals.

---

## 2. Logic Chain

1. **Premise 1 (Zero Regression on 38 Tests)**: Requirement R1 mandates that all 38 existing unit tests must continue to pass cleanly within `engines/quantum/` while restructuring the repository into `apps/`, `packages/`, `services/`, `engines/quantum/`, and `shared/`.
2. **Inference 1 (Dual-Path Import & Backward-Compatibility Shims)**: If files are moved into `engines/quantum/src/plaq_quantum/`, tests and legacy scripts that invoke `from circuits import ...` would fail unless `engines/quantum/src/plaq_quantum` (or shim modules) are present in the Python module search path. Therefore, root-level and engine-level shim re-exports (`from plaq_quantum.circuits import *`) alongside `PYTHONPATH` configuration in `conftest.py` will guarantee 100% backward compatibility for existing tests while cleanly modularizing the package as `plaq-quantum`.
3. **Premise 2 (Durable Control Plane & Checkpoints)**: Requirement R2 mandates persistent SQLite state across server restarts, tracking tasks, agent sessions, steps, approvals, tool calls, and artifacts, with an append-only audit trail and checkpoint recovery.
4. **Inference 2 (WAL-Mode SQLite with Cryptographic Audit Log)**: Standard SQLite with `PRAGMA journal_mode = WAL` and `PRAGMA busy_timeout = 5000` allows concurrent non-blocking readers (FastAPI REST endpoints and WebSocket streamers) and reliable atomic writes from background agent tasks. Adding a SHA-256 cryptographic hash chain (`prev_hash` -> `entry_hash`) guarantees audit log tamper evidence.
5. **Premise 3 (Process Isolation & Sandbox Guardrails)**: Requirement R3 mandates sandboxed execution of tools (`terminal.run`, `tests.run`, `workspace.write`) with timeout control and approval gates.
6. **Inference 3 (Defense-in-Depth Sandbox)**: On Windows, malicious commands or recursive directory traversal must be prevented before invoking the OS. Using `pathlib.Path.resolve().is_relative_to(workspace_root)` prevents directory escape. Using `asyncio.create_subprocess_exec` (or `subprocess.Popen`) with process tree termination (`taskkill /F /T /PID` or job objects) prevents orphaned hung processes. Implementing Git worktrees (`.worktrees/<task_id>`) isolates file mutations until verified and approved.
7. **Premise 4 (FastAPI + Real-Time Streaming)**: Requirement R4 mandates REST and WebSocket/SSE streaming.
8. **Inference 4 (Centralized Pub/Sub Event Broadcaster)**: An in-memory asynchronous pub/sub broadcaster (`EventBroadcaster`) decoupling producers (agent runtime steps, sandbox tool outputs) from consumers (WebSocket clients, SSE streams) allows thread-safe event publishing and clean subscriber cleanup on disconnect.
9. **Premise 5 (OS-Like 4-Panel Workbench UI)**: Requirement R5 mandates an OS-like multi-panel interface.
10. **Inference 5 (Zero-Build ES-Module SPA)**: Building the workbench as a self-contained ES-module single-page application directly served by FastAPI eliminates Node.js/npm build prerequisites on Windows. It renders instantly, integrates with WebSockets for live streaming, and reuses the existing cyberpunk neon theme while implementing the exact 4-panel layout (Left Sidebar, Center Workspace, Right Inspector, Bottom Panel).

---

## 3. Caveats

1. **Windows Subprocess Tree Termination**: Under Windows, terminating a parent process via standard `proc.terminate()` does not kill spawned child processes (e.g. `pytest` spawning python workers). The sandbox manager must use `taskkill /F /T /PID <pid>` or `win32job` objects to ensure process trees are terminated upon timeout.
2. **SQLite Write Concurrency**: While SQLite WAL mode allows infinite concurrent readers, only one writer can hold the database write lock at any instant. All writes in the control plane must execute within short, immediate transactions (`BEGIN IMMEDIATE`) with a busy timeout of 5000ms.
3. **Pytest Asyncio Configuration**: Because `pytest.ini` has `addopts = -p no:asyncio`, running async tests must not rely on auto-asyncio discovery. Instead, fixtures and tests should use Starlette's `TestClient` (which manages its own loop synchronously) or use `asyncio.run()` in test bodies.
4. **Git Worktree Prerequisites**: Isolated git worktree execution requires the target workspace to be a valid Git repository with at least one commit. The sandbox manager must automatically run `git init` and an initial commit if an unversioned workspace directory is opened.

---

## 4. Conclusion & Concrete Architectural Specifications

### 4.1 Monorepo Structure & Package Layout

```text
plaq-os/
├── apps/
│   ├── api/                      # FastAPI application
│   │   ├── pyproject.toml
│   │   └── src/plaq_api/
│   │       ├── __init__.py
│   │       ├── main.py           # FastAPI app instance, CORS, routers
│   │       ├── deps.py           # Dependency injection (DB, EventBroadcaster)
│   │       ├── routers/
│   │       │   ├── health.py     # /api/v1/health
│   │       │   ├── workspaces.py # /api/v1/workspaces
│   │       │   ├── tasks.py      # /api/v1/tasks (CRUD, logs, cancel, resume)
│   │       │   ├── approvals.py  # /api/v1/approvals (list, decide)
│   │       │   ├── quantum.py    # /api/v1/quantum (optimize, baselines, etc.)
│   │       │   └── artifacts.py  # /api/v1/artifacts
│   │       ├── websockets/
│   │       │   ├── connection_manager.py
│   │       │   └── broadcaster.py # Async Pub/Sub event bus
│   │       └── static/           # Static mount for apps/workbench
│   ├── cli/                      # Unified `plaq` CLI
│   │   ├── pyproject.toml
│   │   └── src/plaq_cli/
│   │       ├── __init__.py
│   │       ├── main.py           # Typer/Click entrypoint
│   │       ├── commands/
│   │       │   ├── task.py       # plaq task create/list/status/logs/resume
│   │       │   ├── quantum.py    # plaq quantum compile/estimate/benchmark
│   │       │   ├── workspace.py  # plaq workspace open/status
│   │       │   └── serve.py      # plaq serve --port <port>
│   │       └── formatters.py     # Rich terminal & JSON formatters
│   └── workbench/                # Self-contained OS-like Web UI
│       ├── index.html            # 4-panel workbench SPA
│       ├── css/
│       │   ├── layout.css        # CSS Grid & 4-panel layout
│       │   └── theme.css         # Futuristic cyber-quantum aesthetics
│       ├── js/
│       │   ├── app.js            # Main UI state controller
│       │   ├── ws.js             # WebSocket client & reconnect logic
│       │   ├── components/
│       │   │   ├── sidebar.js    # Left: File tree, tasks, quantum catalog
│       │   │   ├── workspace.js  # Center: Code, Diff, Terminal, Charts
│       │   │   ├── inspector.js  # Right: Agent plan, tool stream, approvals
│       │   │   └── bottom.js     # Bottom: Test output, job timeline, logs
│       └── assets/               # Logos and icons
├── packages/
│   ├── contracts/                # Pure Pydantic v2 domain schemas
│   │   ├── pyproject.toml
│   │   └── src/plaq_contracts/
│   │       ├── __init__.py
│   │       ├── common.py         # Enums, timestamps, UUID helpers
│   │       ├── task.py           # Task, TaskCreate, TaskStatus, TaskLifecycle
│   │       ├── step.py           # PlanStep, StepStatus, PlanDefinition
│   │       ├── tool.py           # ToolDefinition, ToolRequest, ToolResult, PermissionTier
│   │       ├── approval.py       # ApprovalRequest, ApprovalDecision
│   │       ├── artifact.py       # ArtifactRecord, ArtifactType
│   │       ├── event.py          # PlatformEvent, EventType
│   │       └── quantum.py        # OptimizationRequest, BaselineRequest, ExperimentResult
│   └── sdk-python/               # Python client library
│       ├── pyproject.toml
│       └── src/plaq_sdk/
│           ├── __init__.py
│           ├── client.py         # REST & WebSocket client
│           └── local.py          # In-process direct execution client
├── services/
│   ├── control-plane/            # SQLite persistent state engine
│   │   ├── pyproject.toml
│   │   └── src/plaq_control_plane/
│   │       ├── __init__.py
│   │       ├── db.py             # SQLite connection manager, WAL, transactions
│   │       ├── schema.py         # Table DDL & indexes
│   │       ├── migrations.py     # Schema migration runner
│   │       ├── repository.py     # TaskRepo, StepRepo, ToolRepo, ArtifactRepo
│   │       ├── audit.py          # Cryptographic append-only audit logger
│   │       └── checkpoint.py     # Checkpoint serializer & recovery manager
│   ├── agent-runtime/            # Autonomous agent loop & tool dispatch
│   │   ├── pyproject.toml
│   │   └── src/plaq_agent_runtime/
│   │       ├── __init__.py
│   │       ├── loop.py           # Agent execution loop
│   │       ├── registry.py       # Typed tool registry
│   │       ├── permissions.py    # Tier gating & security policies
│   │       ├── approvals.py      # Approval barrier & callbacks
│   │       └── tools/            # Concrete tool providers
│   │           ├── workspace.py  # workspace.list, read, write, patch
│   │           ├── git.py        # git.diff, git.branch
│   │           ├── terminal.py   # terminal.run, tests.run
│   │           ├── quantum.py    # quantum.compile, estimate, simulate
│   │           └── artifact.py   # artifacts.publish
│   ├── sandbox-manager/          # Subprocess & in-memory isolation
│   │   ├── pyproject.toml
│   │   └── src/plaq_sandbox/
│   │       ├── __init__.py
│   │       ├── process.py        # Subprocess runner, timeout, tree-kill
│   │       ├── in_memory.py      # In-memory execution sandbox
│   │       ├── path_guard.py     # Path traversal prevention & cwd lock
│   │       ├── redactor.py       # Secret & token scrubber
│   │       └── worktree.py       # Isolated git worktrees manager
│   ├── model-gateway/            # LLM provider abstraction
│   │   ├── pyproject.toml
│   │   └── src/plaq_model_gateway/
│   │       ├── __init__.py
│   │       ├── base.py           # Abstract LLM provider interface
│   │       ├── mock_provider.py  # Deterministic replay provider
│   │       └── gemini_provider.py# Google Gemini API provider
│   └── artifact-service/         # Report, diff, and plot storage
│       ├── pyproject.toml
│       └── src/plaq_artifact_service/
│           ├── __init__.py
│           ├── store.py          # File storage & SHA-256 calculation
│           └── index.py          # Manifest indexing
├── engines/
│   └── quantum/                  # Domain-specific Quantum Co-Design Engine
│       ├── pyproject.toml
│       ├── src/plaq_quantum/
│       │   ├── __init__.py
│       │   ├── circuits.py
│       │   ├── hardware.py
│       │   ├── cost_model.py
│       │   ├── stim_bridge.py
│       │   ├── optimizer.py
│       │   ├── baselines.py
│       │   ├── search_algorithms.py
│       │   ├── benchmark.py
│       │   └── dashboard.py
│       └── tests/                # 38 passing unit tests
├── shared/
│   ├── schemas/                  # Shared JSON schemas
│   ├── policies/                 # Tool permission policies
│   └── prompts/                  # System prompts for agent planner
├── tests/                        # Monorepo integration & E2E tests (Tiers 1-4)
│   ├── conftest.py               # Shared test fixtures
│   ├── test_tier1_features.py    # >=5 tests per core feature
│   ├── test_tier2_boundaries.py  # >=5 tests per boundary/corner case
│   ├── test_tier3_matrices.py    # Pairwise combinatorial tests
│   └── test_tier4_workflows.py   # Multi-step real-world workflows
├── plaq_bootstrap.py             # Automatic PYTHONPATH & package resolver
├── pyproject.toml                # Monorepo root config
└── pytest.ini                    # Root pytest configuration
```

### 4.2 Python Package Resolution & Backward Compatibility Strategy
To ensure that existing code, external scripts, and all 38 tests can run seamlessly without requiring manual `pip install` commands in every subdirectory:
1. **Bootstrap Module (`plaq_bootstrap.py`)**:
   Injects all `src/` directories across `apps/`, `packages/`, `services/`, and `engines/` into `sys.path`. When imported in `tests/conftest.py`, `apps/api/src/plaq_api/main.py`, or `apps/cli/src/plaq_cli/main.py`, all internal monorepo packages are automatically resolvable.
2. **Root & Engine Shim Modules**:
   Root files `circuits.py`, `hardware.py`, `cost_model.py`, `optimizer.py`, `stim_bridge.py`, `baselines.py`, `search_algorithms.py`, and `benchmark.py` will re-export their contents directly from `plaq_quantum.*`. This ensures that any command (e.g. `python main.py --run-all` or `pytest`) continues to execute identically with 0% risk of import breakage.

---

### 4.3 SQLite Control Plane Database Schema & Checkpoint Engine

#### DDL Schema
```sql
-- Migration Version Tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workspaces
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT DEFAULT '{}'
);

-- Tasks & Lifecycle
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    goal TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued', 'planning', 'running', 'verifying', 'completed', 'failed', 'cancelled', 'blocked')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    checkpoint_json TEXT DEFAULT '{}',
    error_message TEXT,
    metadata_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id);

-- Agent Sessions
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'failed', 'paused')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    tokens_used INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}'
);

-- Plan Steps
CREATE TABLE IF NOT EXISTS plan_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    step_index INTEGER NOT NULL,
    description TEXT NOT NULL,
    acceptance_criteria TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'passed', 'failed', 'skipped')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    UNIQUE(task_id, step_index)
);
CREATE INDEX IF NOT EXISTS idx_steps_task ON plan_steps(task_id, step_index);

-- Tool Invocations
CREATE TABLE IF NOT EXISTS tool_invocations (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    step_id TEXT REFERENCES plan_steps(id) ON DELETE SET NULL,
    tool_name TEXT NOT NULL,
    permission_tier TEXT NOT NULL CHECK(permission_tier IN ('read', 'workspace_write', 'git', 'terminal', 'quantum', 'artifacts')),
    parameters_json TEXT NOT NULL,
    stdout TEXT,
    stderr TEXT,
    exit_code INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    modified_file_hashes_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tools_task ON tool_invocations(task_id);

-- Approvals (Human-in-the-Loop Barrier)
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    tool_name TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK(risk_level IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP,
    decided_by TEXT,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_pending ON approvals(status) WHERE status = 'pending';

-- Artifacts
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    artifact_type TEXT NOT NULL CHECK(artifact_type IN ('report', 'diff', 'plot', 'circuit', 'dataset', 'manifest')),
    file_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id);

-- Append-Only Cryptographic Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prev_hash TEXT,
    entry_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_log(task_id);
```

#### Checkpoint Serialization & Crash Recovery
1. **Atomic Checkpointing**: After every step execution or tool invocation, the runtime writes the task state to `checkpoint_json` within an immediate SQLite transaction:
   ```python
   def save_checkpoint(self, task_id: str, step_index: int, state: dict) -> None:
       payload = json.dumps({"current_step": step_index, "state": state, "timestamp": time.time()})
       with self.db.transaction():
           self.db.execute(
               "UPDATE tasks SET checkpoint_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
               (payload, task_id)
           )
   ```
2. **Reboot Crash Recovery**: When the backend server or CLI boots, the control plane queries all tasks in non-terminal states (`running`, `planning`, `verifying`):
   - If a pending approval exists in `approvals` table, the task is preserved in `blocked` state awaiting user input.
   - If no approval is pending, the task is marked `resumable`. The CLI command `plaq task resume <id>` loads the `checkpoint_json`, re-hydrates the agent context, and resumes execution starting exactly from `current_step`.

---

### 4.4 Sandbox Manager: Subprocess, In-Memory & Path Guard Architecture

#### 1. Path Traversal & File Boundary Protection (`PathGuard`)
- All requested filesystem operations must resolve absolute paths using `pathlib.Path(path).resolve()`.
- Validates: `target_path.is_relative_to(workspace_root)`. If false, immediately halts execution with `SecurityException: Path traversal outside workspace boundary`.
- Prevents reading/writing system directories (`C:\Windows`, `.ssh`, environment token files).

#### 2. Subprocess Execution Sandbox (`ProcessSandbox`)
- Runs terminal and test commands via `asyncio.create_subprocess_exec` or `subprocess.Popen` with `shell=False`.
- **Environment Sanitization**: Strips dangerous host variables (`AWS_*`, `GITHUB_TOKEN`, `AZURE_*`, `SECRET_*`), providing a clean minimal execution environment with explicit `PYTHONPATH` pointing to the workspace root.
- **Process Tree Kill on Windows**: When a command exceeds its timeout (default: 30s), kills the entire process tree using `subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)])` to eliminate lingering background processes.
- **Buffer Limiter**: Streams stdout/stderr with a maximum cap (5 MB) to protect against memory exhaustion.

#### 3. Token & Secret Redactor (`SecretRedactor`)
- Scans all stdout, stderr, and parameter payloads using regex filters matching API keys, bearer tokens, passwords, and private certificates before writing to the control plane database or broadcasting to WebSocket streams.

#### 4. Git Worktree Isolation (`WorktreeManager`)
- For modifications requiring git operations (`git.patch`, `workspace.write`), the manager provisions an isolated worktree under `.worktrees/<task_id>`.
- The agent works inside this isolated worktree, generating diffs via `git diff HEAD`. The user can review the diff cleanly in the Workbench UI before the changes are committed to the main branch.

---

### 4.5 FastAPI Backend & Asynchronous Event Broadcaster Architecture

#### REST API Endpoints
- **Health**: `GET /api/v1/health` (Reports uptime, active tasks, database latency, hardware models loaded).
- **Workspaces**:
  - `POST /api/v1/workspaces` (Initialize/register workspace).
  - `GET /api/v1/workspaces/{id}/tree` (Retrieve directory file tree).
- **Tasks**:
  - `POST /api/v1/tasks` (Submit new goal with acceptance criteria).
  - `GET /api/v1/tasks` (List tasks with filter by status).
  - `GET /api/v1/tasks/{id}` (Get task details, active step, checkpoints).
  - `GET /api/v1/tasks/{id}/logs` (Fetch consolidated tool execution logs).
  - `POST /api/v1/tasks/{id}/cancel` (Signal cancellation to agent runtime).
  - `POST /api/v1/tasks/{id}/resume` (Resume interrupted task from checkpoint).
- **Approvals**:
  - `GET /api/v1/approvals` (List pending approval requests).
  - `POST /api/v1/approvals/{id}/decide` (Approve or reject with reason).
- **Quantum Co-Design Engine**:
  - `GET /api/v1/quantum/metadata` (List 8 workloads, 4 hardware models, algorithms).
  - `POST /api/v1/quantum/optimize` (Execute Pareto multi-objective search).
  - `POST /api/v1/quantum/baselines` (Run Four-Baselines comparative protocol).
  - `POST /api/v1/quantum/ablation` (Run systematic layer ablation).
  - `POST /api/v1/quantum/search-bench` (Benchmark search algorithms).
- **Artifacts**:
  - `GET /api/v1/artifacts/{id}` (Download or preview artifact report/diff/plot).

#### Event Broadcaster Architecture
```python
class EventBroadcaster:
    """Async Pub/Sub event bus supporting WebSockets and SSE."""
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=500)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event: PlatformEvent) -> None:
        data = event.model_dump_json()
        async with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(data)
                except asyncio.QueueFull:
                    pass
```
- **WebSocket Route (`/ws/stream`)**: Provides a bidirectional channel. Pushes live step progress, tool execution logs, and approval requests to the Workbench UI; receives user approval decisions in real time.
- **SSE Route (`/api/v1/events/stream`)**: Provides unidirectional HTTP Server-Sent Events for browser event streams.

---

### 4.6 OS-Like 4-Panel Workbench Web Frontend Architecture

#### Layout Specification (CSS Grid)
```text
+----------------------------------------------------------------------------------------------------+
|  HEADER: [Logo] Plaq-OS Workbench | Workspace: /project | Active Task: #task-1 | Status: [CONNECTED] |
+------------------------+---------------------------------------------------+-----------------------+
| LEFT SIDEBAR (240px)   | CENTER WORKSPACE (Flex 1)                         | RIGHT INSPECTOR (320px)|
|                        | [ Tabs: Code | Diff | Terminal | Quantum Pareto ] |                       |
| 1. File Tree           | +-----------------------------------------------+ | 1. Agent Plan Steps   |
|    - src/              | | Active Viewport:                              | |    [x] 1. Inspect     |
|    - tests/            | |                                               | |    [x] 2. Run tests   |
|    - circuits.py       | |  - Code Editor with syntax highlighting       | |    [ ] 3. Synthesize  |
| 2. Task Queue          | |  - Interactive Terminal stream                | | 2. Tool Execution   |
|    - #task-1 (Running) | |  - Side-by-side Git Diff inspector            | |    - terminal.run   |
|    - #task-2 (Queued)  | |  - Interactive Canvas/SVG Pareto trade-off   | |    - Duration: 142ms|
| 3. Quantum Lab Presets | |    scatter plot with hover tooltips           | | 3. Approval Modal   |
|    - FeMoCo Chemistry  | |                                               | |    [APPROVE][REJECT]|
|    - Shor RSA 7q       | +-----------------------------------------------+ | 4. Resource Counters  |
+------------------------+---------------------------------------------------+-----------------------+
| BOTTOM PANEL (Collapsible, 220px)                                                                   |
| [ Tabs: Test Runner Console | Job Timeline | Audit & System Event Log ]                            |
| Running 38 test items... 38 passed in 19.29s.                                                      |
+----------------------------------------------------------------------------------------------------+
```

#### Key Implementation Details
- **Zero Build Dependency**: Written in clean, modern vanilla JavaScript using ES modules (`type="module"`), CSS Grid, and Flexbox. Works out of the box without requiring `node`, `npm`, or Vite bundlers.
- **Cyber-Quantum Aesthetic**: Inherits the neon cyan (`#00f0ff`), deep purple (`#a855f7`), and dark slate background (`#070a13`, `#0d1527`) established in `ui/index.html`.
- **Integrated Interactive Visualizations**:
  - Center panel Pareto visualization utilizes HTML5 Canvas / SVG rendering with hover tooltip inspect, metric toggle (Qubits vs Runtime vs Failure Probability), and baseline overlay comparisons.
  - Interactive terminal component streams live stdout/stderr from `terminal.run` and `tests.run` tools with color-coded ANSI escape parsing.
- **Approval Modal Component**: Displays tool name, arguments, risk rating (e.g. `HIGH: Modifying production files`), and provides instant `Approve` or `Reject` buttons that transmit decisions via WebSocket to `/ws/stream`.

---

### 4.7 Comprehensive E2E Testing Strategy (Tiers 1–4)

To guarantee software reliability, the E2E test infrastructure must be organized into four distinct verification tiers:

```text
tests/
├── conftest.py                   # Reusable fixtures (db, workspace, client, sandbox)
├── test_tier1_features.py        # Tier 1: Core feature coverage (>=5 tests per feature)
├── test_tier2_boundaries.py      # Tier 2: Boundary & corner cases (>=5 tests per feature)
├── test_tier3_matrices.py        # Tier 3: Pairwise combinations
└── test_tier4_workflows.py       # Tier 4: Real-world multi-step workflows
```

#### Tier 1: Feature Coverage (>=5 Tests per Core Feature)
- **Feature 1: Unified CLI (`plaq`)**
  1. `test_cli_task_create_and_list`: `plaq task create "Goal"` creates task and shows in `plaq task list`.
  2. `test_cli_task_status_and_logs`: `plaq task status <id>` and `plaq task logs <id>` output formatted JSON/table.
  3. `test_cli_quantum_compile`: `plaq quantum compile --workload test_rz_cx_5q` outputs transpiled stats.
  4. `test_cli_quantum_estimate`: `plaq quantum estimate --workload qaoa_cycle_6q --hardware superconducting` returns fault-tolerant metrics.
  5. `test_cli_workspace_open`: `plaq workspace open <path>` registers workspace and returns valid status.
- **Feature 2: REST API Backend**
  1. `test_api_health_check`: `GET /api/v1/health` returns status `ok`, database connected, and loaded hardware models.
  2. `test_api_task_crud_lifecycle`: Create, read, update, list, and cancel task via `/api/v1/tasks`.
  3. `test_api_approvals_workflow`: Fetch pending approvals and submit decision via `/api/v1/approvals/{id}/decide`.
  4. `test_api_quantum_optimize`: `POST /api/v1/quantum/optimize` returns valid Pareto frontier execution plans.
  5. `test_api_artifacts_download`: `GET /api/v1/artifacts/{id}` returns correct binary/text payload and SHA-256 header.
- **Feature 3: WebSocket & SSE Event Streaming**
  1. `test_ws_connection_and_handshake`: Client connects to `/ws/stream` and receives welcome event.
  2. `test_ws_broadcast_step_transitions`: EventBroadcaster emits `step_started` and `step_completed` to all connected clients.
  3. `test_ws_tool_log_streaming`: Tool stdout chunks are streamed in real time to WebSocket subscribers.
  4. `test_ws_approval_request_push`: Pending approval triggers immediate push notification on WebSocket.
  5. `test_sse_event_stream`: `GET /api/v1/events/stream` yields valid `text/event-stream` formatted messages.
- **Feature 4: Control Plane & Persistence**
  1. `test_db_migration_initialization`: Schema migrations apply cleanly from clean database state.
  2. `test_db_task_state_transitions`: Task moves through `queued` -> `planning` -> `running` -> `verifying` -> `completed`.
  3. `test_db_tool_invocation_audit`: Every tool execution is recorded with parameters, exit code, duration, and hashes.
  4. `test_db_checkpoint_serialization`: Serializes and deserializes agent memory and step progress.
  5. `test_db_cryptographic_audit_chain`: Tampering with an audit log record breaks SHA-256 verification chain.
- **Feature 5: Agent Runtime & Typed Tool Registry**
  1. `test_tool_registry_permission_tiers`: Verifies read-only, workspace-write, git, terminal, and quantum tier restrictions.
  2. `test_tool_workspace_read_and_list`: Lists directory files and reads contents safely.
  3. `test_tool_terminal_execution`: Runs sandboxed command and captures exit code and output.
  4. `test_tool_quantum_simulation`: Executes Stim stabilizer simulation and returns empirical logical error rate.
  5. `test_tool_artifacts_publish`: Writes verified report and publishes artifact record in database.
- **Feature 6: Quantum Engine Modularization**
  1. `test_quantum_all_38_tests_pass`: All existing 38 unit tests pass in `engines/quantum/`.
  2. `test_quantum_workload_generation`: Verifies all 8 workloads from `circuits.py` generate valid circuits.
  3. `test_quantum_hardware_models`: Verifies all 4 hardware models from `hardware.py` provide coupling graphs.
  4. `test_quantum_cost_model_estimation`: Evaluates fault-tolerant T-count, code distance, and physical qubits.
  5. `test_quantum_pareto_optimizer`: Confirms compilation caching and non-dominated Pareto extraction.

#### Tier 2: Boundary & Corner Conditions (>=5 Tests per Feature)
- **Boundary 1: Path Traversal & Filesystem Escapes**
  1. `test_path_traversal_relative_parent`: `../../windows/system32` is blocked.
  2. `test_path_traversal_absolute_escape`: Direct access to `C:\Windows` is denied.
  3. `test_path_traversal_symlink_escape`: Symlinks pointing outside workspace root raise `SecurityException`.
  4. `test_path_traversal_encoded_dots`: URL-encoded or backslash permutations `..%2f..` are neutralized.
  5. `test_path_traversal_hidden_files`: Attempts to read `.git/config` or `.env` without permissions are rejected.
- **Boundary 2: Sandbox Process Execution & Timeouts**
  1. `test_sandbox_timeout_infinite_loop`: Subprocess running `while True: pass` is forcefully killed at timeout.
  2. `test_sandbox_orphan_process_cleanup`: Child processes spawned by child processes are cleanly terminated.
  3. `test_sandbox_large_output_truncation`: Command emitting 20MB of text is truncated at buffer limit without OOM.
  4. `test_sandbox_nonzero_exit_code`: Failing bash/cmd command reports accurate exit code and stderr.
  5. `test_sandbox_environment_sanitization`: Verifies `AWS_ACCESS_KEY_ID` or host secrets are scrubbed from subshell.
- **Boundary 3: Database Concurrency & Locks**
  1. `test_db_concurrent_readers_and_writer`: 10 threads reading while 1 thread writes under WAL mode without locking.
  2. `test_db_busy_timeout_retry`: Concurrent write conflict waits for busy timeout rather than failing immediately.
  3. `test_db_transaction_rollback_on_error`: Failed multi-statement transaction cleanly rolls back.
  4. `test_db_corrupted_checkpoint_recovery`: Malformed JSON in `checkpoint_json` defaults safely to recovery mode.
  5. `test_db_foreign_key_enforcement`: Deleting a workspace cascades or restricts tasks properly under FK constraints.
- **Boundary 4: API & Input Validation Corner Cases**
  1. `test_api_invalid_json_payload`: Malformed body returns standard HTTP 422 with descriptive error.
  2. `test_api_nonexistent_task_id`: `GET /api/v1/tasks/invalid-uuid` returns HTTP 404.
  3. `test_api_duplicate_workspace_root`: Registering an existing root returns idempotent or 409 response.
  4. `test_api_double_approval_decision`: Deciding on an already approved/rejected task returns HTTP 400.
  5. `test_api_ws_client_abrupt_disconnect`: Client socket dropped mid-stream does not crash backend broadcaster.
- **Boundary 5: Secret Redaction & Log Security**
  1. `test_redactor_openai_key`: `sk-abc123456789...` is redacted to `[REDACTED_API_KEY]`.
  2. `test_redactor_github_pat`: `ghp_123456789...` is masked.
  3. `test_redactor_jwt_token`: Bearer tokens in headers/stdout are sanitized.
  4. `test_redactor_password_flags`: `--password secret123` is scrubbed from logged command parameters.
  5. `test_redactor_private_key`: `-----BEGIN RSA PRIVATE KEY-----` blocks are redacted.

#### Tier 3: Pairwise Combinations
- **Matrix 1: Quantum Co-Design Combinatorial Grid**
  - Workloads: `test_rz_cx_5q`, `qaoa_cycle_6q`, `bv_oracle_6q`, `chemistry_femoco_6q` (4)
  - Hardware Models: `superconducting`, `trapped_ion`, `neutral_atom`, `qldpc` (4)
  - Search Algorithms: `Exhaustive Grid`, `Greedy Coordinate`, `Simulated Annealing`, `Random Search` (4)
  - *Verification*: Evaluates 16 pairwise configurations verifying cost estimation convergence and stability.
- **Matrix 2: Task Lifecycle x Approval Decisions x Network Status**
  - Task States: `queued`, `planning`, `running`, `verifying`
  - Approval Decisions: `approved`, `rejected`, `timeout`
  - Client States: `connected`, `reconnecting`, `disconnected`
- **Matrix 3: Sandbox Mode x Worktree Isolation**
  - Execution Target: `in_memory` vs `subprocess`
  - Workspace Context: `main_branch` vs `isolated_worktree`

#### Tier 4: Real-World Workflows
- **Workflow 1: Autonomous Quantum Benchmark & Artifact Generation**
  1. User issues `plaq task create "Transpile and benchmark chemistry_femoco_6q on superconducting hardware and publish executive report"`.
  2. Agent inspects workspace files using `workspace.list`.
  3. Agent plans 4 steps: (1) Transpile circuit, (2) Evaluate cost model, (3) Verify 38 tests, (4) Publish artifact.
  4. Executes `quantum.compile` and `quantum.estimate` in sandbox.
  5. Executes `tests.run` in sandbox to verify zero regressions.
  6. Writes report and plots via `artifacts.publish`.
  7. Verifies artifact checksums and transitions task to `completed`.
- **Workflow 2: Human-in-the-Loop Dangerous Operation Gate**
  1. Agent proposes modifying a critical configuration or executing a destructive shell command.
  2. Tool registry detects high-risk permission tier; halts execution and sets task status to `blocked`.
  3. Approval request is created in SQLite and pushed via WebSocket to Workbench UI.
  4. Simulated operator submits `approve` decision via REST API `/api/v1/approvals/{id}/decide`.
  5. Agent runtime receives approval event, resumes execution, executes tool in isolated worktree, and records execution audit trail.
- **Workflow 3: Crash Recovery & Checkpoint Resumption**
  1. Multi-step optimization task runs.
  2. Completes Step 1 and Step 2; writes checkpoint state into `tasks.checkpoint_json`.
  3. Abrupt simulation of server shutdown (ASGI app teardown / process kill).
  4. Fresh server instance starts up and initializes Control Plane.
  5. Detects in-flight task in `running` state; validates checkpoint integrity.
  6. User calls `plaq task resume <id>`; agent runtime recovers active session, skips Steps 1-2, and executes Step 3 to completion.

---

### 4.8 Pytest Test Runner & Fixtures Architecture

In `tests/conftest.py`:
```python
import os
import sys
import pytest
import sqlite3
import tempfile
import pathlib
from starlette.testclient import TestClient

# Ensure all monorepo source packages are in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "engines" / "quantum" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "sdk-python" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "control-plane" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "sandbox-manager" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "agent-runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "cli" / "src"))


@pytest.fixture
def temp_workspace(tmp_path):
    """Creates an isolated git repository workspace for sandboxed tool testing."""
    import subprocess
    ws = tmp_path / "workspace"
    ws.mkdir()
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@plaq.os"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "Plaq Tester"], cwd=ws, check=True)
    test_file = ws / "README.md"
    test_file.write_text("# Test Workspace\n")
    subprocess.run(["git", "add", "."], cwd=ws, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=ws, check=True)
    return ws


@pytest.fixture
def in_memory_db():
    """Initializes a clean SQLite control plane with full migrations applied."""
    from plaq_control_plane.db import DatabaseManager
    from plaq_control_plane.migrations import run_migrations
    db = DatabaseManager(":memory:")
    run_migrations(db)
    return db


@pytest.fixture
def api_test_client(in_memory_db, temp_workspace):
    """Provides a synchronous Starlette TestClient with mocked dependencies."""
    from plaq_api.main import create_app
    app = create_app(db=in_memory_db, default_workspace=temp_workspace)
    return TestClient(app)
```

---

## 5. Verification Method

To independently verify all findings and architectural specifications:

1. **Verify Python & Package Versions**:
   ```powershell
   python -c "import fastapi, uvicorn, pydantic, sqlite3, click, typer, pytest, stim, pymatching, qiskit; print('All required packages import cleanly')"
   ```
2. **Verify Existing 38 Tests**:
   ```powershell
   pytest
   ```
   *Expected output*: `38 passed in ~19.3s`.
3. **Verify SQLite Engine Capabilities**:
   ```powershell
   python -c "import sqlite3; con = sqlite3.connect(':memory:'); con.execute('PRAGMA journal_mode = WAL'); cur = con.cursor(); cur.execute('SELECT json_extract(?, ?)', ['{\"status\": \"ok\"}', '$.status']); assert cur.fetchone()[0] == 'ok'; print('SQLite WAL & JSON1 verified')"
   ```
4. **Invalidation Conditions**:
   - Any modification that causes existing tests in `tests/test_*.py` to fail or import errors to occur.
   - Any dependency on Node.js/npm for serving the Workbench UI.
   - Any failure of process tree cleanup on Windows during task timeout.
