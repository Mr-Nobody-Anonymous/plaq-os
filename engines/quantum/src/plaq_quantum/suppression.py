"""Error *suppression* (before mitigation): dynamical decoupling + Pauli twirling.

IBM Sampler/Estimator options (2025+):
- dynamical_decoupling.sequence_type = XpXm
- twirling.enable_gates = True

Implemented here as circuit rewrites + averaged observables so ``--lite``
installs do not need qiskit-ibm-runtime or pulse-level hardware.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .noise import NoiseModel, noisy_distribution, total_variation
from .primitives import run_estimator
from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit
    from qiskit.circuit import Delay

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


def insert_dynamical_decoupling(circuit: QuantumCircuit, sequence: str = "XpXm") -> QuantumCircuit:
    """Insert an X–X (XpXm) pair on idle qubits after each two-qubit gate.

    Pulse-level DD needs a real dt; this is a *gate-level* analogue used in
    software studies when the backend has no pulse access.
    """
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for dynamical decoupling.")
    seq = (sequence or "XpXm").lower()
    out = QuantumCircuit(*circuit.qregs, *circuit.cregs, name=f"{circuit.name}_dd")
    skip = {"measure", "barrier", "reset", "delay"}
    for inst in circuit.data:
        out.append(inst.operation, inst.qubits, inst.clbits)
        name = getattr(inst.operation, "name", "")
        nq = getattr(inst.operation, "num_qubits", len(inst.qubits))
        if name in skip or int(nq) < 2:
            continue
        busy = {circuit.find_bit(q).index for q in inst.qubits}
        for i in range(circuit.num_qubits):
            if i in busy:
                continue
            if seq in {"xpxm", "xy4", "xx"}:
                out.x(i)
                out.x(i)
            else:
                try:
                    out.append(Delay(1), [out.qubits[i]])
                except Exception:
                    pass
    return out


_TWIRL = (
    ("i", "i"),
    ("x", "x"),
    ("z", "z"),
    ("y", "y"),
)


def _apply_pauli(qc: QuantumCircuit, q: int, kind: str) -> None:
    if kind == "x":
        qc.x(q)
    elif kind == "z":
        qc.z(q)
    elif kind == "y":
        qc.y(q)


def twirl_cnots(circuit: QuantumCircuit, which: int = 0) -> QuantumCircuit:
    """Conjugate every CX by a Pauli pair from the CX-twirl subgroup."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for Pauli twirling.")
    a, b = _TWIRL[int(which) % len(_TWIRL)]
    out = QuantumCircuit(*circuit.qregs, *circuit.cregs, name=f"{circuit.name}_twirl{which}")
    for inst in circuit.data:
        name = getattr(inst.operation, "name", "")
        qidx = [circuit.find_bit(q).index for q in inst.qubits]
        if name in {"cx", "cnot"} and len(qidx) == 2:
            _apply_pauli(out, qidx[0], a)
            _apply_pauli(out, qidx[1], b)
            out.append(inst.operation, inst.qubits, inst.clbits)
            _apply_pauli(out, qidx[0], a)
            _apply_pauli(out, qidx[1], b)
        else:
            out.append(inst.operation, inst.qubits, inst.clbits)
    return out


@dataclass
class SuppressionResult:
    sequence: str
    twirl_randomizations: int
    original_depth: int
    dd_depth: int
    dd_extra_x: int
    ideal_expectation: float
    noisy_expectation: float
    suppressed_expectation: float
    noisy_tvd: float
    suppressed_tvd: float
    improved: bool
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_suppression(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    sequence: str = "XpXm",
    twirl_randomizations: int = 4,
    p1: float = 0.001,
    p2: float = 0.02,
    p_readout: float = 0.0,
    observable: str = "ZZ",
) -> SuppressionResult:
    """Compare ideal vs noisy vs DD+twirl under the phenomenological noise model."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for suppression.")
    qc = circuit or resolve_circuit(workload=workload, qubits=qubits, qasm=qasm)
    dd = insert_dynamical_decoupling(qc, sequence=sequence)
    extra_x = sum(1 for inst in dd.data if getattr(inst.operation, "name", "") == "x") - sum(
        1 for inst in qc.data if getattr(inst.operation, "name", "") == "x"
    )
    model = NoiseModel(p1=p1, p2=p2, p_readout=p_readout)
    n = qc.num_qubits
    obs = observable if len(observable or "") == n else (observable or "Z")
    ideal = run_estimator(qc, observable=obs).expectation
    _i, noisy_p, *_r = noisy_distribution(qc, model)
    _i2, dd_p, *_r2 = noisy_distribution(dd, model)
    # Twirl: average noisy distributions of conjugated circuits
    if twirl_randomizations > 0:
        acc = None
        for k in range(int(twirl_randomizations)):
            tw = twirl_cnots(dd, which=k)
            _it, tp, *_rt = noisy_distribution(tw, model)
            if acc is None:
                acc = {key: float(val) for key, val in tp.items()}
            else:
                for key, val in tp.items():
                    acc[key] = acc.get(key, 0.0) + float(val)
        twirled = {k: v / float(twirl_randomizations) for k, v in (acc or {}).items()}
    else:
        twirled = dd_p

    def _ev(probs: Dict[str, float], label: str) -> float:
        lab = (label or "Z" * n).upper()
        if len(lab) == 1:
            lab = ("I" * (n - 1)) + lab
        if len(lab) != n:
            lab = (lab + ("I" * n))[:n]
        acc = 0.0
        for bitstr, pr in probs.items():
            if len(bitstr) != n:
                continue
            val = 1.0
            for q, ch in enumerate(reversed(lab)):
                bit = bitstr[n - 1 - q]
                if ch == "Z" and bit == "1":
                    val *= -1.0
                elif ch in {"X", "Y"}:
                    val = 0.0
                    break
            acc += float(pr) * val
        return float(acc)

    noisy_ev = _ev(noisy_p, obs)
    supp_ev = _ev(twirled, obs)
    tvd_n = total_variation(_i, noisy_p)
    tvd_s = total_variation(_i2, twirled)
    err_n = abs(noisy_ev - ideal)
    err_s = abs(supp_ev - ideal)
    notes = [
        "Gate-level XpXm analogue (not pulse DD). Twirl subgroup {(I,I),(X,X),(Z,Z),(Y,Y)}.",
        "Improvement is on the scalar observable, not a guarantee for every circuit.",
    ]
    return SuppressionResult(
        sequence=sequence,
        twirl_randomizations=int(twirl_randomizations),
        original_depth=int(qc.depth()),
        dd_depth=int(dd.depth()),
        dd_extra_x=int(max(0, extra_x)),
        ideal_expectation=float(ideal),
        noisy_expectation=float(noisy_ev),
        suppressed_expectation=float(supp_ev),
        noisy_tvd=float(tvd_n),
        suppressed_tvd=float(tvd_s),
        improved=err_s <= err_n + 1e-12,
        notes=notes,
    )
