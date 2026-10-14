# Handoff Report — Explorer 2 (Compilation Cache Explorer)

**Milestone**: M1 Iteration 2 (Compilation Cache Explorer)  
**Agent**: Explorer 2 (Investigator, Synthesizer)  
**Date**: 2026-10-14  
**Target Defects**: Defect 2 (Circuit Name Cache Misses) & Defect 3 (Missing Basis Gates Collision)  

---

## 1. Observation

Direct empirical observations from inspecting the codebase, running Qiskit runtime behavior experiments, executing adversarial test suites, and analyzing `engines/quantum/src/plaq_quantum/optimizer.py`:

### A. Observation 1 — Defect 2 (Circuit Name Invalidation)
- **File**: `engines/quantum/src/plaq_quantum/optimizer.py`, line 134:
  ```python
  hasher = hashlib.sha256()
  hasher.update(circuit.name.encode("utf-8"))
  hasher.update(f":{circuit.num_qubits}:{circuit.num_clbits}:".encode("utf-8"))
  ```
- **Qiskit Behavior**: In Qiskit 2.5.2 (and all standard Qiskit releases), any `QuantumCircuit` instantiated without an explicit `name` parameter increments an internal global counter (`_circuit_counter`) and assigns `circuit.name = f"circuit-{_circuit_counter}"`.
- **Empirical Proof**:
  Executing:
  ```powershell
  python -c "from qiskit import QuantumCircuit; c1 = QuantumCircuit(2); c2 = QuantumCircuit(2); print(c1.name, c2.name)"
  ```
  Yielded verbatim:
  ```text
  circuit-41 circuit-42
  ```
- **Adversarial Defect Proof**:
  In `tests/test_quantum_adversarial.py`, line 487 (`test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits`):
  Two successive calls to `make_test_circuit(4)` yielded `circuit-41` and `circuit-42`. When compiled with `CompilationCache.get_or_compile`, `len(cache._cache)` grew from 1 to 2, causing a cache miss on every new circuit instance and defeating cross-task and cross-query caching.

### B. Observation 2 — Defect 3 (Omission of Hardware Basis Gates)
- **File**: `engines/quantum/src/plaq_quantum/optimizer.py`, lines 142–144:
  ```python
  edges_str = str(sorted(hardware.get_coupling_edges(circuit.num_qubits)))
  hasher.update(f":hw={hardware.name}:{edges_str}:".encode("utf-8"))
  hasher.update(f":opt={opt_level}:rout={routing_method}:lay={layout_method}:seed={seed}:".encode("utf-8"))
  ```
- **Transpilation Dependency**:
  In `CompilationCache.get_or_compile` (lines 187–195):
  ```python
  compiled = transpile(
      circuit,
      coupling_map=coupling_map,
      basis_gates=list(hardware.basis_gates),
      optimization_level=opt_level,
      routing_method=routing_method,
      layout_method=layout_method,
      seed_transpiler=seed,
  )
  ```
  `transpile()` explicitly depends on `basis_gates=list(hardware.basis_gates)`.
- **Adversarial Defect Proof**:
  In `tests/test_quantum_adversarial.py`, line 519 (`test_defect_compilation_cache_basis_gates_omitted`):
  When compiling on two hardware targets sharing name and linear topology but differing in basis gates (`('rz', 'sx', 'x', 'cx')` vs `('cz', 'rz', 'sx', 'x')`), both produced identical fingerprints:
  ```python
  assert fp1 != fp2  # Fails: fp1 == fp2
  ```
  This leads to cache poisoning: CX-transpiled circuit metrics are served for a CZ-native hardware target.

### C. Observation 3 — Classical Bit Routing in Fingerprinting
- In `optimizer.py` lines 136–140:
  ```python
  for inst in circuit.data:
      op = inst.operation
      q_indices = [circuit.find_bit(q).index for q in inst.qubits]
      params_str = ",".join(f"{float(p):.8f}" for p in op.params if isinstance(p, (int, float)))
      hasher.update(f"{op.name}[{','.join(map(str, q_indices))}]:{params_str};".encode("utf-8"))
  ```
  Classical register bit indices (`inst.clbits`) are omitted from the gate string. For circuits with measurement gates (`measure q[0] -> c[0]` vs `measure q[0] -> c[1]`), distinguishing classical bits is necessary for canonical representation.

---

## 2. Logic Chain

1. **Step 1 (Circuit Name Irrelevance)**: Quantum circuit compilation transforms an input DAG of quantum operations into a hardware-compliant DAG targeting a specific coupling map and basis gate set. The human/Python name assigned to the circuit (`circuit.name`) has zero operational effect on transpilation output. Incorporating `circuit.name` couples cache keys to the Python process's instantiation counter rather than the circuit's structural semantics.
2. **Step 2 (Canonical Circuit Structural Hash)**: Removing `circuit.name` and relying on:
   - Total qubit and classical bit count (`:qubits={circuit.num_qubits}:clbits={circuit.num_clbits}:`)
   - Ordered instruction stream (`inst in circuit.data`)
   - Operation name (`op.name`)
   - Ordered qubit indices (`[circuit.find_bit(q).index for q in inst.qubits]`)
   - Classical bit destination indices (`[circuit.find_bit(c).index for c in inst.clbits]`)
   - Operation parameters (floats formatted to 8 decimals or strings for symbolic expressions)
   guarantees that any two structurally identical quantum circuits produce the exact same canonical hash regardless of object identity, variable name, or creation order.
