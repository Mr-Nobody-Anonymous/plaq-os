"""Pauli-frame tracking for a logical circuit (FTQC compiler artefact).

MLIR FTQC dialects (2026) defer physical Pauli corrections to a classical
frame and apply one correction at the end. This module counts the frame
updates a Stim/lattice-surgery runtime would have to keep — it does not
simulate a decoder.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


@dataclass
class PauliFrameReport:
    logical_qubits: int
    two_qubit_gates: int
    measurements: int
    frame_updates: int
    deferred_corrections: int
    cycles_if_d: Dict[str, int]
    model: str = "deferred_pauli_frame_v1"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def track_pauli_frame(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    code_distance: int = 3,
) -> PauliFrameReport:
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for Pauli-frame tracking.")
    qc = circuit or resolve_circuit(workload=workload, qubits=qubits, qasm=qasm)
    twoq = meas = 0
    for inst in qc.data:
        name = getattr(inst.operation, "name", "")
        nq = getattr(inst.operation, "num_qubits", len(inst.qubits))
        if name == "measure":
            meas += 1
        elif int(nq) >= 2:
            twoq += 1
    # Each CX / CZ conjugates the frame of both qubits; each measure snapshots it.
    updates = twoq * 2 + meas
    deferred = qc.num_qubits  # one final correction per logical
    d = max(3, int(code_distance))
    if d % 2 == 0:
        d += 1
    notes = [
        "Corrections are deferred (ftqc.pauli_frame_update analogue), not applied in-circuit.",
        "cycles_if_d assumes one syndrome round per two-qubit gate times d.",
    ]
    return PauliFrameReport(
        logical_qubits=qc.num_qubits,
        two_qubit_gates=twoq,
        measurements=meas,
        frame_updates=updates,
        deferred_corrections=deferred,
        cycles_if_d={f"d{d}": twoq * d, f"d{d+2}": twoq * (d + 2)},
        notes=notes,
    )
