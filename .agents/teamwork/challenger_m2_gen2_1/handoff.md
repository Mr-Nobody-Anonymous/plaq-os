# Milestone M2 Empirical Challenge Report: Persistent Control Plane & State Engine

**Author**: Challenger M2-1 (`challenger_m2_gen2_1`)  
**Roles**: critic, specialist  
**Working Directory**: `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\challenger_m2_gen2_1`  
**Milestone**: M2 (Requirement R2: Persistent Control Plane, Shared Contracts & Task State Engine)  
**Date**: 2026-10-14  
**Verdict**: **APPROVE** (Confirmed Robust)

---

## 1. Observation

### 1.1 Scope and Code Under Review
1. `services/control-plane/src/plaq_control_plane/db.py`:
   - Normalized 10-table relational SQLite schema (`users`, `projects`, `workspaces`, `tasks`, `agent_sessions`, `steps`, `tool_calls`, `approvals`, `artifacts`, `audit_trail`).
   - SQLite PRAGMAs initialized per connection (lines 180-184):
     - `PRAGMA journal_mode = WAL;`
     - `PRAGMA foreign_keys = ON;`
     - `PRAGMA busy_timeout = 5000;`
     - `PRAGMA synchronous = NORMAL;`
   - Connection pooling via `threading.local()` with explicit `BEGIN IMMEDIATE;` atomic transaction context managers.
2. `services/control-plane/src/plaq_control_plane/repository.py`:
   - `ControlPlaneRepository` handling atomic task CRUD, transitions, step recordings, approvals, and audit trails.
3. `services/control-plane/src/plaq_control_plane/state_machine.py`:
   - `TaskStateMachine` specifying the strict 8-state transition matrix and terminal state immutability.
4. `services/control-plane/src/plaq_control_plane/audit.py`:
   - `AuditChainer` and `AuditTrailManager` maintaining unbroken SHA-256 hash chains from genesis hash `"0" * 64`.

### 1.2 Mandatory Baseline Test Executions
1. **Control Plane Unit Tests**:
   - Command:
     ```pwsh
     pytest -v tests/test_plaq_control_plane.py
     ```
   - Verbatim Output:
     ```text
     ============================= test session starts =============================
     platform win32 -- Python 3.10.11, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\hp\AppData\Local\Programs\Python\Python310\python.exe
     cachedir: .pytest_cache
     rootdir: C:\Users\hp\Desktop\plaq-os
     configfile: pytest.ini
     plugins: cov-7.1.0, anyio-4.15.1
     collecting ... collected 6 items

     tests/test_plaq_control_plane.py::test_schema_and_pragmas PASSED         [ 16%]
     tests/test_plaq_control_plane.py::test_task_crud_and_validation PASSED   [ 33%]
     tests/test_plaq_control_plane.py::test_step_and_tool_call_lifecycle PASSED [ 50%]
     tests/test_plaq_control_plane.py::test_approval_flow_and_gating PASSED   [ 66%]
     tests/test_plaq_control_plane.py::test_audit_hash_chain_and_redaction PASSED [ 83%]
     tests/test_plaq_control_plane.py::test_checkpoint_recovery_manager PASSED [100%]

     ============================== 6 passed in 0.22s ==============================
     ```

2. **Tier 2 Boundary Tests (Concurrency & State Transitions)**:
   - Command:
     ```pwsh
     pytest -v tests/e2e/test_tier2_boundary.py -k "TestBoundary02SQLiteConcurrency or TestBoundary03InvalidStateTransitions"
     ```
   - Verbatim Output:
     ```text
     ============================= test session starts =============================
     platform win32 -- Python 3.10.11, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\hp\AppData\Local\Programs\Python\Python310\python.exe
     cachedir: .pytest_cache
     rootdir: C:\Users\hp\Desktop\plaq-os
     configfile: pytest.ini
     plugins: cov-7.1.0, anyio-4.15.1
     collecting ... collected 77 items / 55 deselected / 22 selected

     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_01_concurrent_multithread_readers PASSED [  4%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_02_concurrent_readers_and_writers PASSED [  9%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_03_rapid_sequential_transactions PASSED [ 13%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_04_busy_timeout_pragma_active PASSED [ 18%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_05_rollback_on_failed_transaction PASSED [ 22%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_06_concurrent_audit_logging PASSED [ 27%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_07_concurrent_step_recording PASSED [ 31%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_08_concurrent_approval_updates PASSED [ 36%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_09_read_during_large_batch_insert PASSED [ 40%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_10_connection_leak_recovery PASSED [ 45%]
     tests/e2e/test_tier2_boundary.py::TestBoundary02SQLiteConcurrency::test_b2_11_wal_checkpoint_truncate PASSED [ 50%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_01_disallowed_jump_queued_to_completed PASSED [ 54%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_02_disallowed_jump_queued_to_verifying PASSED [ 59%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_03_modification_of_completed_task PASSED [ 63%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_04_modification_of_cancelled_task PASSED [ 68%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_05_unknown_state_names_rejected PASSED [ 72%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_06_disallowed_jump_planning_to_completed PASSED [ 77%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_07_disallowed_jump_blocked_to_verifying PASSED [ 81%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_08_disallowed_transition_failed_to_running PASSED [ 86%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_09_disallowed_transition_failed_to_completed PASSED [ 90%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_10_disallowed_jump_verifying_to_planning PASSED [ 95%]
     tests/e2e/test_tier2_boundary.py::TestBoundary03InvalidStateTransitions::test_b3_11_empty_state_string_rejected PASSED [100%]
     ================ 22 passed, 55 deselected, 2 warnings in 2.45s ================
     ```

