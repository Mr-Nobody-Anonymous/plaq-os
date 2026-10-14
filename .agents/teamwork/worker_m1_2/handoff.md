# Handoff Report — Worker M1 (Iteration 2: Optimizer Defect Remediation)

**Milestone**: M1 Iteration 2 (Optimizer Defect Remediation)  
**Agent**: Worker M1 (`worker_m1_2`)  
**Parent Agent**: `1f18b9cb-e1e8-4b00-9c69-021157944324`  
**Date**: 2026-10-14  
**Verdict**: **REMEDIATION COMPLETE & VERIFIED (0 FAILURES, 0 XFAILS, 100% PASS ACROSS ALL SUITES)**  

---

## 1. Observation

### A. Pre-Remediation Baseline State
Prior to code modifications, execution of the test suites revealed the exact defect reproduction state:
1. **Adversarial Test Suite (`tests/test_quantum_adversarial.py`)**:
   - Command: `pytest -v tests/test_quantum_adversarial.py`
   - Output: `19 passed, 3 xfailed in 4.34s` (exit code 0).
   - Defect 1 (`test_defect_compilation_failure_missing_feasibility_reason`):
     `evaluate_plan` crashed with `TypeError: CostEstimationResult.__init__() missing 1 required positional argument: 'feasibility_reason'`.
   - Defect 2 (`test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits`):
     Calling `cache.get_or_compile` on two separate instances of `make_test_circuit(4)` failed with `AssertionError: Cache length grew to 2! circuit.name 'circuit-41' vs 'circuit-42' caused different fingerprints for identical circuits.`
   - Defect 3 (`test_defect_compilation_cache_basis_gates_omitted`):
     Comparing fingerprints of two hardware profiles with identical topology but differing basis gates (`('cx', ...)` vs `('cz', ...)`) failed with `AssertionError: Fingerprint collision detected! Basis gates are not included in compilation fingerprint.`

2. **Base Quantum Suite (`engines/quantum/tests/`)**:
   - Command: `pytest -v engines/quantum/tests/`
   - Output: `38 passed in 3.97s` (100% passing).

### B. Code Locations Under Scope
1. `engines/quantum/src/plaq_quantum/optimizer.py`:
   - Lines 133–145: Fingerprint computation used `circuit.name` and omitted classical bit indices as well as `hardware.basis_gates`.
   - Line 231: `dummy_result = CostEstimationResult(...)` omitted `feasibility_reason`.
2. `tests/test_quantum_adversarial.py`:
   - Lines 454–545: Defect proofs in `TestEmpiricalDefectProofs` marked with `@pytest.mark.xfail(strict=True, ...)`.

---

## 2. Logic Chain

1. **Defect 1 Remediation (`evaluate_plan` `feasibility_reason`)**:
   - *Observation*: `CostEstimationResult` is defined in `plaq_quantum/cost_model.py:82` with `valid: bool`, `feasibility_reason: str`, followed by 13 more non-default positional fields.
   - *Logic*: In `optimizer.py:236`, when `metrics is None` (transpilation failure), `dummy_result = CostEstimationResult(...)` omitted `feasibility_reason`. Modifying `cost_model.py` to give `feasibility_reason` a default value would trigger Python's dataclass rule prohibiting non-default fields after default fields (`TypeError: non-default argument follows default argument`). Therefore, the robust and minimal fix is to supply `feasibility_reason="Compilation failed with given routing/layout options."` directly at the instantiation call site in `optimizer.py:238`.
   - *Result*: Candidate plan failures return an `EvaluatedPlan` marked `valid=False` with complete diagnostics and feasibility reasons.

2. **Defect 2 Remediation (Canonical Circuit Hashing)**:
   - *Observation*: In Qiskit, `QuantumCircuit` instances created without explicit names receive auto-incrementing identifiers (e.g. `circuit-41`, `circuit-42`), causing `hasher.update(circuit.name.encode("utf-8"))` to generate divergent fingerprints for structurally identical circuits.
   - *Logic*: Circuit compilation depends on the register sizes, ordered gate operations, classical bit assignments, and parameter values, not on the Python instance name. Replacing `circuit.name` with canonical register structure (`:qubits={circuit.num_qubits}:clbits={circuit.num_clbits}:`), classical bit mappings (`cl_str = f"->{','.join(map(str, c_indices))}" if c_indices else ""`), and floating-point parameters formatted to 8 decimals (`f"{float(p):.8f}"`) guarantees deterministic hashing across instances.
   - *Result*: Two distinct instances of equivalent circuits now produce identical fingerprints and hit the cache (`len(cache._cache) == 1`).

3. **Defect 3 Remediation (Basis Gate Sensitivity)**:
   - *Observation*: Qiskit's `transpile()` function uses `basis_gates=list(hardware.basis_gates)`. Two hardware targets with the same name and topology but differing basis gates (e.g. CX-native superconducting vs CZ-native) require different gate syntheses and produce different compiled metrics.
   - *Logic*: Sorting basis gates (`basis_str = ",".join(sorted(hardware.basis_gates)) if hardware.basis_gates else ""`) and appending `:basis={basis_str}:` to the hardware fingerprint segment guarantees that differing basis sets produce strictly distinct fingerprints, preventing cache collisions and poisoning.
   - *Result*: Hardware profiles with differing basis gates produce strictly distinct SHA-256 fingerprints (`fp1 != fp2`).

