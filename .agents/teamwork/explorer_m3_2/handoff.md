# Investigation & Architecture Report: Feature 18 (Typed Tool Registry & Domain Tools)

**Author**: Explorer M3-2 (`explorer_m3_2`)  
**Mission**: Investigate and design the 6-tier typed tool registry and 12 built-in tools for Plaq-OS.  
**Project Root**: `C:\Users\hp\Desktop\plaq-os`  
**Working Directory**: `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m3_2`  
**Date**: 2026-10-14  

---

## 1. Observation

### 1.1 Requirements Analysis (`ORIGINAL_REQUEST.md § R3` & Feature 18)
The Plaq-OS architecture requires an isolated AI agent runtime featuring a typed tool registry with strict permission boundaries and audit logging. Specifically:
- **6 Permission Tiers**:
  1. `read_only`: Non-mutating inspection of workspace filesystem.
  2. `workspace_write`: Workspace-scoped file creation, modification, and patching.
  3. `git_isolated`: Git operations confined to the repository or isolated worktrees (`.worktrees/<task_id>`).
  4. `process_sandbox`: Subprocess command execution with timeouts and process tree termination.
  5. `quantum_engine`: Fault-tolerant circuit synthesis, resource estimation, and stabilizer simulation.
  6. `privileged`: High-stakes operations requiring explicit authorization (e.g., publishing artifacts, destructive operations).
- **12 Canonical Built-In Tools**:
  1. `workspace.list` (`read_only`): List directory contents safely within workspace.
  2. `workspace.read` (`read_only`): Read file safely via `PathGuard`.
  3. `workspace.patch` (`workspace_write`): Apply unified diff or replace substring safely.
  4. `workspace.write` (`workspace_write`): Write/create file safely via `PathGuard` with SHA-256 fingerprinting.
  5. `git.diff` (`git_isolated`): Run git diff in workspace or worktree.
  6. `git.branch` (`git_isolated`): Check or create git branch.
  7. `terminal.run` (`process_sandbox`): Execute sandboxed shell command via `ProcessRunner`.
  8. `tests.run` (`process_sandbox`): Run pytest / test runner within workspace via `ProcessRunner`.
  9. `quantum.compile` (`quantum_engine`): Wrap `plaq_quantum` circuits and T-count synthesis.
  10. `quantum.estimate` (`quantum_engine`): Wrap `plaq_quantum.cost_model` resource estimation and code distance solver.
  11. `quantum.simulate` (`quantum_engine`): Wrap `plaq_quantum.stim_bridge` rotated surface code stabilizer simulation and PyMatching MWPM decoding.
  12. `artifacts.publish` (`privileged`): Wrap `plaq_artifacts.ArtifactService.publish_artifact` to store and link content-addressable artifacts.

### 1.2 Existing Contracts (`packages/contracts/src/plaq_contracts/tool.py`)
Direct code inspection confirms the canonical contract definitions:
- `PermissionTier` enum:
  - `READ_ONLY = "read_only"`
  - `WORKSPACE_WRITE = "workspace_write"`
  - `GIT_ISOLATED = "git_isolated"`
  - `PROCESS_SANDBOX = "process_sandbox"`
  - `QUANTUM_ENGINE = "quantum_engine"`
  - `PRIVILEGED = "privileged"`
- `DEFAULT_TOOL_TIERS` mapping:
  - Matches all 12 tools to their exact permission tier.
- `ToolDefinition`: Pydantic model with `name`, `description`, `tier`, `parameters_schema`, `requires_approval`, `timeout_sec`.
- `ToolRequest`: Pydantic model with `tool_name`, `parameters` (auto-parses stringified JSON), `task_id`, `step_id`, `request_id`.
- `ToolResult`: Pydantic model with `success`, `output`, `error`, `duration_ms`, `exit_code`, `modified_files` (auto-parses JSON list).
- `AuditRecord`: Pydantic model with cryptographic hash fields `previous_hash` and `current_hash`.

