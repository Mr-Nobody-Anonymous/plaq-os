# BRIEFING — 2026-10-14T12:05:00Z

## Mission
Investigate Defects 2 & 3 in `compute_compilation_fingerprint` (circuit.name hashing causing cache misses and missing hardware.basis_gates causing collisions) and formulate exact fixes for canonical circuit hashing and basis gates inclusion.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigator, synthesizer
- Working directory: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2
- Original parent: 1f18b9cb-e1e8-4b00-9c69-021157944324
- Milestone: M1 Iteration 2 (Compilation Cache Explorer)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement in source code directly (only report / handoff / diff patches)
- Scoped to Defects 2 & 3 in compilation cache fingerprinting

## Current Parent
- Conversation ID: 1f18b9cb-e1e8-4b00-9c69-021157944324
- Updated: 2026-10-14T12:05:00Z

## Investigation State
- **Explored paths**:
  - `engines/quantum/src/plaq_quantum/optimizer.py` (lines 119–203: `compute_compilation_fingerprint` & `CompilationCache`)
  - `engines/quantum/src/plaq_quantum/hardware.py` (lines 16–60: `HardwareModel` and `basis_gates` definition)
  - `engines/quantum/src/plaq_quantum/circuits.py` (lines 26–60: circuit instantiation naming behavior)
  - `tests/test_quantum_adversarial.py` (lines 480–545: defect proofs for Defect 2 and Defect 3)
  - `engines/quantum/tests/test_optimizer.py` and `tests/test_optimizer.py` (base test suite caching coverage)
- **Key findings**:
  1. Defect 2 confirmed: `circuit.name` in Qiskit is automatically generated as `circuit-N` via a global counter if not explicitly supplied. Two identical calls to `make_test_circuit(4)` produce different names (`circuit-41` vs `circuit-42`), producing distinct SHA-256 digests and defeating caching.
  2. Defect 3 confirmed: `compute_compilation_fingerprint` omitted `hardware.basis_gates`. Two hardware instances with identical names and topologies but different native gate sets (e.g. CX vs CZ) yield identical fingerprints, leading to cache poisoning.
  3. Formulated canonical solution: (a) remove `circuit.name` and hash ordered gate sequence with qubit and clbit indices, (b) add `basis_str = ",".join(sorted(hardware.basis_gates))` to the hardware segment.
  4. Empirically tested with standalone scripts and monkeypatching: Defect 2 and Defect 3 adversarial tests pass completely, cache length remains 1 for duplicate circuit instances, and different basis gates generate separate cache entries.
- **Unexplored areas**: None within the scope of Defects 2 & 3. Defect 1 is assigned to Explorer 1.

## Key Decisions Made
- Canonical fingerprinting must omit `circuit.name` completely, as quantum circuit compilation depends purely on circuit structure and target hardware, not cosmetic circuit names.
- Also include classical bit indices (`inst.clbits`) to ensure measurements targeting different classical bits produce distinct fingerprints.
- Basis gates must be canonically sorted before joining into string to ensure order-invariant representation.
- Generated diff patch `fix_defects_2_3.patch`.

## Artifact Index
- `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2\handoff.md` — Final handoff report
- `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2\fix_defects_2_3.patch` — Diff patch for optimizer.py
- `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2\test_fix.py` — Standalone fix verification script
- `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2\test_cache_with_patch.py` — CompilationCache integration verification script
- `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2\test_adversarial_fixed.py` — Adversarial suite reproduction script
- `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2\progress.md` — Liveness & status tracking
- `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m1_fix_2\DISPATCH.md` — Incoming message log
