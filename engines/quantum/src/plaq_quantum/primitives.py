"""Local Sampler / Estimator primitives (no IBM account, no Aer).

Qiskit Runtime's SamplerV2 / EstimatorV2 are the 2025+ API. This module
mirrors them on the statevector so agents can ask for bitstring distributions
and Pauli expectation values without ``qiskit-ibm-runtime``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .simulation import strip_measurements
from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Pauli, Statevector

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


def _circuit(circuit=None, **kwargs) -> QuantumCircuit:
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for primitives.")
    return circuit or resolve_circuit(**kwargs)


def _sv(circuit: QuantumCircuit) -> Any:
    return Statevector.from_instruction(strip_measurements(circuit))


@dataclass
class SamplerResult:
    num_qubits: int
    shots: int
    counts: Dict[str, int] = field(default_factory=dict)
    probabilities: Dict[str, float] = field(default_factory=dict)
    seed: int = 42
    backend: str = "statevector_sampler"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EstimatorResult:
    num_qubits: int
    observable: str
    expectation: float
    variance: float
    shots: int
    std_error: float
    backend: str = "statevector_estimator"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_sampler(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    shots: int = 1024,
    seed: int = 42,
) -> SamplerResult:
    """Sample bitstrings from the ideal statevector (SamplerV2 analogue)."""
    qc = _circuit(circuit, workload=workload, qubits=qubits, qasm=qasm)
    sv = _sv(qc)
    n = qc.num_qubits
    shots = max(1, int(shots))
    try:
        counts_raw = sv.sample_counts(shots, seed=seed)
    except TypeError:
        probs = sv.probabilities_dict()
        keys = list(probs)
        pvals = np.array([float(probs[k]) for k in keys], dtype=float)
        pvals = pvals / (float(pvals.sum()) or 1.0)
        rng = np.random.default_rng(seed)
        picks = rng.choice(len(keys), size=shots, p=pvals)
        counts_raw = {}
        for idx in picks:
            counts_raw[keys[int(idx)]] = counts_raw.get(keys[int(idx)], 0) + 1
    counts = {str(k): int(v) for k, v in counts_raw.items()}
    total = float(sum(counts.values()) or 1)
    ranked = sorted(((k, v / total) for k, v in counts.items()), key=lambda kv: kv[1], reverse=True)
    return SamplerResult(
        num_qubits=n,
        shots=shots,
        counts=counts,
        probabilities={k: float(v) for k, v in ranked[:16]},
        seed=seed,
    )


def _pauli(observable: str, n: int) -> Any:
    label = (observable or "Z" * n).replace(" ", "").upper()
    if label.startswith("PAULI"):
        label = label.split("(")[-1].rstrip(")")
    if len(label) == 1:
        label = label + ("I" * (n - 1))
    if len(label) != n:
        # right-align, pad with I on the left (qiskit little-endian: left is high qubit)
        if len(label) < n:
            label = ("I" * (n - len(label))) + label
        else:
            label = label[-n:]
    return Pauli(label)


def run_estimator(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    observable: str = "Z",
    shots: int = 0,
    seed: int = 42,
) -> EstimatorResult:
    """⟨ψ|P|ψ⟩ for a Pauli string. shots=0 is exact; shots>0 is sampled."""
    qc = _circuit(circuit, workload=workload, qubits=qubits, qasm=qasm)
    sv = _sv(qc)
    n = qc.num_qubits
    pauli = _pauli(observable, n)
    exact = float(np.real(sv.expectation_value(pauli)))
    if shots and shots > 0:
        # Monte-Carlo estimate via Z-basis after rotating P to Z
        rng = np.random.default_rng(seed)
        # Sample computational basis and evaluate the diagonal of P in that basis.
        probs = sv.probabilities_dict()
        keys = list(probs)
        pvals = np.array([float(probs[k]) for k in keys], dtype=float)
        pvals = pvals / (float(pvals.sum()) or 1.0)
        picks = rng.choice(len(keys), size=int(shots), p=pvals)
        # For a general Pauli, map bits through X/Y (treat Y like X for bit, Z for phase).
        label = pauli.to_label()
        acc = []
        for idx in picks:
            bitstr = keys[int(idx)]
            # qiskit label is little-endian: leftmost char is qubit n-1
            val = 1.0
            skip = False
            for q, ch in enumerate(reversed(label)):
                bit = bitstr[n - 1 - q] if n - 1 - q < len(bitstr) else "0"
                # Use bitstring as already measured in Z; X/Y observables need Hadamard
                # We already sampled in Z, so only Z/I are unbiased this way.
                if ch in {"X", "Y"}:
                    skip = True
                    break
                if ch == "Z" and bit == "1":
                    val *= -1.0
            if not skip:
                acc.append(val)
        if acc:
            mean = float(np.mean(acc))
            var = float(np.var(acc))
            se = float(np.sqrt(var / len(acc))) if acc else 0.0
            return EstimatorResult(
                num_qubits=n,
                observable=label,
                expectation=mean,
                variance=var,
                shots=int(shots),
                std_error=se,
            )
    return EstimatorResult(
        num_qubits=n,
        observable=pauli.to_label(),
        expectation=exact,
        variance=max(0.0, 1.0 - exact * exact),
        shots=0,
        std_error=0.0,
    )


def estimate_hamiltonian(
    circuit: QuantumCircuit,
    terms: Sequence[Tuple[str, float]],
) -> float:
    """⟨H⟩ = Σ c_i ⟨P_i⟩ for a list of (Pauli, coeff) terms."""
    acc = 0.0
    for label, coeff in terms:
        acc += float(coeff) * run_estimator(circuit, observable=str(label)).expectation
    return float(acc)