### 1.3 Test Expectations & E2E Validation Findings
Inspection of `tests/e2e/test_tier1_feature.py`, `test_tier2_boundary.py`, `test_tier3_pairwise.py`, and `test_tier4_workloads.py` revealed:
- `TestFeature11TypedToolRegistry` (lines 707-750 of `test_tier1_feature.py`) explicitly validates:
  - `workspace.list` and `workspace.read` belong to `"read_only"` tier.
  - `workspace.patch` and `workspace.write` belong to `"workspace_write"` tier.
  - `git.diff` and `git.branch` belong to `"git_isolated"` tier.
  - `terminal.run` and `tests.run` belong to `"process_sandbox"` tier.
  - `quantum.compile`, `quantum.estimate`, and `quantum.simulate` belong to `"quantum_engine"` tier.
  - `artifacts.publish` belongs to `"privileged"` tier.
- `TestScenario01FullLifecycle` (lines 50-140 of `test_tier4_workloads.py`) validates:
  - Tool invocations chain in order: `quantum.compile` -> `quantum.estimate` -> `artifacts.publish`.
  - Secrets in tool output (e.g., `Authorization: Bearer secret-agent-token-999-xyz`) are scrubbed before logging in `audit_trail` (`Bearer [REDACTED_TOKEN]`).
  - Modified files are tracked (`["bv_resource_report.json"]`).
- `TestPairwise02SandboxRuntimeIntegration` (lines 150-260 of `test_tier3_pairwise.py`) validates:
  - `terminal.run` output with JWT tokens is scrubbed in audit records (`test_p2_01`).
  - `terminal.run` exceeding timeout produces `exit_code = -1` and records `"Execution timed out after ..."` (`test_p2_02`).
  - `workspace.read` rejecting path traversal raises `PathTraversalError` and records failure in audit (`test_p2_03`).
  - Environment variables passed to tools have sensitive keys (`API_KEY`, `AWS_SECRET`) redacted to `[REDACTED]` in logged parameters (`test_p2_04`).
  - `workspace.write` computes file SHA-256 and records it in audit output and `modified_files` (`test_p2_05`).
- `TestScenario03CheckpointRecoveryWorkflow` (lines 235-295 of `test_tier4_workloads.py`) validates:
  - `quantum.simulate` executions with `code_distance` and `rounds` succeed, return 0 errors, and record in unbroken audit trail.

---

## 2. Logic Chain

### 2.1 Architecture of `ToolRegistry` (`src/plaq_agent_runtime/registry.py`)
To satisfy the requirements of Feature 18, `ToolRegistry` must act as the centralized execution broker with the following sequence:

```text
[Agent Loop / Client]
         │  ToolRequest (tool_name, parameters, task_id)
         ▼
┌────────────────────────────────────────────────────────┐
│                     ToolRegistry                       │
│  1. Tool Lookup: Find registered ToolHandler & schema  │
│  2. Tier Check: Verify tool.tier in allowed_tiers      │
│  3. Schema Validation: Validate parameters vs Pydantic │
│  4. Approval Check: Check if privileged / destructive  │
│  5. Timer: Start high-resolution wall-clock timer      │
│  6. Dispatch Handler: Call tool handler implementation │
│  7. Duration & Error Normalization: Build ToolResult   │
│  8. Audit & Secret Scrubbing: Redact & log to DB       │
└────────────────────────────────────────────────────────┘
         │  ToolResult (success, output, error, duration_ms, exit_code, modified_files)
         ▼
[Agent Loop / State Machine]
```

### 2.2 Execution Context (`ToolContext`)
Tool handlers require context about their operational environment. We define a typed `ToolContext`:
```python
@dataclass
class ToolContext:
    workspace_path: Path
    task_id: str
    step_id: Optional[str] = None
    sandbox_manager: Optional[Any] = None  # Or PathGuard / ProcessRunner
    artifact_service: Optional[Any] = None
    control_plane: Optional[Any] = None    # Database or repository for audit logs
    allowed_tiers: Optional[Set[PermissionTier]] = None
    extra: Dict[str, Any] = field(default_factory=dict)
```

