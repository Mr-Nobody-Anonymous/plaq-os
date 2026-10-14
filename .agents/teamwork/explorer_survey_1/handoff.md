# Codebase & Test Suite Survey Handoff Report
**Explorer**: Explorer Survey 1 (Codebase & Test Explorer)  
**Date**: 2026-10-14  
**Project**: Plaq-OS (C:\Users\hp\Desktop\plaq-os)  
**Target Milestone**: Phase 1 Discovery & Codebase Survey  

---

## 1. Observation

### 1.1 Existing Codebase & Repository Layout
Inspection of `C:\Users\hp\Desktop\plaq-os` reveals a flat quantum co-design research codebase:
- **Root Python Modules** (11 files):
  - `circuits.py` (297 lines, 11,047 bytes): Quantum circuit generators and 8 benchmark algorithm workloads.
  - `hardware.py` (259 lines, 10,683 bytes): Hardware specifications, topology coupling generators, and 5 hardware profiles.
  - `cost_model.py` (382 lines, 15,238 bytes): Analytical fault-tolerant cost model, Ross-Selinger T-gate synthesis, code distance solver, decoder backlog stall model, and qLDPC scaling.
  - `stim_bridge.py` (202 lines, 7,706 bytes): Stim rotated surface code generator, PyMatching MWPM decoder, and Wilson score confidence intervals.
  - `optimizer.py` (475 lines, 17,232 bytes): Candidate execution plan generation, SHA-256 canonical compilation caching, Pareto frontier extraction, and sequential vs. joint comparison.
  - `baselines.py` (252 lines, 10,785 bytes): Four-Baselines comparative protocol (B1-B4) and systematic 5-point layer ablation study.
  - `search_algorithms.py` (375 lines, 13,619 bytes): 4 search heuristics (Exhaustive, Greedy, Random, Simulated Annealing) and benchmark harness.
  - `benchmark.py` (132 lines, 4,701 bytes): Compiler baseline benchmarking across Qiskit optimization levels 0-3.
  - `main.py` (410 lines, 18,664 bytes): Research CLI pipeline runner and manifest generator.
  - `server.py` (226 lines, 9,322 bytes): Python built-in HTTP server exposing REST endpoints (`/api/metadata`, `/api/optimize`, `/api/baselines`, `/api/ablation`, `/api/search-bench`) and UI static serving.
  - `dashboard.py` (270 lines, 11,266 bytes): Standalone HTML executive dashboard generator.
- **Test Suite** (`tests/`, 8 files):
  - `tests/__init__.py` (4 lines)
  - `tests/test_baselines.py` (58 lines)
  - `tests/test_circuits.py` (92 lines)
  - `tests/test_cost_model.py` (124 lines)
  - `tests/test_hardware.py` (62 lines)
  - `tests/test_optimizer.py` (115 lines)
  - `tests/test_search_algorithms.py` (67 lines)
  - `tests/test_stim_bridge.py` (63 lines)
- **UI & Web Assets** (`ui/`, `assets/`):
  - `ui/index.html` (942 lines, 31,379 bytes): Cyber-quantum dashboard interface with Chart.js visualizations.
  - `assets/logo.jpg` and `ui/assets/logo.jpg` (175,644 bytes).
- **Project Configuration & CI**:
  - `pyproject.toml` (26 lines): Declares package `plaq-os` v0.3.0 with setuptools build-backend.
  - `requirements.txt` (10 lines): Core dependencies and test dependencies.
  - `pytest.ini` (4 lines): `addopts = -p no:asyncio`, `testpaths = tests`.
  - `.github/workflows/ci.yml` (36 lines): Matrix CI for Python 3.10, 3.11, 3.12 running `pytest -v --cov=.` and a CLI smoke test.
- **Generated Artifacts** (`results/`):
  - Contains `run_manifest.json`, `benchmark_results.csv`, `dashboard.html`, `hypothesis_comparison.json`, `baselines_comparison.json`, `ablation_study.json`, `search_benchmarks.json`, and PNG plots.

---

### 1.2 Unit Test Enumeration & Execution Results
The test suite was executed in the project root:
- **Command**: `pytest -v`
- **Runner Environment**: Windows win32, Python 3.10.11, pytest-9.1.1, pluggy-1.6.0.
- **Plugins loaded**: cov-7.1.0, anyio-4.15.1.
- **Exit Code**: `0` (Success).
- **Execution Time**: `15.95 seconds`.
- **Status**: Exactly 38 passed out of 38 collected items (100% pass rate).

#### Complete Catalog of 38 Unit Tests:

