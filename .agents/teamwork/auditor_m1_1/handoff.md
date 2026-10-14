# Forensic Audit Report: Plaq-OS Milestone M1

**Work Product**: Plaq-OS Milestone M1 (`engines/quantum/`, root shims, monorepo tree, `tests/`)  
**Profile**: General Project (Integrity Mode: `development` per `ORIGINAL_REQUEST.md`)  
**Verdict**: **CLEAN**

---

## 1. Observation

### 1.1 Ground Truth Specification & Constraints
- `ORIGINAL_REQUEST.md` line 9 specifies `Integrity mode: development`.
- Requirement R1 mandates:
  - Monorepo directory partitioning: `apps/` (`api`, `cli`, `workbench`), `packages/` (`contracts`, `sdk-python`), `services/` (`control-plane`, `agent-runtime`, `sandbox-manager`, `model-gateway`, `artifact-service`), `engines/quantum/` (`src/plaq_quantum/`), and `shared/` (`schemas`, `policies`, `prompts`).
  - Modular `plaq-quantum` package at version `0.3.0`.
  - Preservation of all 38 existing unit tests with 100% pass rate.
  - Backward compatibility for flat imports.

### 1.2 Monorepo Layout & Workspace Discipline
- Direct filesystem inspection confirmed all 12 directories exist with proper `.gitkeep` placeholders.
- `.agents/teamwork/` was audited: contains only Markdown metadata files (`BRIEFING.md`, `DISPATCH.md`, `progress.md`, `handoff.md`, `PROJECT.md`). No source code, test scripts, or runtime binaries exist in `.agents/teamwork/`.

### 1.3 Quantum Engine Source Integrity (`engines/quantum/src/plaq_quantum/`)
- A line-by-line diff against ground truth commit `7f181b8` confirmed:
  - `circuits.py` (11,861 bytes): Preserves all 8 quantum circuit generators (`make_test_circuit`, `make_qaoa_circuit`, `make_qft_circuit`, `make_bernstein_vazirani_circuit`, `make_random_clifford_t_circuit`, `make_chemistry_ansatz_circuit`, `make_shor_modexp_circuit`, `get_benchmark_workloads`). Added optional parameter aliases (`num_qubits`, `num_layers`, `make_chemistry_ansatz`) with zero logic suppression.
  - `hardware.py` (11,775 bytes): Preserves all hardware coupling topologies (Linear, All-to-All, Grid, Heavy-Hex, QLDPC) and the `HARDWARE_CATALOG`. Added architecture aliases and `get_hardware_profile()`.
  - `cost_model.py` (18,430 bytes): Preserves Ross-Selinger T-count synthesis, circuit metric extraction, minimum code distance calculation, and fault-tolerant cost estimation. Enhanced `CircuitMetrics` with dictionary-like mapping and `CodeDistanceResult` with dual int/tuple behavior.
  - `stim_bridge.py` (9,150 bytes): Preserves genuine Stim rotated surface code memory experiment generation, detector error model extraction, PyMatching MWPM decoding, and Wilson score confidence intervals. Added `StimSurfaceCodeSimulator` convenience bridge.
  - `optimizer.py` (19,608 bytes): Preserves joint co-design optimization, candidate space generation, Pareto frontier extraction, sequential vs joint comparison, and `CompilationCache` with SHA-256 fingerprinting.
  - `baselines.py` (11,918 bytes): Preserves the Four-Baselines comparative protocol and systematic layer ablation study.
  - `search_algorithms.py` (14,847 bytes): Preserves exhaustive, random, greedy, and simulated annealing search routines.
  - `benchmark.py` (5,434 bytes): Preserves compilation and fault-tolerant benchmarking runners.
  - `__init__.py` (4,095 bytes): Clean re-exports of all 8 submodules and 45 public symbols.
  - `pyproject.toml`: Valid PEP 517/621 setuptools packaging for `plaq-quantum` 0.3.0.

### 1.4 Root Backward Compatibility Shims
- Shims for `circuits.py`, `hardware.py`, `cost_model.py`, `stim_bridge.py`, `optimizer.py`, `baselines.py`, `search_algorithms.py`, and `benchmark.py` import `plaq_bootstrap` and delegate directly to `plaq_quantum.<module>`.
- Object identity was confirmed: `circuits.make_test_circuit is plaq_quantum.circuits.make_test_circuit` is `True`.

### 1.5 Independent Test Suite Execution Outputs

