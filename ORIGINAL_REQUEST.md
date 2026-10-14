# Original User Request

## 2026-10-14T11:06:22Z

Build Plaq-OS as a programmable, agent-driven quantum computing workbench and OS-like execution platform that unifies a developer desktop workbench, an isolated AI agent runtime with controlled tools, a persistent control plane, and a domain-specific fault-tolerant quantum co-design engine.

Requested team: Full multi-agent engineering team (Orchestrator, Research, Coding, Testing, Review, Integration)
Working directory: C:\Users\hp\Desktop\plaq-os
Integrity mode: development

## Verification Resources
- Existing test suite (38 passing unit tests) located at `tests/` validating:
  - Rotated surface code simulation and PyMatching 2.4+ MWPM decoding (`tests/test_stim_bridge.py`)
  - Ross-Selinger $T$-gate synthesis, critical path DAG depth, and composite crosstalk errors (`tests/test_cost_model.py`)
  - Literature hardware profiles with heavy-hex spanning connectivity (`tests/test_hardware.py`)
  - Multi-objective Pareto frontier extraction and SHA-256 compilation caching (`tests/test_optimizer.py`)
  - Four-Baselines comparative protocol and systematic layer ablation (`tests/test_baselines.py`)
  - Fair search algorithm benchmarking (`tests/test_search_algorithms.py`)
- Benchmark runner and CLI pipeline in `main.py` and `benchmark.py`.

## Requirements

### R1. Full Monorepo Architecture & Quantum Engine Modularization
- Reorganize repository into a production-grade monorepo layout:
  - `apps/`: User-facing applications (`apps/api` for FastAPI backend, `apps/cli` for unified `plaq` CLI, and `apps/workbench` for desktop/web UI).
  - `packages/`: Reusable packages (`packages/contracts` for data schemas, `packages/sdk-python` for local/remote client access).
  - `services/`: Core platform services (`services/control-plane` for task state and permissions, `services/agent-runtime` for loop and tool dispatch, `services/sandbox-manager` for process isolation, `services/model-gateway` for provider abstraction, `services/artifact-service` for reports and diffs).
  - `engines/quantum/`: Quantum package (`src/plaq_quantum/`) containing circuits, hardware profiles, cost models, Stim/PyMatching QEC simulation, Pareto optimization, and baselines.
  - `shared/`: Versioned schemas, security policies, and agent prompts.
- All existing 38 tests must continue to pass cleanly within `engines/quantum/`.

### R2. Plaq Control Plane & Durable Task State Engine
- Implement a persistent SQLite/schema-backed state engine tracking:
  - Users, projects, workspaces, tasks, agent sessions, steps, approvals, and artifacts.
- Enforce the task lifecycle: `queued` → `planning` → `running` → `verifying` → `completed` (with `failed`, `cancelled`, `blocked`).
- Maintain an append-only audit trail recording every tool invocation, parameters, execution time, exit code, and modified file hashes.
- Support checkpoint recovery: interrupting and restarting the application resumes in-flight tasks without data loss.

### R3. Plaq Agent Runtime, Tool Registry & Sandbox Boundaries
- Implement an agent execution loop:
  `Receive Task → Inspect Context → Plan & Define Criteria → Execute Tool → Collect Output → Verify → Review Diff & Deliver`.
- Implement a typed tool registry with strict permission tiers:
  - `workspace.list` & `workspace.read` (Read-only)
  - `workspace.patch` & `workspace.write` (Workspace-scoped write)
  - `git.diff` & `git.branch` (Git operations in isolated worktrees)
  - `terminal.run` & `tests.run` (Sandboxed process execution with timeouts)
  - `quantum.compile`, `quantum.estimate`, `quantum.simulate` (Domain engine operations)
  - `artifacts.publish` (Save verified reports and diffs)
- Provide human approval gates for sensitive/destructive operations (e.g. deleting files, executing privileged commands).

### R4. Unified CLI & Application API
- Expose a FastAPI REST API and WebSocket/SSE event streaming for tasks, workspaces, agent sessions, approvals, and quantum experiments.
- Build the `plaq` CLI entrypoint supporting:
  - `plaq task create <goal>` / `plaq task list` / `plaq task status <id>` / `plaq task logs <id>`
  - `plaq quantum compile` / `plaq quantum estimate` / `plaq quantum benchmark`
  - `plaq workspace open <path>` / `plaq serve --port <port>`

### R5. Plaq Workbench Desktop & Quantum Lab Interface
- Build an OS-like multi-panel interface featuring:
  - **Left Sidebar**: Workspace file tree, agent session monitor, task queue, and quantum experiments.
  - **Center Workspace**: Code viewer/editor, interactive terminal, diff inspector, and quantum Pareto visualization.
  - **Right Inspector**: Active agent plan and criteria, live tool execution stream, resource counters, and approval prompt modals.
  - **Bottom Panel**: Test runner output, job timelines, and event logs.

## Acceptance Criteria

### Core Monorepo & Quantum Engine
- [ ] Directory structure matches monorepo specification (`apps/`, `services/`, `engines/quantum/`, `packages/`, `shared/`).
- [ ] `engines/quantum/` is fully functional with 100% of existing 38 unit tests passing.

### Agent Loop & Tool Registry
- [ ] Agent execution loop takes an end-to-end task (e.g. "Run test suite and generate benchmark artifact"), creates structured plan steps, executes tools, and completes.
- [ ] All tool invocations are schema-validated, logged with duration and exit codes, with secrets redacted.
- [ ] Protected operations (destructive commands, file deletion) block until an explicit approval is granted.

### Control Plane Persistence
- [ ] Database persists tasks, steps, tool calls, and artifacts across application restarts.
- [ ] Reconnecting or reloading recovers active task state and history.

### CLI, API & UI Workbench
- [ ] FastAPI backend starts up and provides health, task, and quantum endpoints.
- [ ] `plaq` CLI commands execute and output valid JSON or formatted tables.
- [ ] Workbench web interface runs and displays file explorer, live agent status, quantum trade-off charts, and approval modals.