| # | Test File | Test Case | Functionality Verified |
|---|---|---|---|
| 1 | `tests/test_baselines.py` | `test_four_baselines_protocol` | Verifies execution of baselines B1, B2, B3, B4; ensures physical qubit validity and cost reductions. |
| 2 | `tests/test_baselines.py` | `test_ablation_study` | Validates 5 ablation configurations and verifies penalty increments when decoder, factory, routing, or QEC distance are ablated. |
| 3 | `tests/test_circuits.py` | `test_make_test_circuit` | Verifies 5-qubit test circuit structure containing H, CX, and RZ gates. |
| 4 | `tests/test_circuits.py` | `test_make_qaoa_circuit` | Validates QAOA MaxCut ansatz on cyclic graphs with cost and mixer layers. |
| 5 | `tests/test_circuits.py` | `test_make_qft_circuit` | Verifies Quantum Fourier Transform circuit gate breakdown and swap layers. |
| 6 | `tests/test_circuits.py` | `test_make_bernstein_vazirani_circuit` | Validates Bernstein-Vazirani oracle construction and measurement operations. |
| 7 | `tests/test_circuits.py` | `test_make_random_clifford_t` | Verifies pseudorandom Clifford+T circuits with controlled T-gate density. |
| 8 | `tests/test_circuits.py` | `test_make_chemistry_ansatz` | Validates Trotterized electronic structure Hamiltonian ansatz (FeMoCo active site model). |
| 9 | `tests/test_circuits.py` | `test_make_shor_modexp` | Verifies Shor modular exponentiation kernel with carry networks and semiclassical QFT. |
| 10 | `tests/test_circuits.py` | `test_get_benchmark_workloads` | Confirms availability of all 8 standard benchmark workload circuits. |
| 11 | `tests/test_circuits.py` | `test_workload_manifest` | Verifies `WORKLOAD_MANIFEST` schema (family, mathematical_task, semantics, literature_reference, correctness_criteria). |
| 12 | `tests/test_cost_model.py` | `test_synthesize_rotation_t_count` | Tests Ross-Selinger synthesis: exact Cliffords = 0 T, exact T = 1 T, and log scaling for arbitrary angles. |
| 13 | `tests/test_cost_model.py` | `test_extract_circuit_metrics` | Validates DAG inspection for 1Q/2Q ops, explicit T-count, synthesized T-count, depth, and T-depth. |
| 14 | `tests/test_cost_model.py` | `test_solve_minimum_code_distance` | Validates odd distance solver $d \ge 3$ and confirms infeasibility detection when physical error rate exceeds threshold. |
| 15 | `tests/test_cost_model.py` | `test_evaluate_fault_tolerant_cost_structure` | Validates full resource estimation: data qubits, factory qubits, runtime seconds, and cycle count. |
| 16 | `tests/test_cost_model.py` | `test_qldpc_cost_scaling` | Validates bivariate bicycle qLDPC code overhead scaling ($12$ physical qubits per logical qubit). |
| 17 | `tests/test_cost_model.py` | `test_decoder_stall_behavior` | Tests classical decoder latency vs cycle time, confirming stall factor = 2.0 when latency (2000ns) > cycle (1000ns). |
| 18 | `tests/test_hardware.py` | `test_linear_coupling_edges` | Verifies 1D linear nearest-neighbor directed coupling edges. |
| 19 | `tests/test_hardware.py` | `test_all_to_all_coupling_edges` | Verifies full all-to-all connectivity graph generation (e.g. trapped ion). |
| 20 | `tests/test_hardware.py` | `test_grid_coupling_edges` | Verifies 2D Cartesian grid coupling graph generation (e.g. neutral atom). |
| 21 | `tests/test_hardware.py` | `test_heavy_hex_coupling_edges` | Validates heavy-hex lattice coupling generator with alternating vertical bridge links. |
| 22 | `tests/test_hardware.py` | `test_qldpc_hardware_profile` | Validates IBM bivariate bicycle hardware model with torus coupler edges and literature provenance. |
| 23 | `tests/test_hardware.py` | `test_hardware_catalog_presets` | Checks catalog integrity across superconducting, trapped ion, neutral atom, and qLDPC profiles. |
| 24 | `tests/test_optimizer.py` | `test_generate_candidate_space` | Validates combinatorial candidate space generation across optimization levels, routings, factories, and decoders. |
| 25 | `tests/test_optimizer.py` | `test_evaluate_plan` | Evaluates single execution plan and checks physical qubits, runtime, and odd code distance. |
| 26 | `tests/test_optimizer.py` | `test_pareto_frontier_filtering` | Validates multi-objective Pareto dominance filtering ($Q_{phys}, T_{wall}, P_{fail}$). |
| 27 | `tests/test_optimizer.py` | `test_compare_sequential_vs_joint` | Validates comparative analysis between sequential baseline and joint co-design optimizer. |
| 28 | `tests/test_optimizer.py` | `test_compilation_cache_fingerprint` | Verifies SHA-256 canonical hashing across circuit gates, parameters, hardware coupling, and transpiler options. |
| 29 | `tests/test_search_algorithms.py` | `test_search_exhaustive` | Tests exhaustive candidate space search and validity of evaluated plans. |
| 30 | `tests/test_search_algorithms.py` | `test_search_random` | Tests stochastic uniform sampling within candidate evaluation budget. |
| 31 | `tests/test_search_algorithms.py` | `test_search_greedy` | Tests greedy coordinate-descent optimization across compiler, routing, factory, and decoder stages. |
| 32 | `tests/test_search_algorithms.py` | `test_search_simulated_annealing` | Tests simulated annealing with Metropolis-Hastings acceptance probability. |
| 33 | `tests/test_search_algorithms.py` | `test_benchmark_search_methods` | Benchmarks all 4 search methods against exhaustive ground truth (optimality gap % and Pareto coverage %). |
| 34 | `tests/test_stim_bridge.py` | `test_stim_simulator_initialization` | Verifies rotated surface code stabilizer simulator parameter checks (rejects even $d$ and $d < 3$). |
| 35 | `tests/test_stim_bridge.py` | `test_wilson_score_interval` | Verifies Wilson score 95% binomial confidence interval calculation. |
| 36 | `tests/test_stim_bridge.py` | `test_genuine_stim_circuit` | Verifies genuine Stim circuit generation (`stim.Circuit.generated("surface_code:rotated_memory_z")`). |
| 37 | `tests/test_stim_bridge.py` | `test_genuine_mwpm_decoding` | Verifies PyMatching MWPM decoding on Stim detector error models, returning a `ThresholdSampleResult`. |
| 38 | `tests/test_stim_bridge.py` | `test_run_threshold_study` | Validates threshold parameter sweep across code distances and physical error rates. |