4. **Adversarial Test Suite Conversion**:
   - *Observation*: With the three defects remediated, tests marked with `@pytest.mark.xfail(strict=True)` in `tests/test_quantum_adversarial.py` would cause `XPASS` errors under pytest.
   - *Logic*: Removing the `@pytest.mark.xfail` decorators and adding assertions on `res.valid`, `res.cost_result.feasibility_reason`, cache hit size, and fingerprint inequality converts known defect demonstrations into permanent regression protections.
   - *Result*: All 22 adversarial tests pass cleanly without xfail.

---

## 3. Caveats

- **Root Shim Files**: Root-level `optimizer.py` and `cost_model.py` are thin re-export shims (`from plaq_quantum.optimizer import *`). They required no edits and automatically expose the patched functions with zero code duplication.
- **Transpiler Seeds**: Deterministic compilation caching continues to require fixed seeds (`seed=42`) for stochastic transpiler passes (e.g. Sabre routing), which is standard behavior in `CompilationCache`.
- No other files were modified, strictly upholding the minimal-change mandate.

---

## 4. Conclusion

All three optimizer defects have been cleanly and genuinely remediated:
1. `engines/quantum/src/plaq_quantum/optimizer.py`:
   - Updated `compute_compilation_fingerprint`: Removed `circuit.name`, added canonical qubit/clbit registers and classical bit targeting, and included sorted `hardware.basis_gates`.
   - Updated `evaluate_plan`: Added `feasibility_reason="Compilation failed with given routing/layout options."` to `CostEstimationResult(...)` when `metrics is None`.
2. `tests/test_quantum_adversarial.py`:
   - Removed `@pytest.mark.xfail` from all 3 defect tests in `TestEmpiricalDefectProofs`.
   - Added validation assertions verifying graceful failure handling, cache hit across distinct instances, and basis gate differentiation.

---

## 5. Verification Method & Output Evidence

### A. Independent Verification Commands and Results

1. **Adversarial Regression Test Suite**:
   - Command: `pytest -v tests/test_quantum_adversarial.py`
   - Exit Code: `0`
   - Result:
     ```text
     ============================= 22 passed in 3.71s ==============================
     ```
   - Includes clean passes for:
     - `test_defect_compilation_failure_missing_feasibility_reason` PASSED
     - `test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits` PASSED
     - `test_defect_compilation_cache_basis_gates_omitted` PASSED

2. **Quantum Package Unit Tests**:
   - Command: `pytest -v engines/quantum/tests/`
   - Exit Code: `0`
   - Result:
     ```text
     ============================= 38 passed in 4.21s ==============================
     ```

3. **Root Pytest Discovery (All Quantum Tests)**:
   - Command: `pytest -v`
   - Exit Code: `0`
   - Result:
     ```text
     ============================= 60 passed in 6.85s ==============================
     ```
     (38 base unit tests + 22 adversarial tests = 60 passed, 0 failed, 0 xfailed).

4. **Tier 1 Feature E2E Verification**:
   - Command: `pytest -v tests/e2e/test_tier1_feature.py -k TestFeature02QuantumModularization`
   - Exit Code: `0`
   - Result:
     ```text
     ================ 5 passed, 75 deselected, 2 warnings in 2.49s =================
     ```

5. **Direct Python Invariant & Root Shim Checks**:
   - Command:
     ```powershell
     python -c "from plaq_quantum.circuits import make_qft_circuit; from plaq_quantum.hardware import DEMO_HARDWARE; from plaq_quantum.optimizer import ExecutionPlan, evaluate_plan; plan = ExecutionPlan(0, 'lookahead', 'trivial', 1, 'minimal_safe', 'streaming_asic'); res = evaluate_plan(make_qft_circuit(4), DEMO_HARDWARE, plan); assert res.valid is False; assert res.cost_result.feasibility_reason == 'Compilation failed with given routing/layout options.'"
     ```
     Exit Code: `0`.
   - Command:
     ```powershell
     python -c "from circuits import make_qft_circuit; from hardware import DEMO_HARDWARE; from optimizer import ExecutionPlan, evaluate_plan; plan = ExecutionPlan(0, 'lookahead', 'trivial', 1, 'minimal_safe', 'streaming_asic'); res = evaluate_plan(make_qft_circuit(4), DEMO_HARDWARE, plan); assert res.valid is False"
     ```
     Exit Code: `0`.

### B. Invalidation Conditions
- If calling `evaluate_plan` with an unroutable layout/routing option raises `TypeError`.
- If `cache.get_or_compile` called on two separate invocations of `make_test_circuit(4)` produces `len(cache._cache) > 1`.
- If `compute_compilation_fingerprint` produces identical hashes for different `hardware.basis_gates`.
