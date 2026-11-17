"""Phenomenological NISQ noise (no Aer required).

Mixes the ideal statevector distribution with a depolarizing channel whose
strength scales with 1q/2q gate counts, then applies independent readout
bit-flips. This is the same model IBM Runtime documents as a *toy* noise
model — not a device calibration.

References:
- Nielsen & Chuang, depolarizing channel
- Qiskit Aer NoiseModel (we reimplement the classical mixture so ``--lite``
  installs without ``qiskit-aer``)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .simulation import strip_measurements
from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


@dataclass
class NoiseModel:
    """Per-gate depolarizing + independent readout bit-flip."""

    p1: float = 0.001
    p2: float = 0.01
    p_readout: float = 0.02
    name: str = "depolarizing+readout"

    def clamped(self) -> "NoiseModel":
        return NoiseModel(
            p1=float(min(1.0, max(0.0, self.p1))),
            p2=float(min(1.0, max(0.0, self.p2))),
            p_readout=float(min(1.0, max(0.0, self.p_readout))),
            name=self.name,
        )


@dataclass
class NoisySimulationResult:
    num_qubits: int
    depth: int
    shots: int
    seed: int
    one_qubit_gates: int
    two_qubit_gates: int
    survival_probability: float
    noise: Dict[str, float]
    ideal_probabilities: Dict[str, float] = field(default_factory=dict)
    noisy_probabilities: Dict[str, float] = field(default_factory=dict)
    noisy_counts: Dict[str, int] = field(default_factory=dict)
    total_variation_distance: float = 0.0
    hellinger_distance: float = 0.0
    model: str = "phenomenological_depolarizing_readout"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def count_gates(circuit: QuantumCircuit) -> Tuple[int, int]:
    """Return (1q, 2q) gate counts, ignoring measure/barrier/reset."""
    n1 = n2 = 0
    skip = {"measure", "barrier", "reset", "delay"}
    for inst in circuit.data:
        name = getattr(inst.operation, "name", "")
        if name in skip:
            continue
        nq = getattr(inst.operation, "num_qubits", None)
        if nq is None:
            nq = len(getattr(inst, "qubits", ()) or ())
        if int(nq) >= 2:
            n2 += 1
        else:
            n1 += 1
    return n1, n2


def survival_probability(n1: int, n2: int, model: NoiseModel) -> float:
    """P(circuit still implements the ideal unitary) under independent depolarizing."""
    m = model.clamped()
    return float(((1.0 - m.p1) ** max(0, n1)) * ((1.0 - m.p2) ** max(0, n2)))


def _all_bitstrings(n: int) -> List[str]:
    return [format(i, f"0{n}b") for i in range(1 << n)]


def apply_readout_bitflips(probs: Dict[str, float], n: int, p_readout: float) -> Dict[str, float]:
    """Independent bit-flip channel on computational-basis labels."""
    p = float(min(1.0, max(0.0, p_readout)))
    if p <= 0.0 or n <= 0:
        return dict(probs)
    current: Dict[str, float] = dict(probs)
    for pos in range(n):
        nxt: Dict[str, float] = {}
        for bitstr, pr in current.items():
            stay = pr * (1.0 - p)
            nxt[bitstr] = nxt.get(bitstr, 0.0) + stay
            bits = list(bitstr)
            bits[pos] = "1" if bits[pos] == "0" else "0"
            flipped = "".join(bits)
            nxt[flipped] = nxt.get(flipped, 0.0) + pr * p
        current = nxt
    return current


def mix_depolarizing(ideal: Dict[str, float], n: int, survival: float) -> Dict[str, float]:
    """p' = s p + (1-s)/2^n  (global depolarizing mixture)."""
    s = float(min(1.0, max(0.0, survival)))
    dim = 1 << n
    uniform = (1.0 - s) / dim
    out: Dict[str, float] = {}
    for key in _all_bitstrings(n):
        out[key] = s * float(ideal.get(key, 0.0)) + uniform
    return out