3. **Step 3 (Hardware Basis Gates Essentiality)**: Because Qiskit transpilation maps high-level gates into `hardware.basis_gates`, changing the native basis gates changes the decomposition (e.g., decomposing SWAP or CNOT into CX vs CZ + single-qubit rotations). Thus `hardware.basis_gates` is a primary compilation parameter.
4. **Step 4 (Canonical Hardware Hash)**: Sorting `hardware.basis_gates` into `basis_str = ",".join(sorted(hardware.basis_gates))` ensures set-equivalence (e.g. `('cx', 'rz', 'sx', 'x')` and `('rz', 'sx', 'x', 'cx')` produce the identical string `"cx,rz,sx,x"`). Incorporating this into `:hw={hardware.name}:{edges_str}:basis={basis_str}:` guarantees that hardware targets with differing basis gates produce strictly distinct fingerprints, preventing cache collisions and cache poisoning.
5. **Step 5 (Empirical Validation)**: Testing the proposed implementation with a standalone integration harness confirmed:
   - Two separate instances of `make_test_circuit(4)` produce identical fingerprints and hit `cache._cache` without cache growth (`len == 1`).
   - Hardware with `cz` vs `cx` basis gates produces different fingerprints (`len == 2`).
   - All 6 sensitivity variations (seeds, optimization levels, hardware profiles, routing methods, mutated gates) continue to produce distinct fingerprints.
   - All 38 existing unit tests pass without regression.

---

## 3. Caveats

- **Transpiler Non-Determinism without Seed**: If `seed_transpiler` is omitted, Qiskit's stochastic passes (e.g. Sabre routing) may produce slightly different metrics across runs. However, `CompilationCache.get_or_compile` defaults `seed=42`, and `seed` is included in the fingerprint, ensuring reproducible results.
- **Symbolic Parameters**: If a circuit contains Qiskit `Parameter` objects, `str(p)` is hashed instead of `float(p)`. For non-bound parametric circuits, caching will differentiate parameter names.
- **Defect 1**: Crash in `evaluate_plan` when transpilation returns `None` is being investigated by Explorer 1 and is separate from compilation fingerprinting.

---

## 4. Conclusion

Defects 2 and 3 can be cleanly and completely resolved by replacing lines 133–145 of `engines/quantum/src/plaq_quantum/optimizer.py` with canonical circuit structural hashing and sorted basis gate representation.

### Concrete Recommended Implementation

In `engines/quantum/src/plaq_quantum/optimizer.py`, replace `compute_compilation_fingerprint`:

```python
def compute_compilation_fingerprint(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    opt_level: int,
    routing_method: str,
    layout_method: str,
    seed: int,
) -> str:
    """
    Generate cryptographically unique SHA-256 canonical fingerprint for a compilation pass.
    Includes ordered gates, parameter floats, qubit/clbit registers, hardware coupling graph,
    hardware basis gates, and compiler seed. Excludes volatile circuit.name.
    """
    hasher = hashlib.sha256()
    # Canonical circuit structure: omit volatile circuit.name (which has auto-incrementing id 'circuit-N' in Qiskit)
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

    edges_str = str(sorted(hardware.get_coupling_edges(circuit.num_qubits)))
    basis_str = ",".join(sorted(hardware.basis_gates)) if hardware.basis_gates else ""
    hasher.update(f":hw={hardware.name}:{edges_str}:basis={basis_str}:".encode("utf-8"))
    hasher.update(f":opt={opt_level}:rout={routing_method}:lay={layout_method}:seed={seed}:".encode("utf-8"))
    try:
        import qiskit
        hasher.update(f"qiskit={qiskit.__version__}".encode("utf-8"))
    except Exception:
        pass
    return hasher.hexdigest()
```

### Accompanying Test Updates
In `tests/test_quantum_adversarial.py`, remove `@pytest.mark.xfail(...)` from:
1. `test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits` (lines 479–510)
2. `test_defect_compilation_cache_basis_gates_omitted` (lines 511–545)

And in `engines/quantum/tests/test_optimizer.py`, add assertions to `test_compilation_cache_fingerprint` to verify cache hits across distinct circuit instances and distinct fingerprints across different basis gates.

### Diff Patch Reference
A ready-to-apply diff patch is available at:
`C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2\fix_defects_2_3.patch`

---

## 5. Verification Method

1. **Verify with Standalone Test Script**:
   ```powershell
   python .agents/teamwork/explorer_m1_fix_2/test_adversarial_fixed.py
   ```
   *Expected*: Prints:
   ```text
   CompilationCache across distinct circuit instances test passed: cache hit confirmed (cache len = 1)!
   CompilationCache different basis gates test passed: separate cache entry created (cache len = 2)!
   Test 1 (Defect 2) Passed!
   Test 2 (Defect 3) Passed!
   All adversarial defect tests for Defect 2 and Defect 3 pass!
   ```

2. **Verify Base Test Suite Remains 100% Passing**:
   ```powershell
   pytest engines/quantum/tests -v
   ```
   *Expected*: 38 passed.

3. **Verify Adversarial Suite Post-Fix**:
   ```powershell
   pytest tests/test_quantum_adversarial.py -k "test_defect_compilation_cache" -v
   ```
   *Expected*: Both `test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits` and `test_defect_compilation_cache_basis_gates_omitted` pass cleanly without `XFAIL`.

4. **Invalidation Conditions**:
   - If calling `cache.get_or_compile` on two separate calls of `make_test_circuit(4)` results in `len(cache._cache) > 1`.
   - If compiling for two hardware models with different basis gates produces identical fingerprints.
