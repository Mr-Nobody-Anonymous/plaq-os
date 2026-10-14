# Milestone M2 Code and Contract Review Report: Shared Contracts & Python SDK

**Reviewer**: `reviewer_m2_gen2_1` (Reviewer M2-1)  
**Roles**: reviewer, critic  
**Working Directory**: `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\reviewer_m2_gen2_1`  
**Target Milestone**: M2 (`packages/contracts` and `packages/sdk-python`)  
**Verdict**: **APPROVE**  
**Date**: 2026-10-14  

---

## 1. Observation

### 1.1 Scope & Codebase Inspection
The following packages, modules, and test suites were inspected and verified against `ORIGINAL_REQUEST.md` and `PROJECT.md`:

1. **`packages/contracts` (`plaq-contracts` v0.1.0)**:
   - `packages/contracts/pyproject.toml`: Declares package metadata and dependency `pydantic>=2.0.0`.
   - `packages/contracts/src/plaq_contracts/__init__.py`: Cleanly re-exports all canonical models, enums, and utility functions in `__all__`.
   - `packages/contracts/src/plaq_contracts/common.py`:
     - `generate_id(prefix=None) -> str`: Generates UUID4 strings with optional prefix.
     - `utc_now() -> datetime`, `utc_now_iso() -> str`: Standard timezone-aware UTC datetime helpers.
     - `PlaqBaseModel(BaseModel)`: Standard Pydantic v2 configuration with `from_attributes=True, populate_by_name=True, validate_assignment=True, use_enum_values=True`.
     - `PaginationParams`, `PaginatedResponse[T]`, `SuccessResponse`, `ErrorResponse`.
   - `packages/contracts/src/plaq_contracts/task.py`:
     - `TaskStatus(str, Enum)`: Enforces the 8 canonical states: `QUEUED`, `PLANNING`, `RUNNING`, `VERIFYING`, `COMPLETED`, `FAILED`, `CANCELLED`, `BLOCKED`.
     - `TaskCreate`, `TaskUpdate`, `Task`: Full task data models with `@field_validator("parameters", mode="before")` to automatically deserialize raw JSON strings stored in SQLite columns into Python dictionaries.
   - `packages/contracts/src/plaq_contracts/step.py`:
     - `StepStatus(str, Enum)`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`.
     - `PlanStep`, `PlanDefinition`: Plan models with sequential step indexing and JSON parameter deserialization.
   - `packages/contracts/src/plaq_contracts/tool.py`:
     - `PermissionTier(str, Enum)`: Enforces the 6 security boundaries (`READ_ONLY`, `WORKSPACE_WRITE`, `GIT_ISOLATED`, `PROCESS_SANDBOX`, `QUANTUM_ENGINE`, `PRIVILEGED`).
     - `DEFAULT_TOOL_TIERS`: Canonical dictionary mapping tools (e.g. `workspace.read`, `terminal.run`, `quantum.compile`, `artifacts.publish`) to their required permission tier.
     - `ToolDefinition`, `ToolRequest`, `ToolResult`, `AuditRecord`: Enforces duration (`duration_ms >= 0`), exit codes, modified files lists, and chained hashes.
   - `packages/contracts/src/plaq_contracts/approval.py`:
     - `ApprovalStatus(str, Enum)`: `PENDING`, `APPROVED`, `REJECTED`.
     - `ApprovalRequest`, `ApprovalDecision`.
   - `packages/contracts/src/plaq_contracts/artifact.py`:
     - `ArtifactType(str, Enum)`: 13 artifact categories including `REPORT`, `DIFF`, `CIRCUIT`, `BENCHMARK`, `PARETO_FRONTIER`, `QUANTUM_PARETO`.
     - `ArtifactRecord`: Enforces SHA-256 length (`min_length=64, max_length=64`) and non-negative size (`ge=0`).
     - `ArtifactPublishRequest`.
   - `packages/contracts/src/plaq_contracts/event.py`:
     - `EventType(str, Enum)`: 18 platform event categories.
     - `PlatformEvent`: Canonical event envelope for WebSocket and SSE broadcasting.
   - `packages/contracts/src/plaq_contracts/quantum.py`:
     - `QuantumCompileRequest`, `QuantumEstimateRequest`, `QuantumBenchmarkRequest`, `QuantumResult`: Input/output contracts for quantum circuit compilation, analytical fault-tolerant resource estimation, and Pareto optimization.

2. **`packages/sdk-python` (`plaq-sdk` v0.1.0)**:
   - `packages/sdk-python/pyproject.toml`: Declares package metadata, dependency `plaq-contracts>=0.1.0`, `httpx>=0.25.0`, `websockets>=12.0`.
   - `packages/sdk-python/src/plaq_sdk/__init__.py`: Exports `PlaqClient`.
   - `packages/sdk-python/src/plaq_sdk/models.py`: Clean re-export of all canonical contracts and enums.
   - `packages/sdk-python/src/plaq_sdk/client.py`:
     - Unified `PlaqClient` supporting both direct in-process local execution and remote HTTP/SSE access.
     - `PlaqClient.local_client(db_path)` and `PlaqClient.remote_client(base_url, api_key)` factory constructors.
     - Context manager support (`__enter__`, `__exit__`, `close()`) properly closing HTTP and SQLite connections.
     - Local mode delegates to `ControlPlaneRepository` for task CRUD, state transitions, audit logs, and approval gating.
     - Local quantum estimation delegates to `plaq_quantum.cost_model.solve_minimum_code_distance`.
     - Remote mode uses `httpx.Client` for REST endpoints (`/api/v1/health`, `/api/v1/tasks`, `/api/v1/approvals`, `/api/v1/quantum/estimate`) and Server-Sent Events (`/api/v1/events/stream`).

### 1.2 Verification Test Execution Results

#### Command 1: Dedicated Contracts and SDK Unit Test Suite
```pwsh
pytest -v tests/test_plaq_contracts.py tests/test_plaq_sdk.py
```
**Exact Output**:
```text
============================= test session starts =============================
platform win32 -- Python 3.10.11, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\hp\AppData\Local\Programs\Python\Python310\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\hp\Desktop\plaq-os
configfile: pytest.ini
plugins: cov-7.1.0, anyio-4.15.1
collecting ... collected 12 items