### 2.3 Parameter Validation Pattern
Each tool must define a Pydantic model for its parameters. `ToolRegistry.execute()` performs:
```python
try:
    validated_params = tool_entry.param_model(**request.parameters)
except ValidationError as val_err:
    return ToolResult(
        success=False,
        output="",
        error=f"Parameter validation failed for tool '{request.tool_name}': {val_err}",
        exit_code=1,
        duration_ms=0.0,
        modified_files=[],
    )
```
This guarantees type safety, rejects unexpected or malformed inputs, applies default values, and prevents injection.

### 2.4 Audit Trail & Secret Scrubbing Integration
To guarantee non-repudiation and prevent data leakage:
1. `ToolRegistry` calls `SecretRedactor.redact_json(request.parameters)` before logging parameters.
2. `ToolRegistry` calls `SecretRedactor.redact_text(result.output)` before logging output.
3. If `context.control_plane` is configured with `record_audit()`, the registry invokes:
   ```python
   context.control_plane.record_audit(
       task_id=context.task_id,
       tool_name=request.tool_name,
       parameters=redacted_params,
       output=redacted_output,
       exit_code=result.exit_code or (0 if result.success else 1),
       duration_ms=duration_ms,
       modified_files=result.modified_files,
   )
   ```
4. Cryptographic hash chaining is automatically preserved by the control plane's `AuditChainer`.

### 2.5 Detailed Design of the 12 Domain Tools

#### Group 1: Workspace Tools (`src/plaq_agent_runtime/tools/workspace_tools.py`)
- **`workspace.list`** (`PermissionTier.READ_ONLY`):
  - Parameters: `path: str = "."`, `recursive: bool = False`, `max_depth: int = 3`, `include_hidden: bool = False`.
  - Logic:
    1. `target = PathGuard.resolve_safe_path(context.workspace_path, path)`
    2. If not `target.is_dir()`, raise `NotADirectoryError`.
    3. Traverses entries up to `max_depth`, collecting name, relative path, type (`file` / `dir`), size, and mtime.
    4. Returns JSON string of entries. `modified_files = []`.
- **`workspace.read`** (`PermissionTier.READ_ONLY`):
  - Parameters: `path: str`, `start_line: Optional[int] = None`, `end_line: Optional[int] = None`, `encoding: str = "utf-8"`.
  - Logic:
    1. `target = PathGuard.resolve_safe_path(context.workspace_path, path)`
    2. Reads text with specified encoding.
    3. If `start_line` or `end_line` specified (1-indexed), slices lines.
    4. Returns text content. `modified_files = []`.
- **`workspace.write`** (`PermissionTier.WORKSPACE_WRITE`):
  - Parameters: `path: str`, `content: str`, `encoding: str = "utf-8"`, `create_parents: bool = True`.
  - Logic:
    1. `target = PathGuard.resolve_safe_path(context.workspace_path, path)`
    2. If `create_parents`, calls `target.parent.mkdir(parents=True, exist_ok=True)`.
    3. Writes content atomically (write to temp file in same directory, then atomic rename).
    4. Computes SHA-256 fingerprint: `sha256 = hashlib.sha256(content.encode(encoding)).hexdigest()`.
    5. Returns `f"Wrote {len(content)} bytes, sha256={sha256}"`.
    6. Returns `modified_files = [str(target.relative_to(context.workspace_path))]`.
- **`workspace.patch`** (`PermissionTier.WORKSPACE_WRITE`):
  - Parameters: `path: str`, `diff: Optional[str] = None`, `target: Optional[str] = None`, `replacement: Optional[str] = None`, `allow_multiple: bool = False`.
  - Logic:
    1. `file_path = PathGuard.resolve_safe_path(context.workspace_path, path)`
    2. If `target` and `replacement` given: reads file, checks occurrences. If not found or occurs multiple times without `allow_multiple`, raises `ValueError`. Applies substring replacement.
    3. If unified `diff` given: applies patch hunks cleanly.
    4. Writes file and recalculates SHA-256.
    5. Returns `f"Patched {path}, sha256={sha256}"`.
    6. Returns `modified_files = [str(file_path.relative_to(context.workspace_path))]`.