### 1.3 Empirical Adversarial Stress Suite (`tests/test_m2_adversarial.py`)
To rigorously stress-test the production `DatabaseEngine` and `ControlPlaneRepository` directly against on-disk SQLite databases (beyond the conftest wrapper), an adversarial suite of 47 tests was authored in `tests/test_m2_adversarial.py`:
- Command:
  ```pwsh
  pytest -v tests/test_m2_adversarial.py
  ```
- Verbatim Output:
  ```text
  ============================= test session starts =============================
  platform win32 -- Python 3.10.11, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\hp\AppData\Local\Programs\Python\Python310\python.exe
  cachedir: .pytest_cache
  rootdir: C:\Users\hp\Desktop\plaq-os
  configfile: pytest.ini
  plugins: cov-7.1.0, anyio-4.15.1
  collecting ... collected 47 items

  tests/test_m2_adversarial.py::TestM2ConcurrencyStress::test_wal_mode_and_pragmas_on_disk PASSED [  2%]
  tests/test_m2_adversarial.py::TestM2ConcurrencyStress::test_heavy_multithreaded_read_write_stress PASSED [  4%]
  tests/test_m2_adversarial.py::TestM2ConcurrencyStress::test_concurrent_audit_chain_verifiability PASSED [  6%]
  tests/test_m2_adversarial.py::TestM2ConcurrencyStress::test_wal_checkpoint_truncate_under_read_pressure PASSED [  8%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[queued-completed] PASSED [ 10%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[queued-failed] PASSED [ 12%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[queued-cancelled] PASSED [ 14%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[planning-completed] PASSED [ 17%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[planning-failed] PASSED [ 19%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[planning-cancelled] PASSED [ 21%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[running-completed] PASSED [ 23%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[running-failed] PASSED [ 25%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[running-cancelled] PASSED [ 27%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[verifying-completed] PASSED [ 29%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[verifying-failed] PASSED [ 31%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[verifying-cancelled] PASSED [ 34%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[completed-completed] PASSED [ 36%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[completed-failed] PASSED [ 38%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[completed-cancelled] PASSED [ 40%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[failed-completed] PASSED [ 42%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[failed-failed] PASSED [ 44%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[failed-cancelled] PASSED [ 46%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[cancelled-completed] PASSED [ 48%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[cancelled-failed] PASSED [ 51%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[cancelled-cancelled] PASSED [ 53%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[blocked-completed] PASSED [ 55%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[blocked-failed] PASSED [ 57%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[blocked-cancelled] PASSED [ 59%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[UNKNOWN-completed] PASSED [ 61%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[UNKNOWN-failed] PASSED [ 63%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[UNKNOWN-cancelled] PASSED [ 65%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[-completed] PASSED [ 68%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[-failed] PASSED [ 70%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[-cancelled] PASSED [ 72%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[in_progress-completed] PASSED [ 74%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[in_progress-failed] PASSED [ 76%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[in_progress-cancelled] PASSED [ 78%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[terminated-completed] PASSED [ 80%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[terminated-failed] PASSED [ 82%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_terminal_state_immutability_all_targets[terminated-cancelled] PASSED [ 85%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_exhaustive_64_state_transition_matrix PASSED [ 87%]
  tests/test_m2_adversarial.py::TestM2StateMachineImmutability::test_state_machine_self_transitions_disallowed PASSED [ 89%]
  tests/test_m2_adversarial.py::TestM2ForeignKeyCascades::test_orphaned_inserts_rejected PASSED [ 91%]
  tests/test_m2_adversarial.py::TestM2ForeignKeyCascades::test_cascading_delete_on_task_removal PASSED [ 93%]
  tests/test_m2_adversarial.py::TestM2ForeignKeyCascades::test_step_deletion_sets_null_on_tool_calls PASSED [ 95%]
  tests/test_m2_adversarial.py::TestM2ForeignKeyCascades::test_project_deletion_cascades_workspaces PASSED [ 97%]
  tests/test_m2_adversarial.py::TestM2ForeignKeyCascades::test_sqlite_check_constraint_rejects_bogus_status PASSED [100%]

  ============================= 47 passed in 4.12s ==============================
  ```

### 1.4 Full Regression Test Execution
- Command: `pytest`
- Verbatim Result: `156 passed in 31.80s` (covering quantum engine, control plane, contracts, artifacts, SDK, and both adversarial suites).

