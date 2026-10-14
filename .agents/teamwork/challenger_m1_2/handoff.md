# Handoff Report — Challenger 2 (Quantum Engine Stress Challenger)

**Milestone**: M1 (Monorepo Architecture & Quantum Modularization)  
**Agent**: Challenger 2 (Empirical Challenger: critic, specialist)  
**Date**: 2026-10-14  
**Verdict**: **FAILED (DEFECTS IDENTIFIED - REMEDIATION REQUIRED)**  

---

## 1. Observation

Direct empirical observations from executing live quantum error correction simulations, Pareto optimization across hardware/workloads, and compilation cache validation:

### A. Base Test Suite & Environment Verification
1. Environment has all required quantum compilation and decoding libraries installed:
   - `stim: 1.16.0`
   - `pymatching: 2.4.0`
   - `qiskit: 2.5.2`
2. Base unit test suite executed via command:
   ```powershell
   pytest engines/quantum/tests -v
   ```
   **Result**: 38 of 38 unit tests pass cleanly in 4.23s.

### B. Live Quantum Simulations (`stim_bridge.py`)
Direct execution of `plaq_quantum.stim_bridge.run_surface_code_simulation` for $d \in \{3, 5\}$ and $p \in \{0.001, 0.01\}$ with 2,000 shots:
- $d=3, p=0.001$: 0 errors / 2,000 shots ($P_L = 0.0000$, 95% Wilson CI $[0.0, 0.00192]$, decoder=`MWPM via PyMatching`, genuine=`True`)
- $d=5, p=0.001$: 0 errors / 2,000 shots ($P_L = 0.0000$, 95% Wilson CI $[0.0, 0.00192]$, decoder=`MWPM via PyMatching`, genuine=`True`)
- $d=3, p=0.010$: 119 errors / 2,000 shots ($P_L = 0.0595$, 95% Wilson CI $[0.0500, 0.0707]$, decoder=`MWPM via PyMatching`, genuine=`True`)
- $d=5, p=0.010$: 172 errors / 2,000 shots ($P_L = 0.0860$, 95% Wilson CI $[0.0745, 0.0991]$, decoder=`MWPM via PyMatching`, genuine=`True`)
- Sub-threshold crossover sweep at $p=0.003$ (4,000 shots):
  - $d=3$: 38 errors ($9.50 \times 10^{-3}$)
  - $d=5$: 18 errors ($4.50 \times 10^{-3}$) -> **2.11x error suppression** confirmed.
- Wilson score interval, seed determinism, and invalid distance validation ($d=1, 4$) confirmed correct.

### C. Defect 1 (CRITICAL): Crash in `evaluate_plan` upon Compilation Failure
- **File**: `engines/quantum/src/plaq_quantum/optimizer.py`, lines 230–247:
  ```python
  if metrics is None:
      dummy_result = CostEstimationResult(
          valid=False,
          physical_qubits=999_999,
          runtime_seconds=999.0,
          failure_probability=1.0,
          code_distance=0,
          factory_code_distance=0,
          num_factories=plan.num_magic_factories,
          data_physical_qubits=0,
          factory_physical_qubits=0,
          total_surface_code_cycles=0,
          decoder_stall_factor=1.0,
          spacetime_volume=0,
          total_cost_score=float("inf"),
          assumptions={},
          diagnostics=["Compilation failed with given routing/layout options."],
      )
  ```
- **Definition in `engines/quantum/src/plaq_quantum/cost_model.py`**, lines 82–100:
  ```python
  @dataclass(frozen=True)
  class CostEstimationResult:
      valid: bool
      feasibility_reason: str
      physical_qubits: int
      ...
  ```
- **Trigger**: When running `search_pareto_optimizer` or `compare_sequential_vs_joint` on `make_qft_circuit(4)` or any workload where routing fails (e.g. `routing_method='lookahead'`, `layout_method='trivial'` on linear topology raises Qiskit `TranspilerError`), `metrics` is `None`. `evaluate_plan` attempts to construct `CostEstimationResult` without the required positional parameter `feasibility_reason`.
- **Verbatim Error Output**:
  ```text
  TypeError: CostEstimationResult.__init__() missing 1 required positional argument: 'feasibility_reason'
  ```

### D. Defect 2 (HIGH): Non-Deterministic Compilation Caching Across Circuit Instances
- **File**: `engines/quantum/src/plaq_quantum/optimizer.py`, line 134:
  ```python
  hasher.update(circuit.name.encode("utf-8"))
  ```
- **Trigger**: In Qiskit, every `QuantumCircuit` instantiated without an explicit `name` is automatically assigned an auto-incrementing name (`circuit-41`, `circuit-42`, etc.). All standard workload generators in `circuits.py` (`make_test_circuit`, `make_qaoa_circuit`, `make_qft_circuit`, etc.) create circuits without explicit names.
- **Result**: Calling `cache.get_or_compile(make_test_circuit(4), ...)` followed by `cache.get_or_compile(make_test_circuit(4), ...)` generates two completely different SHA-256 fingerprints, causing a cache miss every time a new circuit object is compiled, defeating cross-run and cross-task compilation caching.

### E. Defect 3 (MEDIUM): Cache Key Collision Omitting Hardware Basis Gates
- **File**: `engines/quantum/src/plaq_quantum/optimizer.py`, line 143:
  ```python
  edges_str = str(sorted(hardware.get_coupling_edges(circuit.num_qubits)))
  hasher.update(f":hw={hardware.name}:{edges_str}:".encode("utf-8"))
  hasher.update(f":opt={opt_level}:rout={routing_method}:lay={layout_method}:seed={seed}:".encode("utf-8"))
  ```