#### Group 2: Git Tools (`src/plaq_agent_runtime/tools/git_tools.py`)
- **`git.diff`** (`PermissionTier.GIT_ISOLATED`):
  - Parameters: `target: Optional[str] = None`, `cached: bool = False`, `worktree_path: Optional[str] = None`, `commit: Optional[str] = None`.
  - Logic:
    1. Resolves directory: `worktree_path` (if provided, validated via PathGuard) or `context.workspace_path`.
    2. Builds command: `["git", "diff"]` with `--cached`, `commit`, and `-- <target>`.
    3. Executes via `ProcessRunner` or `subprocess.run`.
    4. Returns diff output.
- **`git.branch`** (`PermissionTier.GIT_ISOLATED`):
  - Parameters: `action: str = "list"`, `branch_name: Optional[str] = None`, `worktree_path: Optional[str] = None`.
  - Logic:
    1. Resolves working directory.
    2. If `action == "current"`: runs `git branch --show-current`.
    3. If `action == "list"`: runs `git branch --list`.
    4. If `action == "create"`: validates `branch_name` and runs `git branch <name>`.
    5. Returns branch name/list.

#### Group 3: Terminal & Test Tools (`src/plaq_agent_runtime/tools/terminal_tools.py`)
- **`terminal.run`** (`PermissionTier.PROCESS_SANDBOX`):
  - Parameters: `cmd: Union[str, List[str]]`, `timeout_sec: float = 30.0`, `cwd: Optional[str] = None`, `env: Optional[Dict[str, str]] = None`, `shell: bool = False`.
  - Logic:
    1. Resolves `cwd` via `PathGuard.resolve_safe_path(context.workspace_path, cwd or ".")`.
    2. Detects destructive patterns (e.g. `rm -rf`, `git clean -fdx`, `dropdb`) to notify approval gate if configured.
    3. Invokes `ProcessRunner.run()` (or safe subprocess execution with `taskkill /F /T` tree-kill on Windows).
    4. Handles timeout: returns `ToolResult(success=False, output=f"Execution timed out after {timeout_sec}s", exit_code=-1)`.
    5. Returns stdout/stderr and exit code.
- **`tests.run`** (`PermissionTier.PROCESS_SANDBOX`):
  - Parameters: `test_path: Optional[str] = None`, `args: List[str] = Field(default_factory=list)`, `timeout_sec: float = 60.0`.
  - Logic:
    1. Resolves `test_path` safely within workspace.
    2. Builds command: `[sys.executable, "-m", "pytest", str(test_path)] + args`.
    3. Runs via `ProcessRunner`.
    4. Formats test results and returns `ToolResult`.

#### Group 4: Quantum Tools (`src/plaq_agent_runtime/tools/quantum_tools.py`)
- **`quantum.compile`** (`PermissionTier.QUANTUM_ENGINE`):
  - Parameters: `workload: Optional[str] = None`, `qubits: Optional[int] = None`, `bitstring: Optional[str] = None`, `qasm: Optional[str] = None`, `rotation_angle: Optional[float] = None`, `synth_precision: float = 1e-10`.
  - Logic:
    1. If `rotation_angle` is provided: calls `plaq_quantum.cost_model.synthesize_rotation_t_count(rotation_angle, synth_precision)`. Returns synthesized T-count.
    2. If `workload` is provided: resolves generator in `plaq_quantum.circuits` (e.g., `make_bernstein_vazirani_circuit(bitstring or "101")`, `make_qaoa_circuit(qubits or 6)`, `make_test_circuit(qubits or 4)`).
    3. Extracts circuit metrics via `plaq_quantum.cost_model.extract_circuit_metrics(qc)`.
    4. Returns JSON: `num_qubits`, `depth`, `t_ops`, `t_depth`, `total_ops`, `synthesis_t_count`.
