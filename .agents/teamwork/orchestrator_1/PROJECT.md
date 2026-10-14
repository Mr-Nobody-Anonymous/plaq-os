# Project: Plaq-OS

## Architecture
Plaq-OS is a programmable, agent-driven quantum computing workbench and OS-like execution platform. It unifies:
1. **User Applications (`apps/`)**:
   - `apps/api`: FastAPI backend providing REST endpoints, OpenAPI 3.1 documentation, and real-time bidirectional WebSocket / SSE event streaming.
   - `apps/cli`: Unified `plaq` CLI entrypoint supporting task management, quantum co-design benchmarks, workspace management, and local server launch.
   - `apps/workbench`: Zero-build ES-module single-page desktop/web interface delivering an OS-like 4-panel workbench (Left Sidebar, Center Workspace, Right Inspector, Bottom Panel) with cyber-quantum aesthetics.
2. **Reusable Packages (`packages/`)**:
   - `packages/contracts`: Pydantic v2 schemas defining domain models for tasks, steps, tool calls, approvals, artifacts, events, and quantum requests.
   - `packages/sdk-python`: High-level Python client library for interacting with Plaq-OS locally or via HTTP/WebSocket.
3. **Core Platform Services (`services/`)**:
   - `services/control-plane`: SQLite WAL-backed state engine tracking users, projects, workspaces, tasks, agent sessions, steps, approvals, artifacts, and tamper-evident append-only audit trail with secret redaction and crash checkpoint recovery.
   - `services/agent-runtime`: 7-stage deterministic agent execution loop (`Receive Task -> Inspect Context -> Plan & Define Criteria -> Execute Tool -> Collect Output -> Verify -> Review Diff & Deliver`), 6-tier typed tool registry, and human approval gates.
   - `services/sandbox-manager`: Process execution sandbox with Windows process-tree termination, execution timeouts, PathGuard workspace path traversal confinement, and isolated git worktrees.
   - `services/model-gateway`: Provider abstraction layer supporting rule-based/mock and LLM providers.
   - `services/artifact-service`: Storage and retrieval of diffs, benchmark reports, and manifests with SHA-256 fingerprinting.
4. **Quantum Co-Design Engine (`engines/quantum/`)**:
   - `src/plaq_quantum/`: Analytical fault-tolerant cost models, Ross-Selinger T-gate synthesis, surface code distance solver, Stim rotated surface code simulation, PyMatching MWPM decoding, hardware topologies, Pareto optimization, and baselines.
   - `tests/`: 38 unit tests validating the quantum engine.
5. **Shared Configuration & Policies (`shared/`)**:
   - `schemas/`: Canonical JSON schemas.
   - `policies/`: Tool permission definitions and security constraints.
   - `prompts/`: Agent prompt templates.

