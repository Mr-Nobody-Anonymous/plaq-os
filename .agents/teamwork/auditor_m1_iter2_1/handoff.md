# Forensic Audit Report: Milestone M1 Iteration 2 (Optimizer Defect Remediation)

**Work Product**: `engines/quantum/src/plaq_quantum/optimizer.py`, `tests/test_quantum_adversarial.py`  
**Auditor**: Forensic Auditor (`auditor_m1_iter2_1`)  
**Parent Agent**: `1f18b9cb-e1e8-4b00-9c69-021157944324`  
**Profile**: General Project (`development` mode per `ORIGINAL_REQUEST.md:9`)  
**Verdict**: **CLEAN**

---

### Phase Results
- **Phase 1.1: Hardcoded Output Detection**: PASS — No hardcoded test results, expected hashes, or conditional test bypasses found in `optimizer.py`.
- **Phase 1.2: Facade Implementation Detection**: PASS — Canonical fingerprinting, compilation caching, and error handling represent genuine mathematical and systems logic; no placeholder stubs or empty returns.
- **Phase 1.3: Pre-populated Artifact Detection**: PASS — No fabricated log files or fake output artifacts exist in workspace.
- **Phase 1.4: Bypassed Assertions, Mocks & Skips**: PASS — 0 mocks, 0 monkeypatches, 0 skips, and 0 xfails across `tests/test_quantum_adversarial.py`.
- **Phase 2.1: Behavioral Verification (Adversarial Suite)**: PASS — All 22 tests in `tests/test_quantum_adversarial.py` execute and pass cleanly in 5.98s.
- **Phase 2.2: Behavioral Verification (Quantum Unit Tests)**: PASS — All 38 unit tests in `engines/quantum/tests/` execute and pass cleanly in 7.71s.
- **Phase 2.3: Root Suite Discovery Verification**: PASS — All 60 collected tests execute and pass cleanly in 9.45s from project root.
- **Phase 2.4: Genuine Simulation Verification**: PASS — Stim and PyMatching are confirmed active (`HAS_STIM=True`, `HAS_PYMATCHING=True`), executing genuine detector error model generation and MWPM decoding (`is_genuine_simulation=True`).
- **Phase 2.5: Adversarial Stress Testing**: PASS — Canonical hashing verified sensitive to gate ordering, 8-decimal parameter precision, classical bit mapping, and hardware basis gates, while remaining invariant to circuit instance names.

---

## 1. Observation

### A. Source Code Inspection (`engines/quantum/src/plaq_quantum/optimizer.py`)
1. **Canonical Fingerprint Calculation (`optimizer.py:121-156`)**:
   - Lines 133–145: Replaces non-deterministic `circuit.name` with canonical register sizing:
     ```python
     hasher.update(f":qubits={circuit.num_qubits}:clbits={circuit.num_clbits}:".encode("utf-8"))
     for inst in circuit.data:
         op = inst.operation
         q_indices = [circuit.find_bit(q).index for q in inst.qubits]
         c_indices = [circuit.find_bit(c).index for c in inst.clbits]
         params_str = ",".join(
             f"{float(p):.8f}" if isinstance(p, (int, float)) else str(p)
             for p in op.params
         )
         cl_str = f"->{','.join(map(str, c_indices))}" if c_indices else ""
         hasher.update(f"{op.name}[{','.join(map(str, q_indices))}{cl_str}]:{params_str};".encode("utf-8"))
     ```
   - Lines 146–149: Incorporates sorted hardware coupling edges and sorted basis gates:
     ```python
     edges_str = str(sorted(hardware.get_coupling_edges(circuit.num_qubits)))
     basis_str = ",".join(sorted(hardware.basis_gates)) if hardware.basis_gates else ""
     hasher.update(f":hw={hardware.name}:{edges_str}:basis={basis_str}:".encode("utf-8"))
     hasher.update(f":opt={opt_level}:rout={routing_method}:lay={layout_method}:seed={seed}:".encode("utf-8"))
     ```
   - No hardcoded hash outputs or test bypass strings exist.

2. **Compilation Failure Error Handling (`optimizer.py:235-263`)**:
   - When Qiskit transpilation fails (`metrics is None`), `CostEstimationResult` is instantiated with explicit `feasibility_reason="Compilation failed with given routing/layout options."`, resolving the previous `TypeError`.
   - The returned `EvaluatedPlan` correctly sets `valid=False`, `physical_qubits=999_999`, and `total_cost_score=float("inf")`.

### B. Test Suite Inspection (`tests/test_quantum_adversarial.py`)
- Total lines: 524 lines.
- Total test functions: 22 across 4 test classes:
  - `TestLiveQuantumSimulations`: 9 tests
  - `TestParetoOptimizationCrossMatrix`: 4 tests
  - `TestCompilationCacheAndNumerics`: 6 tests
  - `TestEmpiricalDefectProofs`: 3 tests (`test_defect_compilation_failure_missing_feasibility_reason`, `test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits`, `test_defect_compilation_cache_basis_gates_omitted`)
- Inspection for bypasses:
  - `grep` for `(mock|monkeypatch|skip|xfail)`: 0 matches found.
  - `grep` for trivial assertions (`assert True`, `assert 1 == 1`): 0 matches found.
  - All `@pytest.mark.xfail` markers have been legitimately converted into strict assertions checking actual behavioral validity.

### C. Empirical Test Execution Outputs
1. **Adversarial Test Suite**:
   - Command: `pytest -v tests/test_quantum_adversarial.py`
   - Exit code: `0`
   - Raw output summary:
     ```text
     ============================= 22 passed in 5.98s ==============================
     ```
