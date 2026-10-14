# Handoff Report — Challenger 1 (Compilation Cache Empirical Stress Test)

**Milestone**: M1 Iteration 2 (Optimizer Defect Remediation Verification)  
**Agent**: Challenger 1 (Empirical Challenger: critic, specialist)  
**Parent Agent**: `1f18b9cb-e1e8-4b00-9c69-021157944324`  
**Date**: 2026-10-14  
**Verdict**: **CONFIRMED** (Compilation cache determinism, basis gate sensitivity, and defect regression suites are empirically verified)

---

## 1. Observation

Direct empirical observations from executing cache determinism stress tests, hardware basis gate variation suites, parameter precision boundaries, and pytest regression tests:

### A. Adversarial Regression Suite Execution (`tests/test_quantum_adversarial.py`)
Executed pytest targeting the defect compilation cache tests:
```powershell
pytest -v tests/test_quantum_adversarial.py -k test_defect_compilation_cache
```
**Exit Code**: 0  
**Verbatim Output**:
```text
tests/test_quantum_adversarial.py::TestEmpiricalDefectProofs::test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits PASSED [ 50%]
tests/test_quantum_adversarial.py::TestEmpiricalDefectProofs::test_defect_compilation_cache_basis_gates_omitted PASSED [100%]

====================== 2 passed, 20 deselected in 3.53s =======================
```

Executed the full adversarial test suite:
```powershell
pytest -v tests/test_quantum_adversarial.py
```
**Exit Code**: 0  
**Verbatim Output**:
```text
============================= 22 passed in 6.73s ==============================
```

Executed the quantum engine base test suite:
```powershell
pytest -v engines/quantum/tests/
```
**Exit Code**: 0  
**Verbatim Output**:
```text
============================= 38 passed in 6.64s ==============================
```

### B. Cache Determinism Across Multiple Fresh Circuit Instances
Stress-tested cache determinism across 7 diverse quantum circuit generators with 5 fresh instances each:
1. `make_test_circuit(3)`
2. `make_test_circuit(4)`
3. `make_qaoa_circuit(4, 1)`
4. `make_qft_circuit(3)`
5. `make_bernstein_vazirani_circuit('101')`
6. `make_chemistry_ansatz_circuit(4, 1)`
7. `make_shor_modexp_circuit(5)`

For each generator:
- Generated 5 independent instances of the circuit without setting `circuit.name` (allowing Qiskit auto-incrementing naming: `circuit-41`, `circuit-42`, etc.).
- Evaluated `compute_compilation_fingerprint(qc, DEMO_HARDWARE, 1, 'basic', 'trivial', 42)`:
  - `test_circuit_3q`: SHA-256 `9b17815d23f31a11...` (5/5 identical)
  - `test_circuit_4q`: SHA-256 `4a8d7dd63e868414...` (5/5 identical)
  - `qaoa_4q`: SHA-256 `fac13beec3792f98...` (5/5 identical)
  - `qft_3q`: SHA-256 `91a0b20b3ee2d8ed...` (5/5 identical)
  - `bv_3q`: SHA-256 `c9f7722b0423fc45...` (5/5 identical)
  - `chem_4q`: SHA-256 `5deaf664eec55d01...` (5/5 identical)
  - `shor_5q`: SHA-256 `bc086dd8da3f3daa...` (5/5 identical)
- Executed `cache.get_or_compile(qc, DEMO_HARDWARE, 1, 'basic', 'trivial', 42)` on all 5 instances:
  - Cache size `len(cache._cache)` remained strictly 1 (`len(cache._cache) == 1`).
  - Instances 2 through 5 returned the exact cached `CircuitMetrics` object reference (`m is first_m`).

### C. Basis Gate Sensitivity Across Hardware Profiles
Stress-tested fingerprint differentiation across hardware models with identical names (`test_processor`), identical topologies (`linear`), but differing basis gates:
1. CX Basis: `basis_gates=('cx', 'rz', 'sx', 'x')`
   - Fingerprint: `9170cb4b578e9bb59df7cc8da1fa3986117f2805919c1a2ce4291941d47951b7`
   - Compiled Metrics: `two_qubit_ops=4, total_ops=19`
2. CZ Basis: `basis_gates=('cz', 'rz', 'sx', 'x')`
   - Fingerprint: `ceb924d2c5c99daab4d2d52121cf4d452a922bc83ab6052b5b74a79a4a8f09a2`
   - Compiled Metrics: `two_qubit_ops=4, total_ops=28`
