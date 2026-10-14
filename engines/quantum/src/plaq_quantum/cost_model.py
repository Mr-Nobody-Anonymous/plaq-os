"""
Plaq OS Fault-Tolerant Resource and Reliability Cost Model

Scientifically grounded analytical and architectural cost engine:
1. Circuit Metrics & Logical Gate Synthesis (Ross-Selinger / gridsynth scaling)
2. Critical-path T-depth and Clifford depth scheduling
3. Composite hardware physical error modeling (p_1q, p_2q, p_meas, crosstalk)
4. Calibrated rotated surface code distance solver with explicit feasibility verification
5. High-rate Quantum LDPC (qLDPC) bivariate bicycle code projections
6. 15-to-1 Bravyi-Kitaev magic-state distillation factory and multi-level cascade throughput
7. Classical decoder throughput vs streaming latency modeling
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

try:
    from .hardware import HardwareModel, DEMO_HARDWARE
except (ImportError, ValueError):
    try:
        from plaq_quantum.hardware import HardwareModel, DEMO_HARDWARE
    except ImportError:
        from hardware import HardwareModel, DEMO_HARDWARE

try:
    from qiskit import QuantumCircuit
    HAS_QISKIT = True
except ImportError:
    HAS_QISKIT = False


@dataclass(frozen=True)
class CircuitMetrics:
    """Quantitative structural and fault-tolerant profile of a quantum circuit."""
    num_qubits: int
    depth: int
    total_ops: int
    single_qubit_ops: int
    two_qubit_ops: int
    t_ops: int
    t_depth: int
    measurement_ops: int
    operation_counts: Dict[str, int]
    synthesis_t_count: int

    def __getitem__(self, key: str) -> Any:
        mapping = {
            "t_count": self.synthesis_t_count if self.synthesis_t_count else self.t_ops,
            "clifford_depth": max(0, self.depth - self.t_depth),
            "num_qubits": self.num_qubits,
            "depth": self.depth,
            "total_ops": self.total_ops,
            "single_qubit_ops": self.single_qubit_ops,
            "two_qubit_ops": self.two_qubit_ops,
            "t_ops": self.t_ops,
            "t_depth": self.t_depth,
            "measurement_ops": self.measurement_ops,
        }
        if key in mapping:
            return mapping[key]
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        keys = {
            "t_count", "clifford_depth", "num_qubits", "depth", "total_ops",
            "single_qubit_ops", "two_qubit_ops", "t_ops", "t_depth",
            "measurement_ops", "operation_counts", "synthesis_t_count",
        }
        return key in keys or hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


@dataclass(frozen=True)
class CostEstimationResult:
    """Rigorous fault-tolerant execution cost report with explicit feasibility."""
    valid: bool
    feasibility_reason: str
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
            "feasibility_reason": self.feasibility_reason,
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


def synthesize_rotation_t_count(angle: float, target_synthesis_error: float = 1e-4) -> int:
    """
    Estimate non-Clifford T-count for an arbitrary single-qubit rotation R_z(theta)
    based on Ross-Selinger / gridsynth optimal Clifford+T synthesis:
        N_T ~ 3 * log2(1 / epsilon_syn) + O(1)
    Clifford angles (multiples of pi/2) require 0 T-gates.
    T angles (multiples of pi/4) require 1 T-gate.
    """
    # Normalize angle into [0, 2pi)
    twopi = 2 * math.pi
    norm_angle = angle % twopi
    if norm_angle < 0:
        norm_angle += twopi

    # Check for exact Clifford angles (I, Z, S, Sdg)
    for k in range(5):
        if abs(norm_angle - k * (math.pi / 2.0)) < 1e-6:
            return 0

    # Check for exact T gates (T, Tdg, etc.)
    for k in range(9):
        if abs(norm_angle - k * (math.pi / 4.0)) < 1e-6:
            return 1

    # Arbitrary angle requires optimal precision synthesis
    eps = max(1e-12, target_synthesis_error)
    # Proven asymptotic scaling: ~ 3.21 * log2(1 / eps) + 2.5
    t_synth = int(math.ceil(3.21 * math.log2(1.0 / eps) + 2.5))
    return max(1, t_synth)


def extract_circuit_metrics(
    circuit: Any,
    target_synthesis_error: float = 1e-4,
) -> CircuitMetrics:
    """
    Extract operation counts, critical-path T-depth, and synthesized non-Clifford T-gates.
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
    rotation_gates = {"rz", "rx", "ry", "u", "p", "u1", "u2", "u3"}

    explicit_t_ops = sum(count for gate, count in op_counts.items() if gate in t_gates)
    two_qubit_ops = sum(count for gate, count in op_counts.items() if gate in two_qubit_gates)
    meas_ops = sum(count for gate, count in op_counts.items() if gate in measurement_gates)

    single_qubit_ops = sum(
        count for gate, count in op_counts.items()
        if gate not in two_qubit_gates and gate not in measurement_gates and gate != "barrier"
    )

    # Calculate synthesis-based non-Clifford count for arbitrary rotations
    synthesized_t_ops = 0
    t_qubit_last_layer: Dict[int, int] = {q: 0 for q in range(num_qubits)}
    t_critical_depth = 0

    for instruction in circuit.data:
        op = instruction.operation
        name = op.name.lower()
        q_indices = [circuit.find_bit(q).index for q in instruction.qubits]

        req_t = 0
        if name in t_gates:
            req_t = 1
        elif name in rotation_gates and len(op.params) > 0:
            angle = float(op.params[0]) if isinstance(op.params[0], (int, float)) else math.pi / 8.0
            req_t = synthesize_rotation_t_count(angle, target_synthesis_error)

        if req_t > 0:
            synthesized_t_ops += req_t
            start_l = max(t_qubit_last_layer[q] for q in q_indices)
            end_l = start_l + req_t
            for q in q_indices:
                t_qubit_last_layer[q] = end_l
            if end_l > t_critical_depth:
                t_critical_depth = end_l
        elif name in two_qubit_gates:
            start_l = max(t_qubit_last_layer[q] for q in q_indices)
            for q in q_indices:
                t_qubit_last_layer[q] = start_l

    total_t_ops = explicit_t_ops + synthesized_t_ops
    t_depth = max(explicit_t_ops, t_critical_depth) if t_critical_depth > 0 else explicit_t_ops

    return CircuitMetrics(
        num_qubits=num_qubits,
        depth=depth,
        total_ops=total_ops,
        single_qubit_ops=single_qubit_ops,
        two_qubit_ops=two_qubit_ops,
        t_ops=total_t_ops,
        t_depth=t_depth,
        measurement_ops=meas_ops,
        operation_counts=op_counts,
        synthesis_t_count=synthesized_t_ops,
    )