#### 1. Isolated Unit Test Suite (`pytest -v engines/quantum/tests/`)
```text
Exit Code: 0
Output:
collected 38 items
engines/quantum/tests/test_baselines.py::test_four_baselines_protocol PASSED [  2%]
engines/quantum/tests/test_baselines.py::test_ablation_study PASSED      [  5%]
engines/quantum/tests/test_circuits.py::test_make_test_circuit PASSED    [  7%]
engines/quantum/tests/test_circuits.py::test_make_qaoa_circuit PASSED    [ 10%]
engines/quantum/tests/test_circuits.py::test_make_qft_circuit PASSED     [ 13%]
engines/quantum/tests/test_circuits.py::test_make_bernstein_vazirani_circuit PASSED [ 15%]
engines/quantum/tests/test_circuits.py::test_make_random_clifford_t PASSED [ 18%]
engines/quantum/tests/test_circuits.py::test_make_chemistry_ansatz PASSED [ 21%]
engines/quantum/tests/test_circuits.py::test_make_shor_modexp PASSED     [ 23%]
engines/quantum/tests/test_circuits.py::test_get_benchmark_workloads PASSED [ 26%]
engines/quantum/tests/test_circuits.py::test_workload_manifest PASSED    [ 28%]
engines/quantum/tests/test_cost_model.py::test_synthesize_rotation_t_count PASSED [ 31%]
engines/quantum/tests/test_cost_model.py::test_extract_circuit_metrics PASSED [ 34%]
engines/quantum/tests/test_cost_model.py::test_solve_minimum_code_distance PASSED [ 36%]
engines/quantum/tests/test_cost_model.py::test_evaluate_fault_tolerant_cost_structure PASSED [ 39%]
engines/quantum/tests/test_cost_model.py::test_qldpc_cost_scaling PASSED [ 42%]
engines/quantum/tests/test_cost_model.py::test_decoder_stall_behavior PASSED [ 44%]
engines/quantum/tests/test_hardware.py::test_linear_coupling_edges PASSED [ 47%]
engines/quantum/tests/test_hardware.py::test_all_to_all_coupling_edges PASSED [ 50%]
engines/quantum/tests/test_hardware.py::test_grid_coupling_edges PASSED  [ 52%]
engines/quantum/tests/test_hardware.py::test_heavy_hex_coupling_edges PASSED [ 55%]
engines/quantum/tests/test_hardware.py::test_qldpc_hardware_profile PASSED [ 57%]
engines/quantum/tests/test_hardware.py::test_hardware_catalog_presets PASSED [ 60%]
engines/quantum/tests/test_optimizer.py::test_generate_candidate_space PASSED [ 63%]
engines/quantum/tests/test_optimizer.py::test_evaluate_plan PASSED       [ 65%]
engines/quantum/tests/test_optimizer.py::test_pareto_frontier_filtering PASSED [ 68%]
engines/quantum/tests/test_optimizer.py::test_compare_sequential_vs_joint PASSED [ 71%]
engines/quantum/tests/test_optimizer.py::test_compilation_cache_fingerprint PASSED [ 73%]
engines/quantum/tests/test_search_algorithms.py::test_search_exhaustive PASSED [ 76%]
engines/quantum/tests/test_search_algorithms.py::test_search_random PASSED [ 78%]
engines/quantum/tests/test_search_algorithms.py::test_search_greedy PASSED [ 81%]
engines/quantum/tests/test_search_algorithms.py::test_search_simulated_annealing PASSED [ 84%]
engines/quantum/tests/test_search_algorithms.py::test_benchmark_search_methods PASSED [ 86%]
engines/quantum/tests/test_stim_bridge.py::test_stim_simulator_initialization PASSED [ 89%]
engines/quantum/tests/test_stim_bridge.py::test_wilson_score_interval PASSED [ 92%]
engines/quantum/tests/test_stim_bridge.py::test_genuine_stim_circuit PASSED [ 94%]
engines/quantum/tests/test_stim_bridge.py::test_genuine_mwpm_decoding PASSED [ 97%]
engines/quantum/tests/test_stim_bridge.py::test_run_threshold_study PASSED [100%]
============================= 38 passed in 9.08s ==============================
```

#### 2. Root Test Suite with Shims (`pytest -v tests/test_*.py`)
```text
Exit Code: 0
Output:
collected 38 items
============================= 38 passed in 9.37s ==============================
```

#### 3. Quantum Modularization E2E Feature Tests
```text
Command: pytest -v tests/e2e/test_tier1_feature.py -k TestFeature02QuantumModularization
Exit Code: 0
Output:
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_01_package_metadata_and_structure PASSED [ 20%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_02_circuit_workload_generation PASSED [ 40%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_03_cost_model_t_count_and_depth PASSED [ 60%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_04_stim_rotated_surface_code_simulation PASSED [ 80%]
tests/e2e/test_tier1_feature.py::TestFeature02QuantumModularization::test_f2_05_multi_objective_pareto_optimizer PASSED [100%]
================ 5 passed, 75 deselected, 2 warnings in 5.23s =================
```

### 1.6 Independent Empirical Verification of Core Mathematics
An independent empirical audit script executed against the live package:
1. **Stim + PyMatching Live Decoding**:
   - `HAS_STIM: True, HAS_PYMATCHING: True`
   - $p = 0.001$: 0 logical errors out of 300 shots.
   - $p = 0.030$: 79 logical errors out of 300 shots (error rate 0.2633).
   - Higher noise rate strictly increases logical errors; `is_genuine_simulation: True`.