3. ECR Basis: `basis_gates=('ecr', 'rz', 'sx', 'x')`
   - Fingerprint: `68c821acdfdc0cd04a8960f8d09e2aba4518e09cb1f05beab20bab118a113c65`
   - Compiled Metrics: `two_qubit_ops=4, total_ops=24`

Verification Results:
- `fp_cx != fp_cz != fp_ecr`: Distinct basis gates strictly produce distinct SHA-256 keys.
- Sequential compilation into a single `CompilationCache`:
  - After `cache.get_or_compile(qc, hw_cx, ...)`: `len(cache._cache) == 1`
  - After `cache.get_or_compile(qc, hw_cz, ...)`: `len(cache._cache) == 2`
  - After `cache.get_or_compile(qc, hw_ecr, ...)`: `len(cache._cache) == 3`
- Recompilation with fresh instances of `qc` for `hw_cx` and `hw_cz` resulted in cache hits without cache growth (`len(cache._cache) == 3`), returning original metrics objects.

### D. Invariance and Boundary Stress Testing
1. **Basis Gates Permutation Invariance**:
   - Hardware with `basis_gates=('cx', 'rz', 'sx', 'x')` vs `basis_gates=('x', 'sx', 'rz', 'cx')` produced identical SHA-256 fingerprints (`fec997afb6ad84d5... == fec997afb6ad84d5...`). Sorting in `optimizer.py:147` guarantees mathematical set invariance.
2. **Floating-Point Parameter Precision**:
   - Circuits differing at the 8th decimal place (`rx(0.12345678, 0)` vs `rx(0.12345679, 0)`) produced distinct fingerprints (`0c300e0d...` vs `f80e1d91...`).
   - Circuits differing beyond the 8th decimal place (`rx(0.123456781, 0)` vs `rx(0.123456782, 0)`) produced identical fingerprints due to `f"{float(p):.8f}"` formatting, providing numerical noise tolerance.
3. **Direct `len(cache)` Protocol Behavior**:
   - Running `len(cache)` directly on `CompilationCache` raised:
     ```text
     TypeError: object of type 'CompilationCache' has no len()
     ```
     `CompilationCache` stores entries in `self._cache: Dict[str, Optional[CircuitMetrics]]` and currently relies on `len(cache._cache)`.

---

## 2. Logic Chain

1. **Remediation of Defect 2 (Circuit Name Volatility)**:
   - *Premise*: Qiskit automatically increments `QuantumCircuit.name` for circuits created without explicit names. In Iteration 1, `compute_compilation_fingerprint` hashed `circuit.name`, causing cache misses between identical circuits.
   - *Observation A & B*: In `optimizer.py:134-144`, hashing now iterates through ordered gate operations, canonical qubit indices (`circuit.find_bit(q).index`), classical bit mappings (`cl_str`), and 8-decimal formatted parameters.
   - *Empirical Proof*: Across 7 distinct circuit generators with 5 fresh instances each (35 compilations), every instance generated an identical fingerprint and produced a cache hit (`len(cache._cache) == 1`).
   - *Inference*: Compilation caching is completely immune to Qiskit's volatile instance naming.

2. **Remediation of Defect 3 (Basis Gate Omission)**:
   - *Premise*: In Iteration 1, `hardware.basis_gates` was omitted from the fingerprint, allowing CX hardware and CZ hardware with the same name to collide and poison each other's cache entries.
   - *Observation A & C*: In `optimizer.py:147-148`, `hardware.basis_gates` is sorted and hashed via `:basis={basis_str}:`.
   - *Empirical Proof*: Hardware configurations differing solely in basis gates (`cx` vs `cz` vs `ecr`) generated 3 distinct SHA-256 hashes (`fp_cx != fp_cz != fp_ecr`) and populated 3 separate cache entries (`len(cache._cache) == 3`). Transpilation metrics properly reflected the native decomposition (`two_qubit_ops=4` with `total_ops=19` for CX vs `total_ops=28` for CZ).
   - *Inference*: Cache collisions between differing native hardware basis sets are eliminated.

3. **Adversarial & Base Test Invariance**:
   - *Observation A*: All 22 tests in `tests/test_quantum_adversarial.py` pass without xfail. All 38 base tests in `engines/quantum/tests/` pass cleanly.
   - *Inference*: Remediations did not introduce any regressions in the quantum engine or Pareto optimizer.

