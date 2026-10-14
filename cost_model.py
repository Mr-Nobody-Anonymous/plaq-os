"""
Q-Day OS Fault-Tolerant Resource and Reliability Cost Model

Calculates:
1. Circuit-level metrics (qubits, depth, gates, T-count, Clifford operations)
2. Fault-tolerant surface code & Quantum LDPC (qLDPC) parameters
3. Multi-level magic state distillation factory sizing (15-to-1 & two-level cascades)
4. Classical decoding throughput & backlog latency
5. End-to-end physical qubit footprint, wall-clock execution time, and failure probability
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from hardware import HardwareModel, DEMO_HARDWARE

try:
    from qiskit import QuantumCircuit
    HAS_QISKIT = True
except ImportError:
    HAS_QISKIT = False


@dataclass(frozen=True)
class CircuitMetrics:
    """Quantitative profile of a quantum circuit."""
    num_qubits: int
    depth: int
    total_ops: int
    single_qubit_ops: int
    two_qubit_ops: int
    t_ops: int
    measurement_ops: int
    operation_counts: Dict[str, int]


@dataclass(frozen=True)
class CostEstimationResult:
    """Detailed fault-tolerant execution cost report."""
    valid: bool
    physical_qubits: int
    runtime_seconds: float
    failure_probability: float
    code_distance: int
    factory_code_distance: int
    num_factories: int
    data_physical_qubits: int
    factory_physical_qubits: int
    total_surface_code_cycles: int
    decoder_stall_factor: float
    spacetime_volume: int
    total_cost_score: float
    assumptions: Dict[str, Any]
    diagnostics: List[str] = field(default_factory=list)

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "physical_qubits": self.physical_qubits,
            "runtime_s": round(self.runtime_seconds, 6),
            "failure_prob": f"{self.failure_probability:.3e}",
            "code_distance": self.code_distance,
            "num_factories": self.num_factories,
            "cycles": self.total_surface_code_cycles,
            "decoder_stall": round(self.decoder_stall_factor, 2),
            "spacetime_volume": self.spacetime_volume,
            "diagnostics": self.diagnostics,
        }


def extract_circuit_metrics(circuit: Any) -> CircuitMetrics:
    """
    Extract operation counts, depth, and non-Clifford T-gate count from a circuit.
    """
    if not HAS_QISKIT or not isinstance(circuit, QuantumCircuit):
        raise TypeError("Expected a valid Qiskit QuantumCircuit instance.")

    op_counts: Dict[str, int] = dict(circuit.count_ops())
    num_qubits = circuit.num_qubits
    depth = circuit.depth()
    total_ops = circuit.size()

    t_gates = {"t", "tdg"}
    two_qubit_gates = {"cx", "cz", "ecr", "swap", "cp", "rxx", "ryy", "rzz", "ch"}
    measurement_gates = {"measure"}

    t_ops = sum(count for gate, count in op_counts.items() if gate in t_gates)
    two_qubit_ops = sum(count for gate, count in op_counts.items() if gate in two_qubit_gates)
    meas_ops = sum(count for gate, count in op_counts.items() if gate in measurement_gates)

    single_qubit_ops = sum(
        count for gate, count in op_counts.items()
        if gate not in two_qubit_gates and gate not in measurement_gates and gate != "barrier"
    )

    return CircuitMetrics(
        num_qubits=num_qubits,
        depth=depth,
        total_ops=total_ops,
        single_qubit_ops=single_qubit_ops,
        two_qubit_ops=two_qubit_ops,
        t_ops=t_ops,
        measurement_ops=meas_ops,
        operation_counts=op_counts,
    )


def solve_minimum_code_distance(
    physical_error: float,
    threshold: float,
    spacetime_volume: int,
    allocated_error_budget: float,
    max_d: int = 51,
) -> int:
    """
    Find smallest odd integer d >= 3 satisfying:
        spacetime_volume * P_L(d, p) <= allocated_error_budget
    """
    if physical_error >= threshold:
        return max_d

    ratio = physical_error / threshold
    if ratio <= 0.0:
        return 3

    for d in range(3, max_d + 1, 2):
        exponent = (d + 1) / 2.0
        p_l = 0.1 * (ratio ** exponent)
        total_logical_error = spacetime_volume * p_l
        if total_logical_error <= allocated_error_budget:
            return d

    return max_d


def evaluate_fault_tolerant_cost(
    metrics: CircuitMetrics,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    num_magic_factories: int = 2,
    code_family: str = "surface_code_rotated",  # 'surface_code_rotated', 'qldpc'
    code_distance_override: Optional[int] = None,
    decoder_latency_ns: Optional[float] = None,
    weight_qubits: float = 1.0,
    weight_time: float = 500.0,
) -> CostEstimationResult:
    """
    Comprehensive fault-tolerant resource estimation.
    Models surface code / qLDPC data patches + magic state distillation + classical decoder latency.
    """
    diagnostics: List[str] = []
    num_logical = max(1, metrics.num_qubits)
    t_count = metrics.t_ops

    if t_count == 0 and metrics.single_qubit_ops > 0:
        rotations = sum(
            metrics.operation_counts.get(g, 0)
            for g in ["rz", "rx", "ry", "u", "p"]
        )
        t_count = rotations * 20

    p_phys = hardware.two_qubit_error * hardware.crosstalk_penalty
    p_th = hardware.surface_code_threshold

    if p_phys >= p_th:
        return CostEstimationResult(
            valid=False,
            physical_qubits=0,
            runtime_seconds=0.0,
            failure_probability=1.0,
            code_distance=0,
            factory_code_distance=0,
            num_factories=0,
            data_physical_qubits=0,
            factory_physical_qubits=0,
            total_surface_code_cycles=0,
            decoder_stall_factor=1.0,
            spacetime_volume=0,
            total_cost_score=float("inf"),
            assumptions={"hardware": hardware.name, "reason": "Physical error rate above threshold"},
            diagnostics=["Physical error rate exceeds threshold (p >= p_th)."],
        )

    data_error_budget = target_epsilon * 0.6
    magic_error_budget = target_epsilon * 0.4

    # Level-1 15-to-1 factory produces magic state with error ~ 35 * p_phys^3
    p_magic_distilled = 35.0 * (p_phys ** 3)
    total_magic_fail_prob = t_count * p_magic_distilled

    # If level-1 magic error is too high, model level-2 cascade
    distillation_level = 1
    if total_magic_fail_prob > magic_error_budget and t_count > 0:
        distillation_level = 2
        p_magic_distilled = (35.0 ** 4) * (p_phys ** 9)
        total_magic_fail_prob = t_count * p_magic_distilled
        diagnostics.append("Adopted Level-2 magic state cascade distillation to fulfill error budget.")

    d_factory = max(3, 7)
    factory_multiplier = 16 if distillation_level == 1 else 16 * 8
    physical_qubits_per_factory = factory_multiplier * 2 * (d_factory ** 2)
    distillation_cycles_per_t = d_factory * distillation_level

    clifford_cycles = max(1, metrics.depth)
    magic_cycles = math.ceil(t_count / max(1, num_magic_factories)) * distillation_cycles_per_t
    total_cycles = max(clifford_cycles, magic_cycles)

    data_spacetime_volume = num_logical * total_cycles

    if code_distance_override is not None:
        d_code = code_distance_override
        if d_code % 2 == 0:
            d_code += 1
    else:
        d_code = solve_minimum_code_distance(
            physical_error=p_phys,
            threshold=p_th,
            spacetime_volume=data_spacetime_volume,
            allocated_error_budget=data_error_budget,
        )

    # Physical qubit calculation based on code family
    if code_family == "qldpc" or hardware.technology == "qldpc":
        # Quantum LDPC constant-rate code (e.g. bivariate bicycle [n, k, d])
        # Overhead ~ 12x physical qubits per logical qubit vs 2*d^2 for surface code
        data_physical_qubits = int(num_logical * max(144 / 12, 2 * d_code * 1.5))
        diagnostics.append("Evaluated under high-rate Quantum LDPC bivariate bicycle architecture.")
    else:
        data_physical_qubits = num_logical * 2 * (d_code ** 2)

    factory_physical_qubits = num_magic_factories * physical_qubits_per_factory
    total_physical_qubits = data_physical_qubits + factory_physical_qubits

    # Logical failure probability
    p_l_cycle = 0.1 * ((p_phys / p_th) ** ((d_code + 1) / 2.0))
    p_data_fail = 1.0 - math.exp(-data_spacetime_volume * p_l_cycle)
    total_failure_probability = p_data_fail + total_magic_fail_prob

    # Classical decoding throughput
    dec_latency = decoder_latency_ns if decoder_latency_ns is not None else hardware.decoder_latency_ns_per_cycle
    cyc_time_ns = hardware.surface_code_cycle_time_ns

    effective_cycle_time_ns = max(cyc_time_ns, dec_latency)
    decoder_stall_factor = effective_cycle_time_ns / cyc_time_ns

    if decoder_stall_factor > 1.0:
        diagnostics.append(
            f"Decoder bottleneck: latency ({dec_latency}ns) > cycle time ({cyc_time_ns}ns), causing {decoder_stall_factor:.2f}x runtime slowdown."
        )

    total_runtime_seconds = (total_cycles * effective_cycle_time_ns) * 1e-9

    valid = True
    if total_physical_qubits > hardware.max_physical_qubits:
        valid = False
        diagnostics.append(
            f"Qubit limit exceeded: {total_physical_qubits} physical qubits > max {hardware.max_physical_qubits}."
        )

    if total_failure_probability > target_epsilon:
        valid = False
        diagnostics.append(
            f"Reliability budget exceeded: failure prob {total_failure_probability:.2e} > budget {target_epsilon:.2e}."
        )

    spacetime_volume = total_physical_qubits * total_cycles

    # Normalized scalar cost score balancing footprint and runtime (in ms)
    runtime_ms = total_runtime_seconds * 1e3
    total_cost_score = (weight_qubits * total_physical_qubits) + (weight_time * runtime_ms)

    return CostEstimationResult(
        valid=valid,
        physical_qubits=total_physical_qubits,
        runtime_seconds=total_runtime_seconds,
        failure_probability=total_failure_probability,
        code_distance=d_code,
        factory_code_distance=d_factory,
        num_factories=num_magic_factories,
        data_physical_qubits=data_physical_qubits,
        factory_physical_qubits=factory_physical_qubits,
        total_surface_code_cycles=total_cycles,
        decoder_stall_factor=decoder_stall_factor,
        spacetime_volume=spacetime_volume,
        total_cost_score=total_cost_score,
        assumptions={
            "hardware": hardware.name,
            "technology": hardware.technology,
            "code_family": code_family,
            "p_phys": p_phys,
            "target_epsilon": target_epsilon,
            "num_logical_qubits": num_logical,
            "t_count": t_count,
            "distillation_level": distillation_level,
        },
        diagnostics=diagnostics,
    )