## Code Layout
```text
C:\Users\hp\Desktop\plaq-os/
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   └── src/plaq_api/
│   │       ├── __init__.py
│   │       ├── main.py
│   │       ├── deps.py
│   │       ├── broadcaster.py
│   │       └── routers/
│   │           ├── health.py
│   │           ├── workspaces.py
│   │           ├── tasks.py
│   │           ├── approvals.py
│   │           ├── quantum.py
│   │           └── artifacts.py
│   ├── cli/
│   │   ├── pyproject.toml
│   │   └── src/plaq_cli/
│   │       ├── __init__.py
│   │       ├── main.py
│   │       ├── commands/
│   │       │   ├── task.py
│   │       │   ├── quantum.py
│   │       │   ├── workspace.py
│   │       │   └── serve.py
│   │       └── formatters.py
│   └── workbench/
│       ├── index.html
│       ├── css/
│       │   ├── layout.css
│       │   └── theme.css
│       ├── js/
│       │   ├── app.js
│       │   ├── ws.js
│       │   └── components/
│       │       ├── sidebar.js
│       │       ├── workspace.js
│       │       ├── inspector.js
│       │       └── bottom.js
│       └── assets/
├── packages/
│   ├── contracts/
│   │   ├── pyproject.toml
│   │   └── src/plaq_contracts/
│   │       ├── __init__.py
│   │       ├── common.py
│   │       ├── task.py
│   │       ├── step.py
│   │       ├── tool.py
│   │       ├── approval.py
│   │       ├── artifact.py
│   │       ├── event.py
│   │       └── quantum.py
│   └── sdk-python/
│       ├── pyproject.toml
│       └── src/plaq_sdk/
│           ├── __init__.py
│           ├── client.py
│           └── models.py
├── services/
│   ├── control-plane/
│   │   ├── pyproject.toml
│   │   └── src/plaq_control_plane/
│   │       ├── __init__.py
│   │       ├── db.py
│   │       ├── models.py
│   │       ├── repository.py
│   │       ├── state_machine.py
│   │       ├── audit.py
│   │       └── recovery.py
│   ├── sandbox-manager/
│   │   ├── pyproject.toml
│   │   └── src/plaq_sandbox/
│   │       ├── __init__.py
│   │       ├── guard.py
│   │       ├── runner.py
│   │       └── worktree.py
│   ├── model-gateway/
│   │   ├── pyproject.toml
│   │   └── src/plaq_model_gateway/
│   │       ├── __init__.py
│   │       ├── gateway.py
│   │       └── providers.py
│   ├── agent-runtime/
│   │   ├── pyproject.toml
│   │   └── src/plaq_agent_runtime/
│   │       ├── __init__.py
│   │       ├── loop.py
│   │       ├── registry.py
│   │       ├── tools/
│   │       │   ├── workspace_tools.py
│   │       │   ├── git_tools.py
│   │       │   ├── terminal_tools.py
│   │       │   ├── quantum_tools.py
│   │       │   └── artifact_tools.py
│   │       └── approvals.py
│   └── artifact-service/
│       ├── pyproject.toml
│       └── src/plaq_artifacts/
│           ├── __init__.py
│           └── service.py
├── engines/
│   └── quantum/
│       ├── pyproject.toml
│       ├── src/
│       │   └── plaq_quantum/
│       │       ├── __init__.py
│       │       ├── circuits.py
│       │       ├── hardware.py
│       │       ├── cost_model.py
│       │       ├── stim_bridge.py
│       │       ├── optimizer.py
│       │       ├── baselines.py
│       │       ├── search_algorithms.py
│       │       └── benchmark.py
│       └── tests/
│           ├── conftest.py
│           ├── test_baselines.py
│           ├── test_circuits.py
│           ├── test_cost_model.py
│           ├── test_hardware.py
│           ├── test_optimizer.py
│           ├── test_search_algorithms.py
│           └── test_stim_bridge.py
├── shared/
│   ├── schemas/
│   ├── policies/
│   └── prompts/
├── tests/
│   ├── e2e/
│   │   ├── conftest.py
│   │   ├── test_tier1_feature.py
│   │   ├── test_tier2_boundary.py
│   │   ├── test_tier3_pairwise.py
│   │   └── test_tier4_workloads.py
│   └── legacy/ (root backward-compatible shims)
└── plaq_bootstrap.py
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Monorepo Structure | Top-level partitioning into `apps/`, `packages/`, `services/`, `engines/`, `shared/` | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Quantum Modularization | Modular `plaq_quantum` package in `engines/quantum/src/` | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Test Suite Preservation | All 38 existing unit tests pass cleanly inside `engines/quantum/tests/` and at root | M1 | ORIGINAL_REQUEST §R1, tests/ |
| 4 | Backward Compatibility Shims | Root import proxies allowing `from circuits import ...` to work transparently | M1 | Survey Discovery |
| 5 | Contracts Data Models | Pydantic v2 schemas for tasks, steps, tools, approvals, artifacts, and events | M2 | ORIGINAL_REQUEST §R1, R2 |
| 6 | SQLite Control Plane Schema | 9-table relational schema with foreign keys and WAL mode | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Task Lifecycle State Machine | Strict transition enforcement (`queued` -> `planning` -> `running` -> `verifying` -> `completed`/`failed`/`cancelled`/`blocked`) | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Append-Only Audit Trail | Chained logging of every tool invocation with exit codes and modified file hashes | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Secret Redaction Filter | Scrubbing sensitive tokens, credentials, and keys from logged params and outputs | M2 | ORIGINAL_REQUEST §R2, AC |
| 10 | Checkpoint Recovery | Automatic state rehydration and resumption of in-flight tasks upon restart | M2 | ORIGINAL_REQUEST §R2 |
| 11 | Artifact Service | File hashing, artifact metadata tracking, diff storage, and publication | M2 | ORIGINAL_REQUEST §R1, R3 |
| 12 | Python SDK Client | `packages/sdk-python` local and remote client interface | M2 | ORIGINAL_REQUEST §R1 |
| 13 | PathGuard Confinement | Canonical path resolution preventing workspace directory escape | M3 | ORIGINAL_REQUEST §R3 |
| 14 | Subprocess Sandbox Runner | Process execution with strict timeouts and Windows process-tree termination | M3 | ORIGINAL_REQUEST §R3 |
| 15 | Git Worktree Isolation | Isolated `.worktrees/<task_id>` execution for file mutations | M3 | ORIGINAL_REQUEST §R3 |
| 16 | Model Gateway | Provider abstraction supporting deterministic mock and live LLM providers | M3 | ORIGINAL_REQUEST §R1, R3 |
| 17 | Agent Execution Loop | 7-stage deterministic loop: Receive -> Inspect -> Plan -> Execute -> Collect -> Verify -> Review | M3 | ORIGINAL_REQUEST §R3 |
| 18 | Typed Tool Registry | 6-tier tool registry (`workspace.*`, `git.*`, `terminal.run`, `tests.run`, `quantum.*`, `artifacts.publish`) | M3 | ORIGINAL_REQUEST §R3 |
| 19 | Human Approval Gates | Execution pause and modal prompt for destructive/privileged actions | M3 | ORIGINAL_REQUEST §R3 |
| 20 | FastAPI Backend Application | REST API with health, workspace, task, approval, quantum, and artifact endpoints | M4 | ORIGINAL_REQUEST §R4 |
| 21 | Event Broadcaster Pub/Sub | Async event broadcaster supporting multi-client WebSocket and SSE streaming | M4 | ORIGINAL_REQUEST §R4 |
| 22 | Unified CLI Entrypoint | `plaq` executable with task, quantum, workspace, and serve command groups | M4 | ORIGINAL_REQUEST §R4 |
| 23 | CLI Task Management | `plaq task create/list/status/logs/resume` | M4 | ORIGINAL_REQUEST §R4 |
| 24 | CLI Quantum Commands | `plaq quantum compile/estimate/benchmark` | M4 | ORIGINAL_REQUEST §R4 |
| 25 | CLI Workspace & Server | `plaq workspace open` and `plaq serve --port` | M4 | ORIGINAL_REQUEST §R4 |
| 26 | Workbench Left Sidebar | Workspace file tree, agent session monitor, task queue, and quantum experiment catalog | M5 | ORIGINAL_REQUEST §R5 |
| 27 | Workbench Center Workspace | Tabbed viewer with code editor, git diff inspector, terminal log, and interactive Pareto canvas | M5 | ORIGINAL_REQUEST §R5 |
| 28 | Workbench Right Inspector | Active agent plan checklist, live tool execution stream, resource counters, and approval prompt modals | M5 | ORIGINAL_REQUEST §R5 |
| 29 | Workbench Bottom Panel | Collapsible panels for test runner output, job timelines, and system event logs | M5 | ORIGINAL_REQUEST §R5 |
| 30 | Workbench Real-time Sync | Live WebSocket updates for task states, tool invocations, and approval decisions | M5 | ORIGINAL_REQUEST §R5 |
| 31 | E2E Test Suite - Tier 1 | Feature coverage (>=5 tests per major feature area) | M6 / E2E Track | ORIGINAL_REQUEST AC |
| 32 | E2E Test Suite - Tier 2 | Boundary and corner cases (>=5 tests per boundary condition) | M6 / E2E Track | ORIGINAL_REQUEST AC |
| 33 | E2E Test Suite - Tier 3 | Cross-feature pairwise combinations | M6 / E2E Track | ORIGINAL_REQUEST AC |
| 34 | E2E Test Suite - Tier 4 | Real-world application scenarios and end-to-end user workflows | M6 / E2E Track | ORIGINAL_REQUEST AC |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Monorepo Architecture & Quantum Modularization | Features 1, 2, 3, 4: Reorganize repository into `apps/`, `packages/`, `services/`, `engines/quantum/`, `shared/`; create `engines/quantum/src/plaq_quantum/` and `engines/quantum/tests/`; establish bootstrap import hooks and root compatibility shims; verify 100% of 38 existing tests pass cleanly; remediate optimizer failure handling and canonical caching (60/60 tests pass). | none | DONE |
| M2 | Shared Contracts & Control Plane Persistence | Features 5, 6, 7, 8, 9, 10, 11, 12: Build `packages/contracts`, `packages/sdk-python`, `services/control-plane` (SQLite engine, WAL mode, models, migrations, 8-state task state machine, append-only chained audit log, secret redaction, checkpoint recovery), and `services/artifact-service`. | M1 | PLANNED |
| M3 | Sandbox Manager & Agent Runtime Engine | Features 13, 14, 15, 16, 17, 18, 19: Build `services/sandbox-manager` (PathGuard, process runner with timeout and Windows tree-kill, git worktrees), `services/model-gateway`, and `services/agent-runtime` (7-stage execution loop, 6-tier typed tool registry, human approval gates). | M1, M2 | PLANNED |
| M4 | Unified CLI & FastAPI Backend Application | Features 20, 21, 22, 23, 24, 25: Build `apps/api` (FastAPI REST endpoints, OpenAPI 3.1, async EventBroadcaster, WebSocket `/ws/stream`, SSE `/api/v1/events/stream`) and `apps/cli` (`plaq` CLI entrypoint with task, quantum, workspace, and serve commands). | M1, M2, M3 | PLANNED |
| M5 | Plaq Workbench Desktop/Web Interface | Features 26, 27, 28, 29, 30: Build `apps/workbench` OS-like 4-panel SPA (Left Sidebar, Center Workspace, Right Inspector, Bottom Panel) with cyber-quantum theme, Chart.js / Canvas Pareto plotting, live WebSocket telemetry, and interactive approval modals. | M4 | PLANNED |
| M6 | E2E Test Verification & Coverage Hardening | Features 31, 32, 33, 34: Final Milestone Phase 1: Pass 100% of E2E tests across Tiers 1-4. Phase 2: Adversarial coverage hardening with Challenger -> Worker -> Reviewer loop. | M1, M2, M3, M4, M5, E2E Track | PLANNED |
| E2E | E2E Testing Track | Features 31, 32, 33, 34: Design and build comprehensive requirement-driven, opaque-box E2E test harness (`tests/e2e/`) covering Tiers 1-4. Publishes `TEST_READY.md`. | M1 | DONE (TEST_READY.md published) |

## Interface Contracts

### 1. `packages/contracts` ↔ All Services & Applications
- **Task Models**:
  - `TaskCreate`: `{ goal: str, workspace_path: Optional[str], parameters: Optional[dict] }`
  - `Task`: `{ id: str, goal: str, workspace_path: str, status: TaskStatus, current_step_id: Optional[str], created_at: datetime, updated_at: datetime, completed_at: Optional[datetime], error: Optional[str] }`
  - `TaskStatus`: `Enum("queued", "planning", "running", "verifying", "completed", "failed", "cancelled", "blocked")`
- **Tool Models**:
  - `ToolDefinition`: `{ name: str, description: str, tier: PermissionTier, parameters_schema: dict }`
  - `ToolRequest`: `{ tool_name: str, parameters: dict, task_id: str, step_id: str }`
  - `ToolResult`: `{ success: bool, output: str, error: Optional[str], duration_ms: float, exit_code: Optional[int], modified_files: List[str] }`
  - `PermissionTier`: `Enum("read_only", "workspace_write", "git_isolated", "process_sandbox", "quantum_engine", "privileged")`
- **Approval Models**:
  - `ApprovalRequest`: `{ id: str, task_id: str, step_id: str, tool_name: str, parameters: dict, reason: str, status: str, created_at: datetime }`
  - `ApprovalDecision`: `{ approval_id: str, approved: bool, reason: Optional[str], decided_at: datetime }`
- **Event Models**:
  - `PlatformEvent`: `{ event_id: str, event_type: EventType, task_id: Optional[str], timestamp: datetime, payload: dict }`

### 2. `services/control-plane` ↔ `services/agent-runtime` & `apps/api`
- `ControlPlaneRepository`:
  - `create_task(goal: str, workspace_path: str) -> Task`
  - `get_task(task_id: str) -> Optional[Task]`
  - `list_tasks(status: Optional[TaskStatus] = None) -> List[Task]`
  - `transition_task(task_id: str, to_status: TaskStatus, error: Optional[str] = None) -> Task`
  - `record_step(task_id: str, step_name: str, criteria: str) -> Step`
  - `record_audit(task_id: str, tool_name: str, parameters: dict, output: str, exit_code: int, duration_ms: float, modified_files: List[str]) -> AuditRecord`
  - `request_approval(task_id: str, step_id: str, tool_name: str, parameters: dict, reason: str) -> ApprovalRequest`
  - `decide_approval(approval_id: str, approved: bool, reason: Optional[str] = None) -> ApprovalRequest`
  - `recover_active_tasks() -> List[Task]`

### 3. `services/sandbox-manager` ↔ `services/agent-runtime`
- `SandboxManager`:
  - `resolve_safe_path(workspace_root: str, relative_path: str) -> Path` (Raises `PathTraversalError` if escapes)
  - `run_command(cmd: List[str], cwd: str, timeout_sec: float = 30.0, env: Optional[dict] = None) -> ProcessResult`
  - `create_worktree(repo_path: str, task_id: str) -> str`
  - `cleanup_worktree(repo_path: str, task_id: str) -> None`

### 4. `services/agent-runtime` ↔ `apps/api` & `apps/cli`
- `AgentRuntime`:
  - `execute_task(task_id: str, on_event: Callable[[PlatformEvent], None]) -> TaskResult`
  - `resume_task(task_id: str, on_event: Callable[[PlatformEvent], None]) -> TaskResult`
  - `cancel_task(task_id: str) -> bool`

### 5. `apps/api` (FastAPI) ↔ `apps/workbench` & `apps/cli`
- REST Routes:
  - `GET /api/v1/health` -> `{ status: "ok", version: "0.3.0", components: {...} }`
  - `GET /api/v1/tasks` & `POST /api/v1/tasks`
  - `GET /api/v1/tasks/{id}` & `GET /api/v1/tasks/{id}/logs` & `POST /api/v1/tasks/{id}/resume`
  - `GET /api/v1/approvals` & `POST /api/v1/approvals/{id}/decide`
  - `POST /api/v1/quantum/optimize` & `POST /api/v1/quantum/estimate` & `POST /api/v1/quantum/baselines`
  - `GET /api/v1/artifacts` & `GET /api/v1/artifacts/{id}`
- Streaming:
  - WebSocket: `/ws/stream` -> Real-time bidirectional JSON events
  - SSE: `/api/v1/events/stream` -> Server-Sent Events text stream