tests/test_plaq_contracts.py::TestCommonContracts::test_id_generation PASSED [  8%]
tests/test_plaq_contracts.py::TestCommonContracts::test_utc_now_format PASSED [ 16%]
tests/test_plaq_contracts.py::TestCommonContracts::test_pagination_and_responses PASSED [ 25%]
tests/test_plaq_contracts.py::TestTaskContracts::test_task_create_and_validation PASSED [ 33%]
tests/test_plaq_contracts.py::TestTaskContracts::test_task_row_hydration PASSED [ 41%]
tests/test_plaq_contracts.py::TestStepAndToolContracts::test_step_contract PASSED [ 50%]
tests/test_plaq_contracts.py::TestStepAndToolContracts::test_tool_definitions_and_tiers PASSED [ 58%]
tests/test_plaq_contracts.py::TestApprovalAndArtifactContracts::test_approval_contracts PASSED [ 66%]
tests/test_plaq_contracts.py::TestApprovalAndArtifactContracts::test_artifact_contracts PASSED [ 75%]
tests/test_plaq_contracts.py::TestQuantumContracts::test_quantum_contracts PASSED [ 83%]
tests/test_plaq_sdk.py::test_plaq_client_local_lifecycle PASSED          [ 91%]
tests/test_plaq_sdk.py::test_plaq_client_quantum_estimation PASSED       [100%]

============================= 12 passed in 2.82s ==============================
```

#### Command 2: Tier 1 Feature Tests (Monorepo Layout & Quantum Modularization)
```pwsh
pytest -v tests/e2e/test_tier1_feature.py -k "TestFeature01 or TestFeature02"
```
**Exact Output**:
```text
============================= test session starts =============================
platform win32 -- Python 3.10.11, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\hp\AppData\Local\Programs\Python\Python310\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\hp\Desktop\plaq-os
configfile: pytest.ini
plugins: cov-7.1.0, anyio-4.15.1
collecting ... collected 80 items / 70 deselected / 10 selected

