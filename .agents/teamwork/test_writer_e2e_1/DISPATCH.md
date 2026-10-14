## 2026-10-14T11:20:49Z
You are Test Writer (E2E Test Writer) for Plaq-OS.
Your working directory is: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\test_writer_e2e_1
The project root is: C:\Users\hp\Desktop\plaq-os
The authoritative original user request is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\ORIGINAL_REQUEST.md
The project master plan is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\orchestrator_1\PROJECT.md
The E2E test infrastructure specification is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\orchestrator_1\TEST_INFRA.md

You MUST read C:\Users\hp\Desktop\plaq-os\.agents\teamwork\ORIGINAL_REQUEST.md, C:\Users\hp\Desktop\plaq-os\.agents\teamwork\orchestrator_1\PROJECT.md, and C:\Users\hp\Desktop\plaq-os\.agents\teamwork\orchestrator_1\TEST_INFRA.md before starting.

TASK:
Design and implement the complete requirement-driven, opaque-box E2E test suite in `tests/e2e/`:
1. Shared Test Fixtures (`tests/e2e/conftest.py`):
   - `temp_workspace`: creates temporary directory with initialized git repo.
   - `test_db`: creates in-memory or temp SQLite database with control plane schema.
   - `event_recorder`: captures async/sync event broadcasts.
2. Tier 1 - Feature Coverage (`tests/e2e/test_tier1_feature.py`):
   - >=5 tests per feature area across all 16 major inventoried features:
     * Monorepo layout & quantum engine modularization
     * SQLite control plane persistence & CRUD
     * Task lifecycle state machine (8 states: queued, planning, running, verifying, completed, failed, cancelled, blocked)
     * Append-only audit trail with hash chaining
     * Secret redaction in audit logs
     * Checkpoint recovery upon restart
     * Sandbox PathGuard path traversal rejection
     * Subprocess runner timeout & process-tree termination
     * Agent execution loop (7-stage deterministic flow)
     * Typed tool registry (6 tiers)
     * Human approval gates & blocking transitions
     * FastAPI REST API endpoints (/health, /tasks, /approvals, /quantum, /artifacts)
     * WebSocket & SSE event streaming
     * Unified `plaq` CLI commands
     * Plaq Workbench 4-panel HTML/CSS/JS interface structure
3. Tier 2 - Boundary & Corner Cases (`tests/e2e/test_tier2_boundary.py`):
   - >=5 tests per boundary condition:
     * Path traversal attacks (`../../`, absolute paths, null bytes, symlinks)
     * Concurrent SQLite read/write lock contention & busy timeout handling
     * Invalid state machine transitions (e.g., queued directly to completed, modifying cancelled tasks)
     * Process timeout termination with runaway child processes
     * Secret redaction edge cases (Bearer tokens, AWS keys, multiline secrets)
     * High quantum noise thresholds ($p \ge p_{th}$) and odd code distance bounds ($d < 3$, even $d$)
     * Empty CLI inputs, non-existent task IDs, corrupted database files
4. Tier 3 - Cross-Feature Combinations (`tests/e2e/test_tier3_pairwise.py`):
   - Pairwise interactions:
     * Task State Machine + Approval Gate + Audit Trail
     * Agent Execution Loop + Process Sandbox + Secret Redaction
     * CLI + FastAPI REST + SQLite Persistence
     * Quantum Engine + Artifact Service + WebSocket Event Broadcaster
5. Tier 4 - Real-World Application Workflows (`tests/e2e/test_tier4_workloads.py`):
   - Complete end-to-end user application scenarios:
     * Scenario 1: End-to-end task execution from CLI, step planning, tool invocation, secret scrubbing, artifact generation, completion.
     * Scenario 2: Destructive operation triggers human approval gate, task blocks, approval granted via REST API, task resumes and finishes.
     * Scenario 3: Mid-execution server restart checkpoint recovery (task state rehydrated without data loss).
     * Scenario 4: Quantum co-design optimization pipeline via CLI and API.
     * Scenario 5: Real-time Workbench WebSocket streaming and event logging.
6. Publish `TEST_READY.md` at project root with full runner instructions and coverage matrix.

FILE OWNERSHIP:
- You exclusively own: `tests/e2e/**` and `TEST_READY.md`.
