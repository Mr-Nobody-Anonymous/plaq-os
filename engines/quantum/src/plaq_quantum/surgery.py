"""Lattice-surgery resource planner (model-based, not a Stim layout).

Inspired by Classiq's 2026 Fault Tolerance Engine and Litinski's
*A Game of Surface Codes*: map a logical Clifford+T circuit onto rotated
surface-code *patches*, schedule CNOT as merge/split, and size 15-to-1
T factories.

This does **not** emit a 3-D spacetime layout or run lattice-surgery Stim
circuits. Numbers are schedule-derived estimates so agents can ask
"how many physical qubits does this algorithm need at distance d?"
before a full FT compiler exists.

References:
- Fowler et al., surface-code lattice surgery
- Litinski, A Game of Surface Codes (Quantum 2019)
- Bravyi–Kitaev 15-to-1 distillation
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .cost_model import extract_circuit_metrics
from .hardware import get_hardware_profile
from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


@dataclass
class SurgeryPlan:
    logical_qubits: int
    t_count: int
    cx_count: int
    depth: int
    code_distance: int
    data_patches: int
    routing_patches: int
    factory_count: int
    distillation_level: int
    physical_qubits_data: int
    physical_qubits_routing: int
    physical_qubits_factories: int
    physical_qubits_total: int
    merge_split_ops: int
    code_cycles: int
    cycle_time_ns: float
    runtime_seconds: float
    spacetime_qubit_cycles: int
    decoder_backlog_safe: bool
    hardware: str
    model: str = "rotated_surface_code_lattice_surgery_v1"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _odd_distance(d: int) -> int:
    d = max(3, int(d))
    if d % 2 == 0:
        d += 1
    return d


def plan_lattice_surgery(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    code_distance: Optional[int] = None,
    hardware_profile: str = "superconducting",
    factory_count: Optional[int] = None,
) -> SurgeryPlan:
    """Estimate patch / factory / cycle counts for a logical circuit."""
    if circuit is None:
        if not HAS_QISKIT:
            raise RuntimeError("Qiskit is required for surgery planning.")
        circuit = resolve_circuit(workload=workload, qubits=qubits, qasm=qasm)
    metrics = extract_circuit_metrics(circuit)
    hw = get_hardware_profile(hardware_profile)
    d = _odd_distance(code_distance or 3)
    n_log = int(metrics.num_qubits)
    t_count = int(metrics.t_ops + metrics.synthesis_t_count)
    cx_count = int(metrics.two_qubit_ops)
    # Rotated surface-code patch ≈ 2 d^2 physical qubits (data + ancilla).
    patch = 2 * d * d
    data_patches = n_log
    # A 1-D surgery bus of ~n routing patches (Litinski-style fast block, compressed).
    routing_patches = max(1, n_log)
    # 15-to-1 factory: ~16 patches at d_factory≈max(d,7) per Litinski table (level-1).
    distillation_level = 1 if t_count < 10_000 else 2
    d_factory = _odd_distance(max(d, 7))
    patches_per_factory = 16 if distillation_level == 1 else 16 * 8
    n_fact = int(factory_count) if factory_count else max(1, min(8, math.ceil(t_count / 64) or 1))
    phys_data = data_patches * patch
    phys_route = routing_patches * patch
    phys_fact = n_fact * patches_per_factory * 2 * d_factory * d_factory
    phys_total = phys_data + phys_route + phys_fact
    # Each logical CX → one merge (~d cycles) + split (~d cycles).
    merge_split = cx_count
    surgery_cycles = cx_count * 2 * d
    # T gates serialized through factories: ~d_factory cycles each / parallelism.
    t_cycles = math.ceil(t_count / max(1, n_fact)) * d_factory * distillation_level
    code_cycles = int(max(surgery_cycles, t_cycles, d * max(1, metrics.depth)))
    cycle_ns = float(getattr(hw, "surface_code_cycle_time_ns", 0) or 1000.0)
    runtime_s = code_cycles * cycle_ns * 1e-9
    decoder_ok = True
    decoder_ns = float(getattr(hw, "decoder_latency_ns_per_cycle", 0) or 0)
    if decoder_ns > 0 and cycle_ns > 0:
        decoder_ok = decoder_ns <= cycle_ns * 1.05
    notes = [
        "Model-based lattice surgery (not a Stim 3-D layout or Classiq visualizer).",
        "CNOT = merge+split of d-distance patches; T via 15-to-1 Bravyi–Kitaev factories.",
        "Routing bus is a 1-D compressed block, not a full 2-D street network.",
    ]
    if phys_total > getattr(hw, "max_physical_qubits", 10**12):
        notes.append(
            f"Footprint {phys_total} exceeds hardware max {hw.max_physical_qubits}."
        )
    return SurgeryPlan(
        logical_qubits=n_log,
        t_count=t_count,
        cx_count=cx_count,
        depth=int(metrics.depth),
        code_distance=d,
        data_patches=data_patches,
        routing_patches=routing_patches,
        factory_count=n_fact,
        distillation_level=distillation_level,
        physical_qubits_data=phys_data,
        physical_qubits_routing=phys_route,
        physical_qubits_factories=phys_fact,
        physical_qubits_total=phys_total,
        merge_split_ops=merge_split,
        code_cycles=code_cycles,
        cycle_time_ns=cycle_ns,
        runtime_seconds=runtime_s,
        spacetime_qubit_cycles=phys_total * code_cycles,
        decoder_backlog_safe=decoder_ok,
        hardware=hw.name,
        notes=notes,
    )