---

### 1.3 Dependencies Required by Existing Engine & Tests
Inspection of `pyproject.toml` and `requirements.txt` reveals:
1. **Core Runtime Dependencies**:
   - `qiskit>=1.0.0`: AST manipulation, DAG parsing, transpilation passes, and coupling maps.
   - `stim>=1.16.0`: Rotated surface code memory circuit generation, detector error model extraction (`circuit.detector_error_model()`), and detector sampling.
   - `pymatching>=2.4.0`: Exact Minimum-Weight Perfect Matching (MWPM) decoding on detector error graphs (`Matching.from_detector_error_model(dem)`).
   - `numpy>=1.24.0`: Tensor/array operations in Stim and PyMatching.
   - `pandas>=2.0.0`: Benchmark result tables, CSV export, and candidate plan dataframes.
   - `matplotlib>=3.7.0`: Publication-grade Pareto trade-off plotting.
   - `scipy>=1.10.0`: Statistical distributions and mathematical functions.
2. **Development / Test Dependencies**:
   - `pytest>=7.0.0`: Test runner and assertions.
   - `pytest-cov>=4.0.0`: Code coverage reporting.

---

## 2. Logic Chain

1. **Test Suite Health**:
   - *Observation*: `pytest -v` executes 38 tests across 7 test files in 15.95 seconds with zero failures and exit code 0.
   - *Inference*: The core quantum domain logic (surface code simulation, MWPM decoding, cost modeling, T-gate synthesis, hardware profiles, Pareto optimization, baselines, and search heuristics) is functional and verified.

2. **Import Coupling in Existing Tests and Engine**:
   - *Observation*: Every test in `tests/test_*.py` imports modules as top-level Python scripts (e.g., `from circuits import ...`, `from hardware import ...`, `from cost_model import ...`, `from stim_bridge import ...`, `from optimizer import ...`, `from baselines import ...`, `from search_algorithms import ...`).
   - *Observation*: Inter-module dependencies also use flat imports (e.g. `cost_model.py` imports `from hardware import ...`; `optimizer.py` imports `from cost_model import ...`, `from hardware import ...`).
   - *Inference*: Reorganizing into `engines/quantum/src/plaq_quantum/` will immediately break all 38 existing tests unless an intentional packaging and backward-compatibility strategy is enacted.

