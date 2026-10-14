import pytest
from plaq_quantum.circuits import make_test_circuit
from plaq_quantum.hardware import DEMO_HARDWARE, HardwareModel
import plaq_quantum.optimizer as opt
from test_cache_with_patch import compute_compilation_fingerprint_fixed

# Patch
opt.compute_compilation_fingerprint = compute_compilation_fingerprint_fixed

def test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits():
    qc1 = make_test_circuit(n_qubits=4)
    qc2 = make_test_circuit(n_qubits=4)
    cache = opt.CompilationCache()

    m1 = cache.get_or_compile(qc1, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
    assert m1 is not None
    assert len(cache._cache) == 1

    m2 = cache.get_or_compile(qc2, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
    assert m2 is not None

    assert len(cache._cache) == 1, (
        f"Cache length grew to {len(cache._cache)}! circuit.name '{qc1.name}' vs '{qc2.name}' "
        f"caused different fingerprints for identical circuits."
    )
    print("Test 1 (Defect 2) Passed!")

def test_defect_compilation_cache_basis_gates_omitted():
    qc = make_test_circuit(n_qubits=3)
    hw_cx = DEMO_HARDWARE
    hw_cz = HardwareModel(
        name=DEMO_HARDWARE.name,
        technology="superconducting",
        single_qubit_error=1e-4,
        two_qubit_error=1e-3,
        measurement_error=1e-3,
        single_qubit_time_ns=30.0,
        two_qubit_time_ns=200.0,
        measurement_time_ns=500.0,
        surface_code_cycle_time_ns=1000.0,
        topology_type="linear",
        basis_gates=("cz", "rz", "sx", "x"),
    )

    fp1 = opt.compute_compilation_fingerprint(qc, hw_cx, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
    fp2 = opt.compute_compilation_fingerprint(qc, hw_cz, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)

    assert fp1 != fp2, "Fingerprint collision detected! Basis gates are not included in compilation fingerprint."
    print("Test 2 (Defect 3) Passed!")

if __name__ == "__main__":
    test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits()
    test_defect_compilation_cache_basis_gates_omitted()
    print("All adversarial defect tests for Defect 2 and Defect 3 pass!")
