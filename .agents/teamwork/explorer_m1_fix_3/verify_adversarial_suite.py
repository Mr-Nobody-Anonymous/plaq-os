"""
Test all 22 tests in test_quantum_adversarial.py with defects fixed and xfails converted to regular assertions.
"""

import sys
import hashlib
from typing import Optional
import pytest
from plaq_quantum.circuits import make_test_circuit, make_qft_circuit
from plaq_quantum.hardware import DEMO_HARDWARE, HardwareModel
from plaq_quantum.cost_model import CostEstimationResult, evaluate_fault_tolerant_cost
from plaq_quantum.optimizer import (
    ExecutionPlan,
    EvaluatedPlan,
    CompilationCache,
    DECODER_LATENCY_SPECS,
)
import plaq_quantum.optimizer as opt

# ==============================================================================
# PROPOSED PATCHES
# ==============================================================================

def patched_compute_compilation_fingerprint(
    circuit,
    hardware,
    opt_level: int,
    routing_method: str,
    layout_method: str,
    seed: int,
) -> str:
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


def patched_evaluate_plan(
    circuit,
    hardware,
    plan: ExecutionPlan,
    target_epsilon: float = 1e-3,
    compilation_cache: Optional[CompilationCache] = None,
    weight_qubits: float = 1.0,
    weight_time: float = 1.0,
) -> EvaluatedPlan:
    if not opt.HAS_QISKIT:
        raise RuntimeError("Qiskit is required to compile and evaluate candidate plans.")

    if compilation_cache is None:
        compilation_cache = CompilationCache()

    metrics = compilation_cache.get_or_compile(
        circuit=circuit,
        hardware=hardware,
        opt_level=plan.optimization_level,
        routing_method=plan.routing_method,
        layout_method=plan.layout_method,
        seed=plan.transpiler_seed,
    )

    if metrics is None:
        dummy_result = CostEstimationResult(
            valid=False,
            feasibility_reason="Compilation failed with given routing/layout options.",
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
        return EvaluatedPlan(
            plan=plan,
            cost_result=dummy_result,
            physical_qubits=999_999,
            runtime_seconds=999.0,
            failure_probability=1.0,
            code_distance=0,
            total_cost_score=float("inf"),
            valid=False,
        )

    d_offset = 0 if plan.code_distance_strategy == "minimal_safe" else 2
    decoder_latency = DECODER_LATENCY_SPECS.get(plan.decoder_architecture, hardware.decoder_latency_ns_per_cycle)

    cost_result = evaluate_fault_tolerant_cost(
        metrics=metrics,
        hardware=hardware,
        target_epsilon=target_epsilon,
        num_magic_factories=plan.num_magic_factories,
        code_family=plan.code_family,
        decoder_latency_ns=decoder_latency,
        weight_qubits=weight_qubits,
        weight_time=weight_time,
    )

    if d_offset > 0 and cost_result.valid:
        new_d = cost_result.code_distance + d_offset
        cost_result = evaluate_fault_tolerant_cost(
            metrics=metrics,
            hardware=hardware,
            target_epsilon=target_epsilon,
            num_magic_factories=plan.num_magic_factories,
            code_family=plan.code_family,
            code_distance_override=new_d,
            decoder_latency_ns=decoder_latency,
            weight_qubits=weight_qubits,
            weight_time=weight_time,
        )

    return EvaluatedPlan(
        plan=plan,
        cost_result=cost_result,
        physical_qubits=cost_result.physical_qubits,
        runtime_seconds=cost_result.runtime_seconds,
        failure_probability=cost_result.failure_probability,
        code_distance=cost_result.code_distance,
        total_cost_score=cost_result.total_cost_score,
        valid=cost_result.valid,
    )


# Apply patches
opt.compute_compilation_fingerprint = patched_compute_compilation_fingerprint
opt.evaluate_plan = patched_evaluate_plan

# Import tests from test_quantum_adversarial
sys.path.insert(0, ".")
import tests.test_quantum_adversarial as tqa

# Monkeypatch the 3 defect methods in tqa.TestEmpiricalDefectProofs to regular assertions
def patched_test_defect_1(self):
    qc = make_qft_circuit(4)
    plan_failing_routing = ExecutionPlan(
        optimization_level=0,
        routing_method="lookahead",
        layout_method="trivial",
        num_magic_factories=1,
        code_distance_strategy="minimal_safe",
        decoder_architecture="streaming_asic",
    )
    res = opt.evaluate_plan(circuit=qc, hardware=DEMO_HARDWARE, plan=plan_failing_routing)
    assert res.valid is False
    assert res.physical_qubits == 999_999
    assert res.total_cost_score == float("inf")
    assert res.cost_result.feasibility_reason == "Compilation failed with given routing/layout options."

def patched_test_defect_2(self):
    qc1 = make_test_circuit(n_qubits=4)
    qc2 = make_test_circuit(n_qubits=4)
    cache = opt.CompilationCache()

    m1 = cache.get_or_compile(qc1, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
    assert m1 is not None
    assert len(cache._cache) == 1

    m2 = cache.get_or_compile(qc2, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
    assert m2 is not None
    assert len(cache._cache) == 1

def patched_test_defect_3(self):
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
    assert fp1 != fp2

tqa.TestEmpiricalDefectProofs.test_defect_compilation_failure_missing_feasibility_reason = patched_test_defect_1
tqa.TestEmpiricalDefectProofs.test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits = patched_test_defect_2
tqa.TestEmpiricalDefectProofs.test_defect_compilation_cache_basis_gates_omitted = patched_test_defect_3

print("=== Running All 22 Adversarial Tests (with defects converted to passing assertions) ===")
res2 = pytest.main(["tests/test_quantum_adversarial.py", "-v"])
if res2 != 0:
    print(f"FAILED: Adversarial tests exited with code {res2}")
    sys.exit(res2)
print("\nSUCCESS: All 22 adversarial tests passed cleanly!")