- **`quantum.estimate`** (`PermissionTier.QUANTUM_ENGINE`):
  - Parameters: `hardware_profile: str = "superconducting_heron"`, `code_distance: Optional[int] = None`, `physical_error: Optional[float] = None`, `target_epsilon: float = 1e-3`, `num_qubits: int = 5`, `t_count: int = 100`, `t_depth: int = 50`, `circuit_depth: int = 100`, `spacetime_volume: Optional[int] = None`.
  - Logic:
    1. Loads `HardwareModel` via `plaq_quantum.hardware.get_hardware_profile(hardware_profile)`.
    2. If `code_distance` is not provided: calls `plaq_quantum.cost_model.solve_minimum_code_distance(...)`.
    3. Calls `plaq_quantum.cost_model.evaluate_fault_tolerant_cost(...)`.
    4. Returns JSON: `feasible`, `feasibility_reason`, `code_distance`, `physical_qubits`, `runtime_seconds`, `failure_probability`.
- **`quantum.simulate`** (`PermissionTier.QUANTUM_ENGINE`):
  - Parameters: `code_distance: int = 3`, `physical_error_rate: float = 0.001`, `shots: int = 1000`, `rounds: Optional[int] = None`, `seed: int = 42`.
  - Logic:
    1. Validates `code_distance` is an odd integer >= 3. If invalid (even or < 3), raises `ValueError("Surface code distance d must be an odd integer >= 3.")` -> returns `exit_code = 1`.
    2. Calls `plaq_quantum.stim_bridge.run_surface_code_simulation(code_distance, physical_error_rate, shots, rounds, seed)` (or `StimSurfaceCodeSimulator`).
    3. Returns JSON serialization of `ThresholdSampleResult`: `code_distance`, `physical_error_rate`, `total_shots`, `logical_errors`, `empirical_logical_error_rate`, `confidence_interval_95`, `decoder_type`.

#### Group 5: Artifact Tools (`src/plaq_agent_runtime/tools/artifact_tools.py`)
- **`artifacts.publish`** (`PermissionTier.PRIVILEGED`):
  - Parameters: `file: Optional[str] = None`, `name: Optional[str] = None`, `content: Optional[Union[str, bytes]] = None`, `artifact_type: str = "report"`, `metadata: Optional[Dict[str, Any]] = None`.
  - Logic:
    1. If `file` is provided: resolves safe path via `PathGuard.resolve_safe_path(context.workspace_path, file)`. Reads file content and sets `name = name or Path(file).name`.
    2. Invokes `ArtifactService.publish_artifact(task_id=context.task_id, artifact_type=artifact_type, name=name, content=content, metadata=metadata)`.
    3. Computes SHA-256 fingerprint and saves to content-addressable storage.
    4. Returns summary: `f"Artifact published: id={record.id}, name={record.name}, sha256={record.sha256_hash}, size_bytes={record.size_bytes}"`.
    5. Returns `modified_files = [file]` if file was published from workspace.

---

## 3. Caveats & Edge Cases

1. **Parameter Schema Coercion**:
   - `ToolRequest.parameters` can arrive as a pre-parsed dictionary or as a stringified JSON blob (common in HTTP payloads and LLM outputs). `ToolRequest.parse_params` normalizes this, but `ToolRegistry` must also safely handle both dictionary and model instance inputs.
2. **Secret Scrubbing Before Persistence**:
   - Secret redaction must happen **before** persisting parameters or outputs to `audit_trail`. Redaction after insertion invalidates the SHA-256 cryptographic hash chain because recalculating the hash on redacted data would not match the raw hash.
   - All tool outputs and parameters must pass through `SecretRedactor` prior to computing `AuditChainer.compute_record_hash()`.
3. **Windows Process-Tree Kill**:
   - On Windows, terminating a parent process via standard `terminate()` or `kill()` leaves orphaned child processes running (e.g., Python spawning child commands).
   - In `terminal_tools.py`, process termination on Windows must use `taskkill /F /T /PID <pid>` to terminate the entire process hierarchy cleanly.
4. **Windows File Locks**:
   - On Windows (`nt`), files opened for reading or writing cannot be deleted, renamed, or overwritten if another file handle is still open. All file operations in `workspace_tools.py` must use `with open(...)` or `Path.read_text()` / `write_bytes()` so that OS handles are closed immediately.