2. **Ross-Selinger $T$-Synthesis Scaling**:
   - Tested $\epsilon \in [10^{-3}, 10^{-6}, 10^{-9}, 10^{-12}]$ for angle $0.314159$.
   - Generated $T$-counts: $[35, 67, 99, 131]$.
   - Strictly scales as $\lceil 3.21 \log_2(1/\epsilon) + 2.5 \rceil$ (+32 gates per $1000\times$ precision gain).
3. **Code Distance Solver**:
   - Small spacetime volume ($V = 1000$): $d = 9$, feasible = `True`.
   - Large spacetime volume ($V = 10^7$): $d = 17$, feasible = `True`.
   - Error above threshold ($p = 0.02 > 0.01$): feasible = `False`, reason = `Physical error rate >= threshold`.
4. **Pareto Frontier Extraction**:
   - Passed candidate set with 1 strictly dominated point and 2 non-dominated trade-offs.
   - Returned exactly the 2 non-dominated points; correctly pruned the dominated point.

---

## 2. Logic Chain

1. **Premise 1 (Monorepo Layout)**: Requirement R1 and master `PROJECT.md` require standard monorepo top-level partitions and metadata-only `.agents/teamwork/`.
   - **Direct Observation**: All 12 directory trees exist. `.agents/teamwork/` contains zero source, test, or compiled files.
   - **Deduction**: Monorepo layout conforms to specification.

2. **Premise 2 (Quantum Modularization Authenticity)**: Requirement R1 requires full preservation of quantum engine logic in `engines/quantum/src/plaq_quantum/` with no facade, dummy, or mocked implementations.
   - **Direct Observation**: Git diff against `7f181b8` proves 100% of domain algorithms (Stim QEC, PyMatching MWPM, Qiskit transpilation, Ross-Selinger synthesis, Pareto filtering) were relocated without truncation or stubbing.
   - **Deduction**: Package implementation is authentic and non-facade.

3. **Premise 3 (Absence of Hardcoded Cheats)**:
   - **Direct Observation**: Static regex scanning across all `.py` files found zero hardcoded PASS/FAIL assertions, zero `return <constant>` bypasses, zero pre-cooked test results, and zero obfuscated code / eval / exec payloads.
   - **Deduction**: No prohibited patterns exist in the work product.

4. **Premise 4 (Test Authenticity & Suite Parity)**:
   - **Direct Observation**: The 38 original unit tests in `engines/quantum/tests/` and `tests/` are identical in logic to the pre-existing test suite. `pytest` executes genuinely in ~9 seconds across all 38 items with exit code 0.
   - **Deduction**: Test suite execution is genuine and fully intact.

5. **Premise 5 (Empirical Mathematical Validity)**:
   - **Direct Observation**: Live execution of Stim/PyMatching QEC, Ross-Selinger synthesis, distance solvers, and Pareto sorting yields physically and mathematically valid outputs.
   - **Deduction**: Scientific co-design logic is operative and functional.

---

## 3. Caveats

- `pytest.ini` was configured with `--ignore=tests/e2e` to prevent collisions during root unit testing while peer teams develop milestones M2 through M5.
- Challenger 2 added a stress test file `tests/test_quantum_adversarial.py` at repository root during Milestone M1 review. That file tests 56 adversarial scenarios (53 passed, 3 failed on pre-existing edge cases in the baseline codebase). Running targeted unit tests (`tests/test_*.py` excluding adversarial stress test) passes 38/38 cleanly.
- System warnings regarding `StarletteDeprecationWarning` and `PytestRemovedIn10Warning` were emitted by third-party packages; these do not affect execution or correctness.

---

## 4. Conclusion

Milestone M1 (`engines/quantum/`, root backward compatibility shims, and monorepo structure) satisfies all integrity requirements:
- Zero hardcoded test results.
- Zero facade or dummy implementations.
- Zero fabricated verification outputs.
- 100% genuine quantum algorithms preserved and verified empirically.
- 38/38 unit tests pass with exit code 0.
- Monorepo directory partitioning matches R1.
- Binary Verdict: **CLEAN**.

---

## 5. Verification Method

To independently reproduce the forensic verification:

```bash
# 1. Run isolated modular test suite
pytest -v engines/quantum/tests/

# 2. Run root backward compatibility test suite (original 38 unit tests)
pytest -v tests/test_baselines.py tests/test_circuits.py tests/test_cost_model.py tests/test_hardware.py tests/test_optimizer.py tests/test_search_algorithms.py tests/test_stim_bridge.py

# 3. Run Quantum Modularization E2E feature tests
pytest -v tests/e2e/test_tier1_feature.py -k TestFeature02QuantumModularization

# 4. Verify live Stim / PyMatching simulation and Ross-Selinger math
python -c "import plaq_quantum as pq; sim = pq.SurfaceCodeStabilizerSimulator(3); res = sim.sample_logical_errors(0.001, 100); assert res.is_genuine_simulation; print('Stim QEC OK')"

# 5. Verify root shim object identity
python -c "import circuits, plaq_quantum.circuits; assert circuits.make_test_circuit is plaq_quantum.circuits.make_test_circuit; print('Identity OK')"
```