---

## 2. Logic Chain

1. **Concurrency Stress Resilience**:
   - *Observation 1.3 (`test_heavy_multithreaded_read_write_stress`)*: 20 writer threads and 10 continuous reader threads (30 concurrent threads total) performed 100 task creations, 100 transitions, 100 step recordings, 100 tool calls, and 100 audit entries on an on-disk database file.
   - *Inference*: `DatabaseEngine`'s thread-local connection model combined with `PRAGMA journal_mode = WAL` and `PRAGMA busy_timeout = 5000` completely prevented `sqlite3.OperationalError: database is locked`. Zero tasks or audit entries were lost or dropped.
   - *Observation 1.3 (`test_concurrent_audit_chain_verifiability`)*: 15 threads logged 6 audit entries each across distinct tasks. Every single task's hash chain from genesis (`0`*64) was validated as unbroken by `AuditChainer.verify_chain`.
   - *Observation 1.3 (`test_wal_checkpoint_truncate_under_read_pressure`)*: Executing `PRAGMA wal_checkpoint(TRUNCATE)` while concurrent readers actively queried tasks passed without deadlocks or latency spikes.

2. **State Machine Immutability**:
   - *Observation 1.3 (`test_terminal_state_immutability_all_targets`)*: Evaluated all 3 terminal states (`completed`, `failed`, `cancelled`) against 12 targets (`queued`, `planning`, `running`, `verifying`, `completed`, `failed`, `cancelled`, `blocked`, `UNKNOWN`, `""`, `in_progress`, `terminated`).
   - *Inference*: Both `TaskStateMachine.validate_transition` and `ControlPlaneRepository.transition_task` raised `InvalidStateTransitionError` across all parameter combinations (with error, without error, empty error), leaving task `status` and `completed_at` timestamps strictly immutable.
   - *Observation 1.3 (`test_exhaustive_64_state_transition_matrix`)*: All 64 transitions across all 8 states were evaluated against the specification; exactly and only valid transitions are permitted. Self-transitions are rejected for all states.

3. **Foreign Key Cascades & Relational Integrity**:
   - *Observation 1.3 (`test_orphaned_inserts_rejected`)*: Directly inserting into `steps`, `tool_calls`, `approvals`, `artifacts`, `audit_trail`, or `workspaces` with non-existent parent IDs raised `sqlite3.IntegrityError` in every case, confirming `PRAGMA foreign_keys = ON` is universally active.
   - *Observation 1.3 (`test_cascading_delete_on_task_removal`)*: Removing a task row from `tasks` cleanly triggered cascading deletion across all 5 dependent tables (`steps`, `tool_calls`, `approvals`, `artifacts`, `audit_trail`).
   - *Observation 1.3 (`test_step_deletion_sets_null_on_tool_calls`)*: Deleting a step set `tool_calls.step_id` to `NULL` (`ON DELETE SET NULL`) while preserving the historical tool invocation.
   - *Observation 1.3 (`test_project_deletion_cascades_workspaces`)*: Removing a project cascaded to all associated workspaces.
   - *Observation 1.3 (`test_sqlite_check_constraint_rejects_bogus_status`)*: SQLite table schema CHECK constraint (`CHECK (status IN (...))`) blocked invalid task statuses at the database layer.

---

## 3. Caveats

- **No Caveats**: Concurrency, state machine transitions, and foreign key cascades were tested directly against genuine SQLite file-based databases with multithreaded contention on Windows.
- **Scope Boundary**: Network-level timeout and connection drops across HTTP/WebSocket belong to Milestone M4 (FastAPI Backend & CLI) and were not part of M2 control plane persistence.

---

## 4. Conclusion & Verdict

**Verdict**: **APPROVE**

Milestone M2 demonstrates outstanding engineering quality:
1. **Concurrency**: Zero database locks or corruption under high multithreaded reader/writer load (30 concurrent workers).
2. **State Machine**: Terminal states are strictly immutable; 100% of illegal state jumps raise `InvalidStateTransitionError`.
3. **Foreign Keys**: SQLite relational constraints are enforced on disk; orphaned rows are rejected and cascading deletions clear all child entities cleanly.
4. **Audit Integrity**: Cryptographic SHA-256 hash chains remain unbroken across concurrent task executions.

Milestone M2 is confirmed robust and ready for Milestone M3.

---

## 5. Verification Method

To independently reproduce and verify this assessment, run the following commands from `C:\Users\hp\Desktop\plaq-os`:

```pwsh
# 1. Run Control Plane unit suite
pytest -v tests/test_plaq_control_plane.py

# 2. Run Tier 2 boundary tests (concurrency & state machine)
pytest -v tests/e2e/test_tier2_boundary.py -k "TestBoundary02SQLiteConcurrency or TestBoundary03InvalidStateTransitions"

# 3. Run Milestone M2 Empirical Adversarial Suite (47 tests)
pytest -v tests/test_m2_adversarial.py

# 4. Run entire monorepo test suite (156 tests)
pytest
```