5. **Stim / PyMatching Fallback**:
   - If Stim or PyMatching is not installed or running in a minimal environment, `plaq_quantum.stim_bridge` includes a statistical fallback ansatz. The tool wrapper must handle both genuine and fallback simulations gracefully without crashing.
6. **Path Traversal Defenses**:
   - Traversal attempts (`../../`, `%2e%2e%2f`, embedded null bytes `\0`, absolute paths `C:\Windows`) must be rejected immediately via `PathGuard.resolve_safe_path()`, raising `PathTraversalError`, returning `exit_code = 1`, and recording the rejection in the audit trail without touching the filesystem.

---

## 4. Conclusion & Interface Design

The typed tool registry and built-in tools form the operational execution backbone of Plaq-OS. The architecture guarantees:
- **Strict Permission Boundaries**: 6 well-defined tiers enforced before any handler is invoked.
- **Strong Typing**: Pydantic v2 schemas for all parameters and outputs.
- **Deterministic Auditing**: Automatic secret redaction and cryptographic SHA-256 hash chaining on every tool call.
- **Fail-Safe Sandboxing**: Confinement within workspace roots via `PathGuard` and process tree timeouts via `ProcessRunner`.

### 4.1 Target Code Layout in `services/agent-runtime/`
```text
services/agent-runtime/
├── pyproject.toml
└── src/
    └── plaq_agent_runtime/
        ├── __init__.py
        ├── registry.py
        └── tools/
            ├── __init__.py
            ├── workspace_tools.py
            ├── git_tools.py
            ├── terminal_tools.py
            ├── quantum_tools.py
            └── artifact_tools.py
```

### 4.2 Module Export Interface (`src/plaq_agent_runtime/__init__.py`)
```python
from .registry import (
    ToolRegistry,
    ToolContext,
    ToolEntry,
    create_default_tool_registry,
)
from .tools.workspace_tools import (
    workspace_list,
    workspace_read,
    workspace_write,
    workspace_patch,
)
from .tools.git_tools import git_diff, git_branch
from .tools.terminal_tools import terminal_run, tests_run
from .tools.quantum_tools import (
    quantum_compile,
    quantum_estimate,
    quantum_simulate,
)
from .tools.artifact_tools import artifacts_publish

__all__ = [
    "ToolRegistry",
    "ToolContext",
    "ToolEntry",
    "create_default_tool_registry",
    "workspace_list",
    "workspace_read",
    "workspace_write",
    "workspace_patch",
    "git_diff",
    "git_branch",
    "terminal_run",
    "tests_run",
    "quantum_compile",
    "quantum_estimate",
    "quantum_simulate",
    "artifacts_publish",
]
```

---

## 5. Verification Method

### 5.1 Verification Commands
Workers can independently verify implementation using the following pytest commands:

1. **Verify Tool Registry Tier Mapping**:
   ```bash
   pytest tests/e2e/test_tier1_feature.py -k TestFeature11TypedToolRegistry -v
   ```
2. **Verify Tool Auditing & Secret Scrubbing in Scenarios**:
   ```bash
   pytest tests/e2e/test_tier4_workloads.py -k "test_s1_full_agent_task_lifecycle" -v
   ```
3. **Verify Sandbox Runtime & Pairwise Integration**:
   ```bash
   pytest tests/e2e/test_tier3_pairwise.py -k "TestPairwise02SandboxRuntimeIntegration" -v
   ```
4. **Verify Boundary Defenses (PathGuard & Process Termination)**:
   ```bash
   pytest tests/e2e/test_tier2_boundary.py -k "TestBoundary01PathTraversal or TestBoundary04ProcessTermination" -v
   ```

### 5.2 Invalidation Conditions
The design is invalidated if:
- Any tool executes outside the workspace root or bypasses `PathGuard`.
- Unscrubbed secrets (API tokens, AWS keys, Bearer tokens) appear in `audit_trail`.
- Any of the 12 tools maps to an incorrect permission tier.
- A tool execution crashes the Python runtime instead of returning a normalized `ToolResult(success=False, error=...)`.

---

## 6. Worker Action Plan

The following implementation steps are ready for worker execution:

