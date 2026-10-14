## 2026-10-14T12:38:42Z
You are Worker M2 (Control Plane, Contracts & Persistence Worker) for Plaq-OS.
Your working directory is: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\worker_m2_1
The project root is: C:\Users\hp\Desktop\plaq-os
The authoritative original user request is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\ORIGINAL_REQUEST.md
The project master plan is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\orchestrator_1\PROJECT.md
The Explorer 1 (Contracts & SDK) blueprint is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m2_1\handoff.md
The Explorer 2 (Control Plane DB & State Machine) blueprint is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m2_2\handoff.md
The Explorer 3 (Audit Trail & Artifacts) blueprint is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m2_3\handoff.md
The E2E test harness contracts are at: C:\Users\hp\Desktop\plaq-os\tests\e2e\conftest.py

You MUST read C:\Users\hp\Desktop\plaq-os\.agents\teamwork\ORIGINAL_REQUEST.md, the three Explorer blueprints, and tests/e2e/conftest.py before starting.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

SCOPE & IMPLEMENTATION OBJECTIVES:
Implement Milestone M2 (Requirement R2: Persistent Control Plane, Shared Contracts & Task State Engine):

1. `packages/contracts` (`packages/contracts/src/plaq_contracts/`):
   - `pyproject.toml` (package `plaq-contracts` 0.1.0)
   - `__init__.py`: Clean exports of all schemas and enums
   - `common.py`: UUID generation, ISO8601 UTC timestamp utilities, pagination schemas
   - `task.py`: `Task`, `TaskCreate`, `TaskUpdate`, `TaskStatus` Enum ("queued", "planning", "running", "verifying", "completed", "failed", "cancelled", "blocked")
   - `step.py`: `PlanStep`, `StepStatus` Enum, `PlanDefinition`
   - `tool.py`: `ToolDefinition`, `ToolRequest`, `ToolResult`, `PermissionTier` Enum ("read_only", "workspace_write", "git_isolated", "process_sandbox", "quantum_engine", "privileged")
   - `approval.py`: `ApprovalRequest`, `ApprovalDecision`, `ApprovalStatus` Enum ("pending", "approved", "rejected")
   - `artifact.py`: `ArtifactRecord`, `ArtifactType` Enum
   - `event.py`: `PlatformEvent`, `EventType` Enum
   - `quantum.py`: `QuantumCompileRequest`, `QuantumEstimateRequest`, `QuantumBenchmarkRequest`, `QuantumResult`
   * Ensure models use `ConfigDict(from_attributes=True, populate_by_name=True, validate_assignment=True, use_enum_values=True)` and include field validators (`mode="before"`) for JSON string parsing when hydrated from SQLite row strings.

2. `packages/sdk-python` (`packages/sdk-python/src/plaq_sdk/`):
   - `pyproject.toml` (package `plaq-sdk` 0.1.0)
   - `__init__.py`: export `PlaqClient`
   - `client.py`: `PlaqClient` supporting both local in-process direct repository access and remote HTTP/WebSocket connection.

3. `services/control-plane` (`services/control-plane/src/plaq_control_plane/`):
   - `pyproject.toml` (package `plaq-control-plane` 0.1.0)
   - `__init__.py`: Clean exports
   - `db.py`: SQLite connection factory with WAL mode (`PRAGMA journal_mode=WAL`), foreign keys (`PRAGMA foreign_keys=ON`), busy timeout (`PRAGMA busy_timeout=5000`), connection context manager, and schema init executing the 10-table normalized DDL:
     `users`, `projects`, `workspaces`, `tasks`, `agent_sessions`, `steps`, `tool_calls`, `approvals`, `audit_trail`, `artifacts`.
   - `models.py`: Row mappers & database transfer objects
   - `state_machine.py`: `TaskStateMachine` enforcing strict 8-state transition matrix and terminal state immutability. Raises `StateTransitionError` / `InvalidStateTransitionError` on illegal transitions.
   - `repository.py`: `ControlPlaneRepository` implementing atomic CRUD for all entities, context-managed transactions, pagination, step transitions, and approval updates.
   - `audit.py`: `AuditTrailManager` with SHA-256 chained hashing (`prev_hash` + current entry digest), genesis block hash, and `verify_chain()` integrity validator.
   - `redact.py`: `SecretRedactor` / `redact_sensitive_info` regex filter scrubbing Bearer tokens, JWTs, AWS keys (`AKIA...`), GitHub PATs (`ghp_...`), private keys, passwords, and tokens from text and dictionary payloads.
   - `recovery.py`: `CheckpointRecoveryManager` that inspects in-flight tasks (`planning`, `running`, `verifying`, `blocked`), re-evaluates active steps, restores state into memory, and resumes execution seamlessly after server crash.

4. `services/artifact-service` (`services/artifact-service/src/plaq_artifacts/`):
   - `pyproject.toml` (package `plaq-artifacts` 0.1.0)
   - `__init__.py`: export `ArtifactService`
   - `service.py`: Content-addressable storage using SHA-256 digests, stores artifacts on disk/workspace, publishes verified artifacts, and registers records in the control plane database.

5. Monorepo import integration:
   - Ensure `plaq_bootstrap.py` at repo root includes all new package paths in `sys.path`.

6. VERIFICATION (Execute every command and verify 0 failures):
   - `pytest -v tests/e2e/test_tier1_feature.py -k "TestFeature03ControlPlanePersistence or TestFeature04TaskStateMachine or TestFeature05AuditTrail or TestFeature06SecretRedaction or TestFeature07CheckpointRecovery"`
   - `pytest -v tests/e2e/test_tier2_boundary.py -k "TestBoundary02SQLiteConcurrency or TestBoundary03TaskStateViolations or TestBoundary05SecretRedaction or TestBoundary07MissingInputsAndCorruption"`
   - `pytest -v tests/e2e/test_tier3_pairwise.py -k TestPairwise01StateApprovalAudit`
   - `pytest -v tests/e2e/test_tier4_workloads.py -k test_s3_crash_recovery_resumes_in_flight_task`
   - `pytest -v engines/quantum/tests/` (Must maintain 38/38 passing quantum tests)
   - `pytest -v tests/test_quantum_adversarial.py` (Must maintain 22/22 passing adversarial tests)

FILE OWNERSHIP:
- You exclusively own: `packages/contracts/**`, `packages/sdk-python/**`, `services/control-plane/**`, `services/artifact-service/**`, `plaq_bootstrap.py`.

OUTPUT REQUIREMENTS:
- Maintain your liveness in `progress.md` in your working directory.
- Write your comprehensive implementation and verification report to `handoff.md` in your working directory.
- Send a message back to the orchestrator with the summary and path to your handoff.md.