2. **Colocated Quantum Package Unit Tests**:
   - Command: `pytest -v engines/quantum/tests/`
   - Exit code: `0`
   - Raw output summary:
     ```text
     ============================= 38 passed in 7.71s ==============================
     ```
3. **Root Discovery Test Suite**:
   - Command: `pytest -v`
   - Exit code: `0`
   - Raw output summary:
     ```text
     ============================= 60 passed in 9.45s ==============================
     ```
4. **Live Stim/PyMatching Decoder Verification**:
   - Command:
     ```powershell
     python -c "from plaq_quantum.stim_bridge import run_surface_code_simulation, HAS_STIM, HAS_PYMATCHING; print('Stim:', HAS_STIM, 'PyMatching:', HAS_PYMATCHING); res = run_surface_code_simulation(3, 0.001, 100, 42); print('Genuine:', res.is_genuine_simulation, 'Decoder:', res.decoder_type, 'Errors:', res.logical_errors)"
     ```
   - Exit code: `0`
   - Output:
     ```text
     Stim: True PyMatching: True
     Genuine: True Decoder: MWPM via PyMatching Errors: 5
     ```

5. **Adversarial Boundary & Sensitivity Stress Tests**:
   - Gate order test (`H -> CX` vs `CX -> H`): Hash collision test exited with distinct digests (PASSED).
   - Parameter precision test (`RZ(1.23456780)` vs `RZ(1.23456781)`): Distinct digests (PASSED).
   - Classical register test: Distinct digests (PASSED).
   - Name-invariance test: Two distinct circuit objects with different `.name` yielded identical hashes and hit `CompilationCache` (`len(cache._cache) == 1`) (PASSED).
   - Transpilation failure test: Returned `res.valid == False` with `feasibility_reason` populated (PASSED).

---

## 2. Logic Chain

1. **Integrity Mode Specification**:
   - In accordance with `ORIGINAL_REQUEST.md:9` (`Integrity mode: development`), the project is audited against Development mode integrity criteria: catching fabricated verification outputs, hardcoded test results, facade implementations, and bypassed test assertions.

2. **Absence of Facades and Hardcoding**:
   - Static analysis of `optimizer.py` confirms that `compute_compilation_fingerprint` uses genuine cryptographic SHA-256 operations computed over circuit gate DAG data, parameter sequences, classical bits, hardware connectivity graphs, and sorted basis gates. No conditionals check for test names or return canned strings.
   - The fallback dataclass in `evaluate_plan` is an error-reporting representation of an unroutable compilation failure, returning `valid=False` and `cost=inf`, not a facade bypassing real computation.

3. **Absence of Test Dilution or Circumvention**:
   - `tests/test_quantum_adversarial.py` contains no mock objects, no monkeypatches, and no skipped assertions.
   - The removal of `@pytest.mark.xfail` in Iteration 2 converted defect reproductions into strict regression tests that assert the corrected behavior.

4. **Independent Execution Proof**:
   - Empirical execution of `pytest` across all suites verified that all 22 adversarial tests and all 38 base quantum tests genuinely run and pass.
   - Monte Carlo stabilizer simulation was verified to be running genuine Stim circuit generation and PyMatching MWPM decoding.

5. **Verdict Conclusion**:
   - All integrity forensics checks have passed without a single failure or warning.
   - The work product satisfies all integrity standards under `ORIGINAL_REQUEST.md`.

---

## 3. Caveats

- **Transpiler Seed Stability**: Deterministic caching relies on fixed transpiler seeds (`seed=42`) for stochastic layout/routing passes (such as Sabre routing), which is standard and expected behavior in compilation caches.
- **Scope Limit**: This audit specifically covered Milestone M1 Iteration 2 work products (`engines/quantum/src/plaq_quantum/optimizer.py`, `tests/test_quantum_adversarial.py`, and colocated quantum unit tests). Other milestones (M2–M5) remain out of M1 scope.

---

## 4. Conclusion

**Verdict: CLEAN**

Milestone M1 Iteration 2 has passed forensic integrity verification. The remediations to `optimizer.py` are genuine, mathematically sound, free of hardcoded results or facades, and backed by 60 passing tests executing without mocks, bypasses, or xfails.

---

## 5. Verification Method

To independently reproduce the forensic verification results:

1. **Verify Adversarial Test Suite Execution**:
   ```bash
   pytest -v tests/test_quantum_adversarial.py
   ```
   *Expected*: `22 passed` in ~6s, exit code 0.

2. **Verify Quantum Unit Test Suite Execution**:
   ```bash
   pytest -v engines/quantum/tests/
   ```
   *Expected*: `38 passed` in ~7s, exit code 0.

3. **Verify Full Root Test Discovery**:
   ```bash
   pytest -v
   ```
   *Expected*: `60 passed` in ~9s, exit code 0.

4. **Verify Absence of Mocks/Skips in Adversarial Suite**:
   ```powershell
   Select-String -Path "tests/test_quantum_adversarial.py" -Pattern "mock|skip|xfail"
   ```
   *Expected*: No matching lines found.

5. **Verify Live Stim/PyMatching Decoder**:
   ```powershell
   python -c "from plaq_quantum.stim_bridge import run_surface_code_simulation; res = run_surface_code_simulation(3, 0.001, 100); assert res.is_genuine_simulation is True; assert res.decoder_type == 'MWPM via PyMatching'; print('VERIFIED GENUINE')"
   ```
   *Expected*: Prints `VERIFIED GENUINE`, exit code 0.
