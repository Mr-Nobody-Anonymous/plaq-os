"""ASCII / Mermaid circuit diagrams for the workbench and agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


@dataclass
class CircuitDrawing:
    num_qubits: int
    depth: int
    ascii: str
    mermaid: str
    gate_counts: Dict[str, int]
    workload: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _gate_counts(circuit: QuantumCircuit) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    skip = {"barrier", "delay"}
    for inst in circuit.data:
        name = getattr(inst.operation, "name", "op")
        if name in skip:
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def _mermaid(circuit: QuantumCircuit, limit: int = 48) -> str:
    lines = ["flowchart LR"]
    n = circuit.num_qubits
    for q in range(n):
        lines.append(f"  q{q}((q{q}))")
    shown = 0
    prev = {q: f"q{q}" for q in range(n)}
    for idx, inst in enumerate(circuit.data):
        name = getattr(inst.operation, "name", "op")
        if name in {"barrier", "delay"}:
            continue
        qidx = [circuit.find_bit(q).index for q in inst.qubits]
        node = f"{name}_{idx}"
        label = name.upper()
        if shown >= limit:
            lines.append(f"  more[… {len(circuit.data) - idx} more gates]")
            break
        if len(qidx) == 1:
            q = qidx[0]
            lines.append(f"  {prev[q]} --> {node}[{label}]")
            prev[q] = node
        elif len(qidx) >= 2:
            a, b = qidx[0], qidx[1]
            lines.append(f"  {prev[a]} --> {node}[{label}]")
            lines.append(f"  {prev[b]} --> {node}")
            prev[a] = node
            prev[b] = node
        shown += 1
    return "\n".join(lines)


def draw_circuit(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    bitstring: Optional[str] = None,
) -> CircuitDrawing:
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to draw circuits.")
    qc = circuit or resolve_circuit(
        workload=workload, qubits=qubits, qasm=qasm, bitstring=bitstring
    )
    try:
        ascii_art = str(qc.draw(output="text"))
    except Exception:
        ascii_art = f"QuantumCircuit({qc.num_qubits} qubits, depth={qc.depth()})"
    return CircuitDrawing(
        num_qubits=qc.num_qubits,
        depth=int(qc.depth()),
        ascii=ascii_art,
        mermaid=_mermaid(qc),
        gate_counts=_gate_counts(qc),
        workload=workload,
    )