tests/e2e/test_tier1_feature.py::TestFeature01MonorepoStructure::test_f1_01_top_level_directories_exist PASSED [ 10%]
tests/e2e/test_tier1_feature.py::TestFeature01MonorepoStructure::test_f1_02_apps_subdirectories PASSED [ 20%]
tests/e2e/test_tier1_feature.py::TestFeature01MonorepoStructure::test_f1_03_packages_subdirectories PASSED [ 30%]
tests/e2e/test_tier1_feature.py::TestFeature01MonorepoStructure::test_f1_04_services_subdirectories PASSED [ 40%]
tests/e2e/test_tier1_feature.py::TestFeature01MonorepoStructure::test_f1_05_shared_subdirectories PASSED [ 50%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_01_package_metadata_and_structure PASSED [ 60%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_02_circuit_workload_generation PASSED [ 70%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_03_cost_model_t_count_and_depth PASSED [ 80%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_04_stim_rotated_surface_code_simulation PASSED [ 90%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_05_multi_objective_pareto_optimizer PASSED [100%]

================ 10 passed, 70 deselected, 2 warnings in 2.53s ================
```

#### Command 3: Full Tier 1 Feature Suite Run
```pwsh
pytest tests/e2e/test_tier1_feature.py
```
**Exact Output**:
```text
================= 77 passed, 3 skipped, 2 warnings in 34.40s ==================
```

### 1.3 Adversarial Stress Testing Results
Direct stress-testing was conducted on boundary conditions and failure modes:
1. **Schema Validation Enforcement**:
   - `Task(goal="valid", status="flying")` -> Rejected with `ValidationError` (illegal enum value).
   - `Task(goal="")` -> Rejected with `ValidationError` (`min_length=1`).
   - `ArtifactRecord(sha256_hash="short", ...)` -> Rejected with `ValidationError` (length != 64).
   - `ArtifactRecord(size_bytes=-1, ...)` -> Rejected with `ValidationError` (`ge=0`).
   - `QuantumEstimateRequest(physical_error_rate=1.5)` -> Rejected with `ValidationError` (`lt=1.0`).
   - `PlanStep(step_number=0, ...)` -> Rejected with `ValidationError` (`ge=1`).
   - `ToolDefinition(timeout_sec=-5, ...)` -> Rejected with `ValidationError` (`gt=0`).
2. **JSON Serialization Roundtrip**:
   - `Task` instantiated with nested dictionaries and timestamps serialized via `.model_dump_json()` and reconstructed via `Task.model_validate_json()` yielded an identical copy with 100% field equality.
3. **Remote HTTP Client Mock Execution**:
   - `PlaqClient.remote_client` configured with `httpx.MockTransport` successfully routed `health()`, `create_task()`, and `get_task()` requests to their corresponding API paths and correctly parsed JSON response payloads into Pydantic models.

---

## 2. Logic Chain

1. **Integrity & Authenticity Assessment**:
   - Source code in `packages/contracts` and `packages/sdk-python` was audited for cheating patterns (hardcoded strings, mock shortcuts, dummy implementations).
   - `ControlPlaneRepository` performs genuine SQLite queries with transactions (`BEGIN IMMEDIATE;`, `COMMIT;`, `ROLLBACK;`).
   - `PlaqClient` local mode genuinely executes against the control plane SQLite database and imports `plaq_quantum.cost_model.solve_minimum_code_distance`.
   - `PlaqClient` remote mode utilizes standard `httpx.Client` request methods and SSE event generators.
   - **Conclusion**: There are **zero integrity violations**. All implementations are authentic and fully functional.

2. **Contract Architecture & Pydantic v2 Conformance**:
   - Observation 1.1 reveals that database rows from SQLite contain serialized JSON strings (e.g. `'{"d": 3}'`).
   - Using `@field_validator(..., mode="before")` on dictionary fields (`parameters`, `modified_files`, `metadata`) provides seamless database-to-model hydration without manual deserialization layers in client or repository code.
   - In `PlaqBaseModel`, `use_enum_values=True` combined with string enums (`class TaskStatus(str, Enum)`) ensures that `task.status == "running"` and `task.status == TaskStatus.RUNNING` both evaluate to `True`.

3. **SDK Client Dual-Mode Architecture**:
   - The dual-mode client design (`local=True` vs `local=False`) enables developer tests, local CLI commands, and detached backend services to use a single unified programming interface (`PlaqClient`).
   - Remote client error handling correctly checks for HTTP 404 (`get_task` returns `None`) and calls `raise_for_status()` on failed requests, propagating standard HTTP exceptions.

---

## 3. Caveats & Adversarial Findings

1. **Local Mode Quantum Engine Absence Fallthrough (Minor)**:
   - *Location*: `packages/sdk-python/src/plaq_sdk/client.py`, lines 263-278.
   - *Behavior*: In `estimate_quantum()`, if `self.local` is `True` but `self._quantum` is `None` (e.g. quantum engine dependency not installed), execution falls through to `assert self._client is not None`. Because `self._client` is `None` in local mode, this raises an uninformative `AssertionError` rather than a descriptive `RuntimeError("Quantum engine is not available in local mode")` (similar to how database methods raise `RuntimeError("Local client requires an initialized database.")`).
   - *Severity*: Minor / non-blocking. In standard environments `plaq_quantum` is present.
   - *Recommendation*: In Milestone M4, update `estimate_quantum()` to explicitly check `if not self._quantum: raise RuntimeError("Local quantum engine is not available")`.

2. **WebSocket Client Method Not Yet Exposed in SDK (Minor / Planned for M4)**:
   - *Location*: `packages/sdk-python/src/plaq_sdk/client.py`.
   - *Behavior*: `pyproject.toml` lists `websockets>=12.0` and client docstrings mention WebSocket access, but `PlaqClient` currently implements event streaming via Server-Sent Events (`stream_events` over `/api/v1/events/stream`). A dedicated bidirectional WebSocket client helper (e.g., `connect_ws()`) is not yet exposed on `PlaqClient`.
   - *Severity*: Minor / non-blocking. Milestone M4 is responsible for building the FastAPI backend with the `/ws/stream` WebSocket endpoint.
   - *Recommendation*: Implement `PlaqClient.connect_websocket()` during Milestone M4 when the WebSocket broadcaster is delivered.

3. **Local In-Process Event Streaming (Minor)**:
   - *Location*: `packages/sdk-python/src/plaq_sdk/client.py`, lines 288-289.
   - *Behavior*: `stream_events()` returns an empty generator in local in-process mode because there is no background HTTP event server running.
   - *Severity*: Minor / non-blocking. Documented as an intended architectural boundary between local repository access and network streaming.

---

## 4. Conclusion

The Milestone M2 packages (`packages/contracts` and `packages/sdk-python`) meet all architectural, schema, and operational requirements specified in `ORIGINAL_REQUEST.md` and `PROJECT.md`.
- All Pydantic v2 schemas and 8-state / 6-tier enums are correctly defined and strictly validated.
- Clean package exports and serialization/deserialization fidelity are confirmed.
- `PlaqClient` successfully delegates to the local repository and properly prepares the remote HTTP/SSE client structure.
- 100% of required and relevant tests pass with zero failures.
- No integrity violations or shortcuts were found.

**Final Verdict**: **APPROVE**

---

## 5. Verification Method

To independently verify this review and reproduce all results from the project root (`C:\Users\hp\Desktop\plaq-os`):

1. **Run Contracts & SDK Unit Tests**:
   ```pwsh
   pytest -v tests/test_plaq_contracts.py tests/test_plaq_sdk.py
   ```
   *Expected*: `12 passed in ~2.8s`.

2. **Run Monorepo Layout & Quantum Tests**:
   ```pwsh
   pytest -v tests/e2e/test_tier1_feature.py -k "TestFeature01 or TestFeature02"
   ```
   *Expected*: `10 passed, 70 deselected in ~2.5s`.

3. **Verify Pydantic Validation Constraints**:
   ```pwsh
   python -c "import plaq_bootstrap; from plaq_contracts import Task, TaskStatus; t = Task(goal='test', status=TaskStatus.RUNNING); assert t.status == TaskStatus.RUNNING; print('OK')"
   ```
   *Expected*: Prints `OK`.

4. **Verify Remote HTTP Mock Client**:
   ```pwsh
   python -c "import plaq_bootstrap, httpx; from plaq_sdk import PlaqClient; client = PlaqClient.remote_client(); print(client.base_url)"
   ```
   *Expected*: Prints `http://127.0.0.1:8000`.