3. **Monorepo Layout Requirements (R1)**:
   - *Observation*: Requirement R1 stipulates:
     - `apps/`: `apps/api` (FastAPI backend), `apps/cli` (unified `plaq` CLI), `apps/workbench` (desktop/web UI).
     - `packages/`: `packages/contracts` (Pydantic / JSON schemas), `packages/sdk-python` (client SDK).
     - `services/`: `services/control-plane`, `services/agent-runtime`, `services/sandbox-manager`, `services/model-gateway`, `services/artifact-service`.
     - `engines/quantum/`: `src/plaq_quantum/` containing circuits, hardware, cost model, Stim/PyMatching QEC, Pareto optimizer, and baselines.
     - `shared/`: Versioned schemas, security policies, agent prompts.
     - Acceptance criterion: "All existing 38 tests must continue to pass cleanly within `engines/quantum/`."
   - *Inference*: To satisfy R1 without breaking test execution:
     - The quantum engine code should be placed in `engines/quantum/src/plaq_quantum/` with an appropriate `pyproject.toml`.
     - In `engines/quantum/`, tests should be colocated in `engines/quantum/tests/`.
     - To ensure tests run seamlessly both from the repository root (`pytest`) and inside `engines/quantum/` (`pytest engines/quantum` or `cd engines/quantum && pytest`), we must provide:
       a) Editable install or `conftest.py` with `sys.path` configuration.
       b) Top-level import compatibility wrappers or direct package re-exports (`from plaq_quantum import ...`).
       c) A root-level shim in `tests/` or backward-compatible proxy modules at the repository root so that legacy scripts (`main.py`, existing tests) remain 100% operational.

4. **Service & Application Separation**:
   - *Observation*: Currently, `main.py` combines CLI parsing, benchmark execution, optimization, and server startup. `server.py` uses Python's standard `http.server.SimpleHTTPRequestHandler` without persistent database state, streaming SSE/WebSocket, or agent execution.
   - *Inference*: Reorganizing according to R1-R5 will modularize this cleanly:
     - `apps/cli/`: Will replace `main.py` with the rich `plaq` CLI commands (`plaq task`, `plaq quantum`, `plaq workspace`, `plaq serve`).
     - `apps/api/`: Will replace `server.py` with a robust FastAPI backend supporting REST, WebSocket/SSE event streaming, and persistent SQLite task storage.
     - `apps/workbench/`: Will host the desktop/web workbench interface (expanding `ui/index.html` into the 4-panel OS layout).
     - `services/`: Will house the control plane, agent execution loop, sandboxed tool runner, and artifact service.
     - `engines/quantum/`: Will serve as the authoritative computational quantum engine library.

---

## 3. Caveats

1. **Stim and PyMatching Platform Compatibility**:
   - Stim and PyMatching rely on compiled C++ extensions. While they installed and passed 100% on this Windows Python 3.10 environment, `stim_bridge.py` includes a statistical fallback in case they are missing in restricted container environments. In production CI and developer workstations, `stim>=1.16.0` and `pymatching>=2.4.0` are mandatory.
2. **Qiskit 1.0+ Transpiler Behavior**:
   - `CompilationCache` caches compiled metrics based on SHA-256 fingerprints that include the Qiskit version string (`qiskit.__version__`). Upgrading Qiskit invalidates old cache entries by design to prevent cross-version compiler discrepancies.
3. **Existing Root Files**:
   - There are legacy markdown files in root (`plaq-os.md` and `plaq os.md`) which are duplicates of the architectural research roadmap. These can be preserved or organized into documentation.

---

## 4. Conclusion

- **Codebase Health**: Excellent baseline. The core quantum engine implements genuine, physically grounded fault-tolerant simulation (Stim 1.16+ surface codes, PyMatching 2.4+ MWPM decoding, Ross-Selinger T-gate synthesis, heavy-hex coupling topologies, multi-objective Pareto optimization, and rigorous baselines/ablations).
- **Test Integrity**: All 38 unit tests pass cleanly in 15.95 seconds.
- **Monorepo Feasibility**: The engine code is self-contained with no external project dependencies other than scientific Python packages (`qiskit`, `stim`, `pymatching`, `numpy`, `pandas`, `scipy`, `matplotlib`).
- **Migration Blueprint**: Moving into `engines/quantum/src/plaq_quantum/` and `engines/quantum/tests/` while providing root import shims and workspace configuration guarantees complete compliance with Requirement R1 while preserving 100% test passing status.

---

## 5. Verification Method

To independently verify the observations and findings in this report:
1. **Run the Complete Test Suite**:
   ```pwsh
   pytest -v
   ```
   *Expected Result*: All 38 tests collected across 7 files pass cleanly in ~16s with exit code 0.
2. **Run with Coverage**:
   ```pwsh
   pytest -v --cov=. --cov-report=term-missing
   ```
   *Expected Result*: Verifies test coverage across `circuits.py`, `hardware.py`, `cost_model.py`, `stim_bridge.py`, `optimizer.py`, `baselines.py`, and `search_algorithms.py`.
3. **Verify Quantum Smoke Test**:
   ```pwsh
   python -c "from stim_bridge import SurfaceCodeStabilizerSimulator; sim = SurfaceCodeStabilizerSimulator(3); res = sim.sample_logical_errors(0.001, shots=100); print(res)"
   ```
   *Expected Result*: Prints a valid `ThresholdSampleResult` with `is_genuine_simulation=True` and `decoder_type='MWPM via PyMatching'`.
4. **Invalidation Condition**:
   - Any test failure among the 38 unit tests or an exit code other than 0 invalidates this baseline report.