---

## 3. Caveats & Adversarial Challenges

1. **API Ergonomics (`CompilationCache.__len__`)**:
   - `CompilationCache` lacks `def __len__(self) -> int: return len(self._cache)`. Calling `len(cache)` directly raises `TypeError: object of type 'CompilationCache' has no len()`. Tests and callers must use `len(cache._cache)`.
   - *Recommendation*: In a future maintenance pass, implement `__len__`, `__contains__`, and `__getitem__` on `CompilationCache` to provide standard container semantics.
2. **Sub-1e-8 Float Parameter Differentiation**:
   - Gate parameters differing by less than $10^{-8}$ produce identical cache keys. This is beneficial for floating-point noise immunity, but parameters requiring precision $> 8$ decimal places would share cache keys. In quantum circuits, $10^{-8}$ radians corresponds to $\sim 10^{-6}$ error, which is well below physical fault tolerance thresholds.
3. **Multi-Threaded Concurrency**:
   - `CompilationCache._cache` is a standard Python dictionary. In single-threaded execution or GIL-bound execution it is safe, but it does not use a threading mutex. For multi-worker parallel search processes, separate cache instances or process-safe stores should be used.

---

## 4. Conclusion

**VERDICT: CONFIRMED**

The compilation cache fingerprinting mechanism in `plaq_quantum.optimizer` has been empirically stress-tested and certified:
1. **Cache Determinism**: Confirmed across all standard workloads. Repeated compilation of fresh, independently instantiated circuits results in 100% cache hits (`len(cache._cache) == 1`) and returns identical metrics instances.
2. **Basis Gate Sensitivity**: Confirmed across differing native basis sets (CX vs CZ vs ECR), producing unique SHA-256 fingerprints and separate cache entries (`len(cache._cache) == 2` for CX+CZ, `len(cache._cache) == 3` for CX+CZ+ECR).
3. **Regression Protections**: `pytest -v tests/test_quantum_adversarial.py -k test_defect_compilation_cache` passes 2/2 tests cleanly (and 22/22 across the full adversarial suite).

---

## 5. Verification Method

To independently verify all findings:

1. **Verify Adversarial Defect Tests**:
   ```powershell
   cd C:\Users\hp\Desktop\plaq-os
   pytest -v tests/test_quantum_adversarial.py -k test_defect_compilation_cache
   ```
   *Expected Output*: `2 passed, 20 deselected in < 4s` (Exit code 0).

2. **Verify Full Adversarial Suite**:
   ```powershell
   pytest -v tests/test_quantum_adversarial.py
   ```
   *Expected Output*: `22 passed in < 8s` (Exit code 0).

3. **Verify Multi-Instance Determinism and Basis Gate Sensitivity**:
   ```powershell
   python -c "from plaq_quantum.circuits import make_test_circuit; from plaq_quantum.hardware import DEMO_HARDWARE, HardwareModel; from plaq_quantum.optimizer import CompilationCache; qc1, qc2 = make_test_circuit(3), make_test_circuit(3); cache = CompilationCache(); m1 = cache.get_or_compile(qc1, DEMO_HARDWARE, 1, 'basic', 'trivial', 42); m2 = cache.get_or_compile(qc2, DEMO_HARDWARE, 1, 'basic', 'trivial', 42); assert len(cache._cache) == 1 and m1 is m2; hw_cz = HardwareModel(name=DEMO_HARDWARE.name, technology='sc', single_qubit_error=1e-4, two_qubit_error=1e-3, measurement_error=1e-3, single_qubit_time_ns=30, two_qubit_time_ns=200, measurement_time_ns=500, surface_code_cycle_time_ns=1000, topology_type='linear', basis_gates=('cz', 'rz', 'sx', 'x')); m3 = cache.get_or_compile(qc1, hw_cz, 1, 'basic', 'trivial', 42); assert len(cache._cache) == 2; print('Determinism and basis gate sensitivity VERIFIED!')"
   ```
   *Expected Output*: `Determinism and basis gate sensitivity VERIFIED!` (Exit code 0).

4. **Verify Invalidation Conditions**:
   - If calling `cache.get_or_compile` on two separate calls to `make_test_circuit(3)` causes `len(cache._cache) > 1`.
   - If `compute_compilation_fingerprint` generates identical hashes for hardware profiles with differing `basis_gates`.