class CodeDistanceResult(int):
    """
    Dual-type result: behaves directly as an integer code distance (supporting comparison,
    modulo, and int operations) while also supporting tuple unpacking (code_distance, is_feasible, reason)
    for backward compatibility with existing tests.
    """
    feasible: bool = True
    reason: str = "Feasible"

    def __new__(cls, val: int, feasible: bool = True, reason: str = "Feasible"):
        obj = super().__new__(cls, val)
        obj.feasible = feasible
        obj.reason = reason
        return obj

    def __iter__(self):
        return iter((int(self), self.feasible, self.reason))

    def __getitem__(self, idx: int):
        return (int(self), self.feasible, self.reason)[idx]

    @property
    def code_distance(self) -> int:
        return int(self)

    @property
    def feasibility_reason(self) -> str:
        return self.reason


def solve_minimum_code_distance(
    physical_error: float = 0.001,
    threshold: float = 0.01,
    spacetime_volume: int = 1000,
    allocated_error_budget: float = 1e-3,
    max_d: int = 51,
    physical_error_rate: Optional[float] = None,
    target_logical_error: Optional[float] = None,
    circuit_depth: Optional[int] = None,
    **kwargs: Any,
) -> CodeDistanceResult:
    """
    Find smallest odd integer d >= 3 satisfying:
        spacetime_volume * P_L(d, p) <= allocated_error_budget
    Returns CodeDistanceResult (acts as int and unpacks as (distance, is_feasible, reason)).
    """
    if physical_error_rate is not None:
        physical_error = physical_error_rate
    if target_logical_error is not None:
        allocated_error_budget = target_logical_error
    if circuit_depth is not None:
        spacetime_volume = max(1000, circuit_depth * 10)

    if physical_error >= threshold:
        return CodeDistanceResult(max_d, False, f"Physical error rate ({physical_error:.3e}) >= threshold ({threshold:.3e}). Error suppression impossible.")

    ratio = physical_error / threshold
    if ratio <= 0.0:
        return CodeDistanceResult(3, True, "Physical error is zero; minimal code distance d=3 sufficient.")

    for d in range(3, max_d + 1, 2):
        exponent = (d + 1) / 2.0
        # Calibrated rotated planar surface code ansatz (Fowler 2012, Gidney 2021)
        p_l = 0.03 * (ratio ** exponent)
        total_logical_error = spacetime_volume * p_l
        if total_logical_error <= allocated_error_budget:
            return CodeDistanceResult(d, True, f"Satisfied reliability budget at code distance d={d}.")

    return CodeDistanceResult(max_d, False, f"Error budget ({allocated_error_budget:.2e}) unachievable within maximum allowed code distance d={max_d}.")