def total_variation(p: Dict[str, float], q: Dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * float(sum(abs(float(p.get(k, 0.0)) - float(q.get(k, 0.0))) for k in keys))


def hellinger(p: Dict[str, float], q: Dict[str, float]) -> float:
    keys = set(p) | set(q)
    acc = 0.0
    for k in keys:
        acc += (float(p.get(k, 0.0)) ** 0.5 - float(q.get(k, 0.0)) ** 0.5) ** 2
    return float((acc / 2.0) ** 0.5)


def _ideal_probs(circuit: QuantumCircuit) -> Tuple[int, int, Dict[str, float]]:
    sv_circ = strip_measurements(circuit)
    sv = Statevector.from_instruction(sv_circ)
    raw = sv.probabilities_dict()
    n = sv_circ.num_qubits
    probs = {k: float(v) for k, v in raw.items() if float(v) > 1e-15}
    # Fill missing mass so TVD vs uniform is well-defined
    for key in _all_bitstrings(n):
        probs.setdefault(key, 0.0)
    return n, int(circuit.depth()), probs


def noisy_distribution(
    circuit: QuantumCircuit,
    model: Optional[NoiseModel] = None,
    scale: float = 1.0,
) -> Tuple[Dict[str, float], Dict[str, float], int, int, float]:
    """Return (ideal, noisy, n1, n2, survival) for ``circuit``."""
    model = (model or NoiseModel()).clamped()
    scaled = NoiseModel(
        p1=min(1.0, model.p1 * scale),
        p2=min(1.0, model.p2 * scale),
        p_readout=model.p_readout,  # readout is not folded
        name=model.name,
    )
    n, _depth, ideal = _ideal_probs(circuit)
    n1, n2 = count_gates(strip_measurements(circuit))
    surv = survival_probability(n1, n2, scaled)
    mixed = mix_depolarizing(ideal, n, surv)
    noisy = apply_readout_bitflips(mixed, n, scaled.p_readout)
    return ideal, noisy, n1, n2, surv


def sample_counts(probs: Dict[str, float], shots: int, seed: int) -> Dict[str, int]:
    keys = list(probs.keys())
    pvals = np.array([float(probs[k]) for k in keys], dtype=float)
    total = float(pvals.sum()) or 1.0
    pvals = pvals / total
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(keys), size=int(shots), p=pvals)
    counts: Dict[str, int] = {}
    for idx in picks:
        counts[keys[int(idx)]] = counts.get(keys[int(idx)], 0) + 1
    return counts


def run_noisy_simulation(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    bitstring: Optional[str] = None,
    shots: int = 1024,
    seed: int = 42,
    p1: float = 0.001,
    p2: float = 0.01,
    p_readout: float = 0.02,
    scale: float = 1.0,
) -> NoisySimulationResult:
    """Ideal vs noisy shot experiment for a named workload or circuit."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for noisy simulation.")
    qc = circuit or resolve_circuit(workload=workload, qubits=qubits, qasm=qasm, bitstring=bitstring)
    model = NoiseModel(p1=p1, p2=p2, p_readout=p_readout)
    ideal, noisy, n1, n2, surv = noisy_distribution(qc, model, scale=scale)
    n = qc.num_qubits
    shots = max(0, int(shots))
    counts = sample_counts(noisy, shots, seed) if shots else {}
    tvd = total_variation(ideal, noisy)
    hel = hellinger(ideal, noisy)
    top_ideal = sorted(ideal.items(), key=lambda kv: kv[1], reverse=True)[:8]
    top_noisy = sorted(noisy.items(), key=lambda kv: kv[1], reverse=True)[:8]
    return NoisySimulationResult(
        num_qubits=n,
        depth=int(qc.depth()),
        shots=shots,
        seed=seed,
        one_qubit_gates=n1,
        two_qubit_gates=n2,
        survival_probability=surv,
        noise={"p1": model.p1, "p2": model.p2, "p_readout": model.p_readout, "scale": scale},
        ideal_probabilities={k: float(v) for k, v in top_ideal},
        noisy_probabilities={k: float(v) for k, v in top_noisy},
        noisy_counts=counts,
        total_variation_distance=tvd,
        hellinger_distance=hel,
    )