### Step 1: Create `services/agent-runtime/pyproject.toml`
Define package metadata, setuptools package finder, and dependencies on `plaq-contracts`, `plaq-sandbox`, `plaq-control-plane`, `plaq-artifacts`, and `plaq-quantum`.

### Step 2: Implement `src/plaq_agent_runtime/registry.py`
1. Define `ToolContext` dataclass (workspace path, task ID, control plane, sandbox manager, artifact service, allowed tiers).
2. Define `ToolEntry` holding `ToolDefinition`, handler callable, and parameter Pydantic model.
3. Implement `ToolRegistry`:
   - `register(definition, handler, param_model)`
   - `register_decorator(name, tier, description, ...)`
   - `get_tool(name)`
   - `list_tools()`
   - `get_tier_map()`
   - `execute(request: ToolRequest, context: ToolContext) -> ToolResult`:
     - Permission tier check against `context.allowed_tiers`.
     - Parameter validation against `param_model`.
     - Exception wrapping (`PathTraversalError`, `TimeoutExpired`, `Exception`).
     - Duration measurement.
     - Secret scrubbing and audit trail logging via `context.control_plane.record_audit()`.
4. Implement `create_default_tool_registry()` registering all 12 tools.

### Step 3: Implement `src/plaq_agent_runtime/tools/workspace_tools.py`
1. Define Pydantic parameter schemas: `WorkspaceListParams`, `WorkspaceReadParams`, `WorkspaceWriteParams`, `WorkspacePatchParams`.
2. Implement handlers:
   - `workspace_list(params, context) -> ToolResult`
   - `workspace_read(params, context) -> ToolResult`
   - `workspace_write(params, context) -> ToolResult`
   - `workspace_patch(params, context) -> ToolResult`
3. Ensure atomic file writes, SHA-256 fingerprinting, line slicing, and `PathGuard` confinement.

### Step 4: Implement `src/plaq_agent_runtime/tools/git_tools.py`
1. Define Pydantic parameter schemas: `GitDiffParams`, `GitBranchParams`.
2. Implement handlers:
   - `git_diff(params, context) -> ToolResult`
   - `git_branch(params, context) -> ToolResult`
3. Support execution in workspace or `.worktrees/<task_id>` directories.

### Step 5: Implement `src/plaq_agent_runtime/tools/terminal_tools.py`
1. Define Pydantic parameter schemas: `TerminalRunParams`, `TestsRunParams`.
2. Implement handlers:
   - `terminal_run(params, context) -> ToolResult`
   - `tests_run(params, context) -> ToolResult`
3. Integrate with `ProcessRunner` (or Windows-safe subprocess execution with `taskkill /F /T` tree-kill).
4. Return exit code -1 on timeout with descriptive message.

### Step 6: Implement `src/plaq_agent_runtime/tools/quantum_tools.py`
1. Define Pydantic parameter schemas: `QuantumCompileParams`, `QuantumEstimateParams`, `QuantumSimulateParams`.
2. Implement handlers:
   - `quantum_compile(params, context) -> ToolResult`: Ross-Selinger T-synthesis and circuit metrics extraction.
   - `quantum_estimate(params, context) -> ToolResult`: Code distance solver and hardware fault-tolerant cost estimation.
   - `quantum_simulate(params, context) -> ToolResult`: Stim rotated surface code stabilizer simulation and PyMatching MWPM decoding. Validate odd distance >= 3.
3. Clean JSON output formatting.

### Step 7: Implement `src/plaq_agent_runtime/tools/artifact_tools.py`
1. Define Pydantic parameter schema: `ArtifactPublishParams`.
2. Implement handler:
   - `artifacts_publish(params, context) -> ToolResult`
3. Integrate with `ArtifactService.publish_artifact()`, saving content-addressable files and returning SHA-256 fingerprint.

### Step 8: Package Initialization & Exports
1. Create `src/plaq_agent_runtime/tools/__init__.py` exporting all 12 tool handlers.
2. Create `src/plaq_agent_runtime/__init__.py` exporting `ToolRegistry`, `ToolContext`, `create_default_tool_registry`, and all tool handlers.
