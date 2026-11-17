"""NISQ error mitigation without Mitiq.

Implements two workhorses used by IBM Runtime resilience levels:

1. **Readout inversion** — invert an independent bit-flip assignment matrix.
2. **Zero-noise extrapolation (ZNE)** — scale depolarizing strengths
   (unitary-folding analogue) and Richardson/linear-extrapolate to λ=0.

Temme, Bravyi, Gambetta, *Error mitigation for short-depth quantum circuits*
(PRL 2017). Honest limit: ZNE estimates *expectation values*, not full
states, and can overshoot when noise is not linear.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .noise import (
    NoiseModel,
    noisy_distribution,
    total_variation,
)
from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


def _bit_index(bitstr: str) -> int:
    return int(bitstr, 2)


def readout_assignment_matrix(n: int, p_readout: float) -> np.ndarray:
    """Kronecker product of 2×2 bit-flip matrices (qubit 0 = least significant)."""
    p = float(min(1.0, max(0.0, p_readout)))
    bit = np.array([[1.0 - p, p], [p, 1.0 - p]], dtype=float)
    mat = np.array([[1.0]], dtype=float)
    for _ in range(n):
        mat = np.kron(bit, mat)
    return mat


def invert_readout(probs: Dict[str, float], n: int, p_readout: float) -> Dict[str, float]:
    """Apply A^{-1} to the probability vector and clip/renormalize."""
    dim = 1 << n
    vec = np.zeros(dim, dtype=float)
    for k, v in probs.items():
        if len(k) != n:
            continue
        vec[_bit_index(k)] = float(v)
    a = readout_assignment_matrix(n, p_readout)
    try:
        inv = np.linalg.inv(a)
    except np.linalg.LinAlgError:
        inv = np.linalg.pinv(a)
    rec = inv @ vec
    rec = np.clip(rec, 0.0, None)
    s = float(rec.sum()) or 1.0
    rec = rec / s
    return {format(i, f"0{n}b"): float(rec[i]) for i in range(dim) if rec[i] > 1e-15}


def _observable(probs: Dict[str, float], kind: str, n: int) -> float:
    """Scalar figure of merit for ZNE."""
    kind = (kind or "success").lower()
    if kind in {"success", "even_parity", "bell"}:
        # P(even parity) — Bell |Φ+⟩ lives here; GHZ too for even n of 1s...
        acc = 0.0
        for k, v in probs.items():
            if k.count("1") % 2 == 0:
                acc += float(v)
        return float(acc)
    if kind in {"allzero", "zero"}:
        key = "0" * n
        return float(probs.get(key, 0.0))
    if kind in {"allone", "one"}:
        key = "1" * n
        return float(probs.get(key, 0.0))
    if kind in {"z0", " mag"}:
        # ⟨Z on qubit 0⟩ (rightmost bit)
        acc = 0.0
        for k, v in probs.items():
            acc += float(v) * (1.0 if k[-1] == "0" else -1.0)
        return float(acc)
    # default: max probability (purity proxy)
    return float(max(probs.values()) if probs else 0.0)


def linear_extrapolate(scales: Sequence[float], values: Sequence[float]) -> float:
    """Least-squares fit value(λ) = a + b λ, return a = value(0)."""
    x = np.array(list(scales), dtype=float)
    y = np.array(list(values), dtype=float)
    if len(x) < 2:
        return float(y[-1]) if len(y) else 0.0
    _slope, intercept = np.polyfit(x, y, 1)
    return float(intercept)


def richardson_two_point(s1: float, e1: float, s2: float, e2: float) -> float:
    """(s2 E(s1) - s1 E(s2)) / (s2 - s1) — classic Richardson to λ=0."""
    if abs(s2 - s1) < 1e-12:
        return float(e1)
    return float((s2 * e1 - s1 * e2) / (s2 - s1))


@dataclass
class MitigationResult:
    num_qubits: int
    observable: str
    ideal_value: float
    unmitigated_value: float
    readout_mitigated_value: Optional[float]
    zne_value: float
    richardson_value: float
    scale_factors: List[float]
    scale_values: List[float]
    unmitigated_tvd: float
    readout_tvd: Optional[float]
    improved: bool
    method: str = "readout+zne"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_mitigation(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    bitstring: Optional[str] = None,
    p1: float = 0.001,
    p2: float = 0.01,
    p_readout: float = 0.02,
    scale_factors: Optional[Sequence[float]] = None,
    observable: str = "success",
) -> MitigationResult:
    """Compare ideal / noisy / readout-inverted / ZNE estimates of one observable."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for error mitigation.")
    qc = circuit or resolve_circuit(workload=workload, qubits=qubits, qasm=qasm, bitstring=bitstring)
    n = qc.num_qubits
    model = NoiseModel(p1=p1, p2=p2, p_readout=p_readout)
    scales = list(scale_factors or (1.0, 3.0, 5.0))
    ideal, noisy_l1, *_rest = noisy_distribution(qc, model, scale=1.0)
    ideal_val = _observable(ideal, observable, n)
    raw_val = _observable(noisy_l1, observable, n)
    inverted = invert_readout(noisy_l1, n, p_readout)
    inv_val = _observable(inverted, observable, n)
    values: List[float] = []
    for s in scales:
        _ideal, noisy, *_r = noisy_distribution(qc, model, scale=float(s))
        values.append(_observable(noisy, observable, n))
    zne = linear_extrapolate(scales, values)
    rich = richardson_two_point(scales[0], values[0], scales[min(1, len(scales) - 1)], values[min(1, len(values) - 1)])
    tvd_raw = total_variation(ideal, noisy_l1)
    tvd_inv = total_variation(ideal, inverted)
    err_raw = abs(raw_val - ideal_val)
    err_mit = abs(zne - ideal_val)
    notes = [
        "ZNE scales the depolarizing probabilities (folding analogue); readout is not scaled.",
        "Observable is a scalar; the full noisy state is not recovered.",
    ]
    if err_mit > err_raw:
        notes.append("ZNE did not improve this observable (noise may be too strong or non-linear).")
    return MitigationResult(
        num_qubits=n,
        observable=observable,
        ideal_value=ideal_val,
        unmitigated_value=raw_val,
        readout_mitigated_value=inv_val,
        zne_value=zne,
        richardson_value=rich,
        scale_factors=[float(s) for s in scales],
        scale_values=values,
        unmitigated_tvd=tvd_raw,
        readout_tvd=tvd_inv,
        improved=(err_mit <= err_raw + 1e-12) or (tvd_inv <= tvd_raw + 1e-12),
        notes=notes,
    )
