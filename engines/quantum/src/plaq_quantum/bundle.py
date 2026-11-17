"""Export a versioned job bundle (circuit + metrics + optional FT estimate).

FTQC technical plans call this a 'versioned job bundle with inputs, requested
accuracy, and success criteria'. Agents can attach it as an artifact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .cost_model import extract_circuit_metrics
from .hardware import get_hardware_profile
from .workloads import circuit_to_qasm, resolve_circuit

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


def _qasm3(circuit: QuantumCircuit) -> str:
    try:
        from qiskit.qasm3 import dumps

        return dumps(circuit)
    except Exception:
        return ""


@dataclass
class JobBundle:
    version: str
    created_at: str
    workload: Optional[str]
    num_qubits: int
    depth: int
    t_count: int
    qasm2: str
    qasm3: str
    hardware_profile: Optional[str] = None
    code_distance: Optional[int] = None
    physical_qubits: Optional[int] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def export_bundle(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    hardware_profile: Optional[str] = "superconducting",
    include_estimate: bool = True,
) -> JobBundle:
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to export a job bundle.")
    qc = circuit or resolve_circuit(workload=workload, qubits=qubits, qasm=qasm)
    metrics = extract_circuit_metrics(qc)
    q2 = circuit_to_qasm(qc)
    q3 = _qasm3(qc)
    d = phys = None
    notes = ["OpenQASM 3 is best-effort (Qiskit qasm3.dumps)."]
    if include_estimate:
        try:
            from .cost_model import evaluate_fault_tolerant_cost

            hw = get_hardware_profile(hardware_profile or "superconducting")
            cost = evaluate_fault_tolerant_cost(metrics=metrics, hardware=hw, target_epsilon=1e-3)
            d = int(cost.code_distance)
            phys = int(cost.physical_qubits)
        except Exception as exc:
            notes.append(f"FT estimate skipped: {exc}")
    return JobBundle(
        version="0.3.0",
        created_at=datetime.now(timezone.utc).isoformat(),
        workload=workload,
        num_qubits=int(metrics.num_qubits),
        depth=int(metrics.depth),
        t_count=int(metrics.t_ops),
        qasm2=q2 or "",
        qasm3=q3 or "",
        hardware_profile=hardware_profile,
        code_distance=d,
        physical_qubits=phys,
        notes=notes,
    )
