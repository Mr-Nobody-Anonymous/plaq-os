import hashlib
from plaq_quantum.circuits import make_test_circuit
from plaq_quantum.hardware import DEMO_HARDWARE, HardwareModel

def compute_compilation_fingerprint_fixed(circuit, hardware, opt_level, routing_method, layout_method, seed):
    hasher = hashlib.sha256()
    hasher.update(f":qubits={circuit.num_qubits}:clbits={circuit.num_clbits}:".encode("utf-8"))
    for inst in circuit.data:
        op = inst.operation
        q_indices = [circuit.find_bit(q).index for q in inst.qubits]
        c_indices = [circuit.find_bit(c).index for c in inst.clbits]
        params_str = ",".join(f"{float(p):.8f}" for p in op.params if isinstance(p, (int, float)))
        cl_str = f"->{','.join(map(str, c_indices))}" if c_indices else ""
        hasher.update(f"{op.name}[{','.join(map(str, q_indices))}{cl_str}]:{params_str};".encode("utf-8"))

    edges_str = str(sorted(hardware.get_coupling_edges(circuit.num_qubits)))
    basis_str = ",".join(sorted(hardware.basis_gates))
    hasher.update(f":hw={hardware.name}:{edges_str}:basis={basis_str}:".encode("utf-8"))
    hasher.update(f":opt={opt_level}:rout={routing_method}:lay={layout_method}:seed={seed}:".encode("utf-8"))
    try:
        import qiskit
        hasher.update(f"qiskit={qiskit.__version__}".encode("utf-8"))
    except Exception:
        pass
    return hasher.hexdigest()

# Test Defect 2:
qc1 = make_test_circuit(4)
qc2 = make_test_circuit(4)
print(f"qc1 name: {qc1.name}, qc2 name: {qc2.name}")
fp1 = compute_compilation_fingerprint_fixed(qc1, DEMO_HARDWARE, 1, "basic", "trivial", 42)
fp2 = compute_compilation_fingerprint_fixed(qc2, DEMO_HARDWARE, 1, "basic", "trivial", 42)
print("Defect 2 Test - Same circuit different instances:", fp1 == fp2)
assert fp1 == fp2, "fp1 and fp2 must be identical"

# Test Defect 3:
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
fp_cx = compute_compilation_fingerprint_fixed(qc1, hw_cx, 1, "basic", "trivial", 42)
fp_cz = compute_compilation_fingerprint_fixed(qc1, hw_cz, 1, "basic", "trivial", 42)
print("Defect 3 Test - Different basis gates different fp:", fp_cx != fp_cz)
assert fp_cx != fp_cz, "fp_cx and fp_cz must be different"
print("ALL TESTS PASSED SUCCESSFULLY!")