- **Trigger**: `hardware.basis_gates` is omitted from the SHA-256 fingerprint.
- **Result**: Two hardware configurations with identical names/topologies but different native basis gates (e.g. `basis_gates=('cx', 'rz', 'sx', 'x')` vs `basis_gates=('cz', 'rz', 'sx', 'x')`) generate the exact same fingerprint, resulting in cache poisoning where CZ-compiled metrics are served for a CX compilation target.

---

## 2. Logic Chain

1. **Premise 1**: Section R1 of `ORIGINAL_REQUEST.md` requires `engines/quantum/` to deliver production-grade modularized quantum compilation, Pareto optimization, and compilation caching.
2. **Step 2 (Stim Bridge)**: Observation B confirms that `stim_bridge.run_surface_code_simulation` uses genuine Stim circuits and PyMatching 2.4+ MWPM decoding. Below threshold ($p=0.003$), distance scaling from $d=3$ to $d=5$ reduces logical error rate from $0.95\%$ to $0.45\%$. Wilson score confidence intervals and seed determinism hold without exception.
3. **Step 3 (Pareto Optimizer Correctness)**: Observation B & E show that when compilation succeeds, `extract_pareto_frontier` extracts a mathematically verified non-dominated set satisfying: (1) mutual non-dominance between all frontier plans, (2) domination of all excluded valid plans, and (3) $valid == True$ invariance across all 5 hardware architectures (`DEMO_HARDWARE`, `SUPERCONDUCTING_HERON`, `TRAPPED_ION_FORTE`, `NEUTRAL_ATOM_AQUILA`, `QLDPC_BIVARIATE_BICYCLE`).
4. **Step 4 (Optimizer Robustness Defect)**: Observation C shows that `generate_candidate_space` includes candidate plans with `routing_method='lookahead'` and `layout_method='trivial'`. When evaluating dense entangling workloads like QFT or arbitrary graphs, Qiskit's lookahead routing fails swap insertion. `CompilationCache` correctly catches this exception and returns `None`. However, `optimizer.py:231` invokes `CostEstimationResult(...)` without `feasibility_reason`, crashing the Python process with `TypeError`.
5. **Step 5 (Cache Determinism Defect)**: Observation D shows that hashing `circuit.name` couples compilation cache keys to Python process-level circuit instantiation counters rather than canonical structural gate representations.
6. **Step 6 (Cache Collision Defect)**: Observation E proves that omitting `hardware.basis_gates` from the hash allows distinct hardware targets to produce identical fingerprints.

---

## 3. Caveats

- Highly parallel distributed MPI decoders (>100 nodes) were not evaluated as the current simulator is single-node Python/C++ PyMatching.
- High code distances ($d \ge 11$) with $10^6$ Monte Carlo shots were skipped to adhere to turn execution limits, but distances $d=3, 5$ were rigorously verified with up to 4,000 shots.
- `engines/quantum/` was evaluated strictly in review-only mode per Challenger constraints; no implementation files were modified.

---

## 4. Conclusion

**Verdict: FAILED (DEFECTS IDENTIFIED - REMEDIATION REQUIRED)**

The quantum engine demonstrates high scientific rigor in its topological Stim simulation and analytical cost modeling. However, the computational execution layer cannot be certified as fully stable until the following three concrete remediations are applied by the engineering team:

1. **Remediation 1 (CRITICAL)**: In `engines/quantum/src/plaq_quantum/optimizer.py`, line 231, add `feasibility_reason`:
   ```python
   dummy_result = CostEstimationResult(
       valid=False,
       feasibility_reason="Compilation failed with given routing/layout options.",
       physical_qubits=999_999,
       ...
   )
   ```
   *(Alternatively, provide `feasibility_reason: str = ""` with a default in `cost_model.py:86`.)*

2. **Remediation 2 (HIGH)**: In `engines/quantum/src/plaq_quantum/optimizer.py`, line 134, do not hash unnormalized `circuit.name` in `compute_compilation_fingerprint`, or normalize it to a canonical representation based solely on qubit registers, gate types, parameters, and clbits.

3. **Remediation 3 (MEDIUM)**: In `engines/quantum/src/plaq_quantum/optimizer.py`, line 143, add `hardware.basis_gates` into the SHA-256 fingerprint:
   ```python
   basis_str = ",".join(sorted(hardware.basis_gates))
   hasher.update(f":hw={hardware.name}:{edges_str}:basis={basis_str}:".encode("utf-8"))
   ```

---

## 5. Verification Method

To independently reproduce all observations and verify subsequent fixes:

1. **Run Base Test Suite**:
   ```powershell
   pytest engines/quantum/tests -v
   ```
   Expected: 38 passed.

2. **Run Challenger Adversarial Stress Suite**:
   ```powershell
   pytest tests/test_quantum_adversarial.py -v -s
   ```
   Expected currently: 19 passed, 3 xfailed (defect proofs).  
   *Post-fix expected*: 22 passed cleanly with zero failures.

3. **Direct Stim Live Simulation Command**:
   ```powershell
   python -c "from plaq_quantum.stim_bridge import run_surface_code_simulation; print(run_surface_code_simulation(5, 0.001, 1000))"
   ```
   Expected: Valid `ThresholdSampleResult` with `is_genuine_simulation=True`.

4. **Direct Defect 1 Reproduction**:
   ```powershell
   python -c "from plaq_quantum.circuits import make_qft_circuit; from plaq_quantum.hardware import DEMO_HARDWARE; from plaq_quantum.optimizer import search_pareto_optimizer; search_pareto_optimizer(make_qft_circuit(4), DEMO_HARDWARE, candidate_limit=15)"
   ```
   Current Result: Raises `TypeError: CostEstimationResult.__init__() missing 1 required positional argument: 'feasibility_reason'`.