def evaluate_fault_tolerant_cost(
    metrics: CircuitMetrics,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    num_magic_factories: int = 2,
    code_family: str = "surface_code_rotated",
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
    t_depth = max(1, metrics.t_depth) if t_count > 0 else 0

    # Composite physical error rate integrating 2Q, 1Q, measurement, and spectator crosstalk
    p_comp = (hardware.two_qubit_error + 0.5 * hardware.single_qubit_error + 0.25 * hardware.measurement_error) * hardware.crosstalk_penalty
    p_phys = p_comp
    p_th = hardware.surface_code_threshold

    if p_phys >= p_th:
        return CostEstimationResult(
            valid=False,
            feasibility_reason=f"Composite physical error rate ({p_phys:.3e}) exceeds fault-tolerance threshold ({p_th:.3e}).",
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
            diagnostics=["Composite physical error rate exceeds surface code threshold (p >= p_th)."],
        )

    # Error budget split: 60% data preservation, 40% magic state distillation
    data_error_budget = target_epsilon * 0.6
    magic_error_budget = target_epsilon * 0.4

    # 15-to-1 Bravyi-Kitaev magic state distillation cascade model
    # Level-1: P_out ~ 35 * p_phys^3
    p_magic_distilled = 35.0 * (p_phys ** 3)
    total_magic_fail_prob = t_count * p_magic_distilled

    distillation_level = 1
    if total_magic_fail_prob > magic_error_budget and t_count > 0:
        # Level-2 cascade: P_out ~ 35 * (35 * p_phys^3)^3
        distillation_level = 2
        p_magic_distilled = (35.0 ** 4) * (p_phys ** 9)
        total_magic_fail_prob = t_count * p_magic_distilled
        diagnostics.append("Adopted Level-2 magic state cascade distillation to fulfill error budget.")

    d_factory = max(3, 7)
    factory_multiplier = 16 if distillation_level == 1 else 16 * 8
    physical_qubits_per_factory = factory_multiplier * 2 * (d_factory ** 2)
    distillation_cycles_per_t = d_factory * distillation_level

    clifford_cycles = max(1, metrics.depth)
    magic_production_cycles = math.ceil(t_count / max(1, num_magic_factories)) * distillation_cycles_per_t
    total_cycles = max(clifford_cycles, magic_production_cycles)

    data_spacetime_volume = num_logical * total_cycles

    if code_distance_override is not None:
        d_code = code_distance_override if code_distance_override % 2 != 0 else code_distance_override + 1
        d_feasible = True
        feasibility_reason = f"Code distance manually set to d={d_code}."
    else:
        d_code, d_feasible, feasibility_reason = solve_minimum_code_distance(
            physical_error=p_phys,
            threshold=p_th,
            spacetime_volume=data_spacetime_volume,
            allocated_error_budget=data_error_budget,
        )

    # Physical qubit calculation based on code family
    if code_family == "qldpc" or hardware.technology == "qldpc":
        # Quantum LDPC bivariate bicycle code [[144, 12, 12]] (Bravyi et al. 2024 Nature)
        # Yields 12 physical qubits per logical qubit vs 2*d^2 for surface code
        data_physical_qubits = int(num_logical * max(144 / 12, 2 * d_code * 1.5))
        diagnostics.append("Evaluated under high-rate Quantum LDPC bivariate bicycle architecture [[144, 12, 12]].")
    else:
        data_physical_qubits = num_logical * 2 * (d_code ** 2)

    factory_physical_qubits = num_magic_factories * physical_qubits_per_factory
    total_physical_qubits = data_physical_qubits + factory_physical_qubits

    # Logical failure probability (analytical Poisson model)
    p_l_cycle = 0.03 * ((p_phys / p_th) ** ((d_code + 1) / 2.0))
    p_data_fail = 1.0 - math.exp(-data_spacetime_volume * p_l_cycle)
    total_failure_probability = p_data_fail + total_magic_fail_prob

    # Classical decoding throughput & feedback latency
    dec_latency = decoder_latency_ns if decoder_latency_ns is not None else hardware.decoder_latency_ns_per_cycle
    cyc_time_ns = hardware.surface_code_cycle_time_ns

    effective_cycle_time_ns = max(cyc_time_ns, dec_latency)
    decoder_stall_factor = effective_cycle_time_ns / cyc_time_ns

    if decoder_stall_factor > 1.0:
        diagnostics.append(
            f"Decoder stall: latency ({dec_latency}ns) > cycle ({cyc_time_ns}ns), causing {decoder_stall_factor:.2f}x runtime slowdown."
        )

    total_runtime_seconds = (total_cycles * effective_cycle_time_ns) * 1e-9

    valid = d_feasible
    if not d_feasible:
        diagnostics.append(feasibility_reason)

    if total_physical_qubits > hardware.max_physical_qubits:
        valid = False
        feasibility_reason = f"Qubit limit exceeded: {total_physical_qubits} physical qubits > hardware max {hardware.max_physical_qubits}."
        diagnostics.append(feasibility_reason)

    if total_failure_probability > target_epsilon:
        valid = False
        feasibility_reason = f"Reliability budget exceeded: failure prob {total_failure_probability:.2e} > budget {target_epsilon:.2e}."
        diagnostics.append(feasibility_reason)

    spacetime_volume = total_physical_qubits * total_cycles

    # Normalized scalar cost score balancing footprint and runtime (in ms)
    runtime_ms = total_runtime_seconds * 1e3
    total_cost_score = (weight_qubits * total_physical_qubits) + (weight_time * runtime_ms)

    return CostEstimationResult(
        valid=valid,
        feasibility_reason=feasibility_reason,
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
            "p_phys_composite": p_phys,
            "target_epsilon": target_epsilon,
            "num_logical_qubits": num_logical,
            "t_count": t_count,
            "t_depth": t_depth,
            "distillation_level": distillation_level,
            "weight_qubits": weight_qubits,
            "weight_time": weight_time,
        },
        diagnostics=diagnostics,
    )
