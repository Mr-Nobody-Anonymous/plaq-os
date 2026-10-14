## 2026-10-14T11:20:49Z

You are Worker M1 (Monorepo & Quantum Modularization Worker) for Plaq-OS.
Your working directory is: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\worker_m1_1
The project root is: C:\Users\hp\Desktop\plaq-os
The authoritative original user request is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\ORIGINAL_REQUEST.md
The project master plan is at: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\orchestrator_1\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

SCOPE & OBJECTIVES:
Execute Milestone M1 (Requirement R1: Full Monorepo Architecture & Quantum Engine Modularization):
1. Create the complete production-grade monorepo directory layout:
   - `apps/api`
   - `apps/cli`
   - `apps/workbench`
   - `packages/contracts`
   - `packages/sdk-python`
   - `services/control-plane`
   - `services/agent-runtime`
   - `services/sandbox-manager`
   - `services/model-gateway`
   - `services/artifact-service`
   - `engines/quantum/`
   - `shared/schemas`, `shared/policies`, `shared/prompts`
2. Modularize the quantum computing co-design engine into `engines/quantum/`:
   - Create `engines/quantum/pyproject.toml` (package `plaq-quantum` version 0.3.0).
   - Create `engines/quantum/src/plaq_quantum/` containing:
     `__init__.py`, `circuits.py`, `hardware.py`, `cost_model.py`, `stim_bridge.py`, `optimizer.py`, `baselines.py`, `search_algorithms.py`, and `benchmark.py`.
   - In `engines/quantum/src/plaq_quantum/__init__.py`, export all key classes and functions.
   - Update internal imports within `plaq_quantum` so they import cleanly (e.g., `from plaq_quantum.circuits import ...` or relative imports `from .circuits import ...`, with fallback to flat imports if needed).
   - Colocate tests in `engines/quantum/tests/`:
     `conftest.py`, `test_baselines.py`, `test_circuits.py`, `test_cost_model.py`, `test_hardware.py`, `test_optimizer.py`, `test_search_algorithms.py`, `test_stim_bridge.py`.
3. Provide root-level backward compatibility and bootstrap import hooks:
   - Create `plaq_bootstrap.py` at root that configures `sys.path` to include `engines/quantum/src` and all upcoming package directories.
   - At repository root, create/update shim modules (`circuits.py`, `hardware.py`, `cost_model.py`, `stim_bridge.py`, `optimizer.py`, `baselines.py`, `search_algorithms.py`, `benchmark.py`) that import and re-export everything from `plaq_quantum` (e.g., `from plaq_quantum.circuits import *`).
   - Add/update root `conftest.py` ensuring `pytest` executed from root automatically imports `plaq_bootstrap` so legacy imports and new imports resolve seamlessly.
4. VERIFICATION:
   - Run the test suite inside `engines/quantum/`:
     `pytest -v engines/quantum/tests/`
   - Run the test suite from the repository root:
     `pytest -v`
   - Verify that all 38 existing unit tests pass cleanly (100% pass rate) in both modes!
   - Document the exact execution commands, outputs, execution times, and exit codes in your report.

FILE OWNERSHIP:
- You exclusively own: `engines/quantum/**`, `plaq_bootstrap.py`, root import shims, root `conftest.py`, root directory skeleton for `apps/`, `packages/`, `services/`, `shared/`.

OUTPUT REQUIREMENTS:
- Maintain your liveness in `progress.md` in your working directory.
- Write your comprehensive completion report to `handoff.md` in your working directory.
- Send a message back to the orchestrator with the summary and path to your handoff.md.
