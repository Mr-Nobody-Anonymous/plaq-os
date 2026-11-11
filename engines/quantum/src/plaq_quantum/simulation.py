"""Circuit-level simulation for agent-driven quantum experiments.

Uses Qiskit's ``quantum_info.Statevector`` (no Aer dependency) so agents can:
- inspect amplitudes / measurement probabilities
- sample shot counts
- evaluate a toy Ising / MaxCut cost Hamiltonian
- compare two circuits by state fidelity
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector, state_fidelity

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


@dataclass
class CircuitSimulationResult:
    """Outcome of a statevector or shot-based circuit simulation."""

    num_qubits: int
    depth: int
    mode: str  # 'statevector' | 'shots'
    shots: int
    probabilities: Dict[str, float] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    energy: Optional[float] = None
    energy_kind: Optional[str] = None
    top_bitstrings: List[Tuple[str, float]] = field(default_factory=list)
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def strip_measurements(circuit: QuantumCircuit) -> QuantumCircuit:
    """Return a copy of ``circuit`` with final measurements removed (statevector-safe)."""
    if hasattr(circuit, "remove_final_measurements"):
        return circuit.remove_final_measurements(inplace=False)
    qc = circuit.copy()
    # Fallback: drop measure instructions
    new = qc.copy()
    new.data = [inst for inst in qc.data if inst.operation.name not in {"measure", "barrier"}]
    return new


def _bitstring_probs(sv: Any, limit: int = 16) -> Tuple[Dict[str, float], List[Tuple[str, float]]]:
    raw = sv.probabilities_dict()
    # Keep only non-trivial mass; cap payload size for agent tools.
    filtered = {k: float(v) for k, v in raw.items() if float(v) > 1e-12}
    ranked = sorted(filtered.items(), key=lambda kv: kv[1], reverse=True)
    top = [(k, float(v)) for k, v in ranked[:limit]]
    return {k: float(v) for k, v in ranked[: max(limit, 32)]}, top


def _cycle_maxcut_energy(sv: Any, n_qubits: int) -> float:
    """⟨C⟩ for MaxCut on a ring: C = Σ_i (1 - Z_i Z_{i+1}) / 2."""
    from qiskit.quantum_info import Pauli

    energy = 0.0
    for i in range(n_qubits):
        j = (i + 1) % n_qubits
        label = ["I"] * n_qubits
        label[n_qubits - 1 - i] = "Z"
        label[n_qubits - 1 - j] = "Z"
        zz = sv.expectation_value(Pauli("".join(label)))
        energy += 0.5 * (1.0 - float(np.real(zz)))
    return float(energy)


def _ising_energy(sv: Any, n_qubits: int) -> float:
    """Toy 1-D Ising energy ⟨Σ Z_i + Σ Z_i Z_{i+1}⟩ (not a chemistry Hamiltonian)."""
    from qiskit.quantum_info import Pauli

    energy = 0.0
    for i in range(n_qubits):
        label = ["I"] * n_qubits
        label[n_qubits - 1 - i] = "Z"
        energy += float(np.real(sv.expectation_value(Pauli("".join(label)))))
    for i in range(n_qubits - 1):
        label = ["I"] * n_qubits
        label[n_qubits - 1 - i] = "Z"
        label[n_qubits - 1 - (i + 1)] = "Z"
        energy += float(np.real(sv.expectation_value(Pauli("".join(label)))))
    return float(energy)


def run_circuit_simulation(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    bitstring: Optional[str] = None,
    shots: int = 0,
    seed: int = 42,
    compute_energy: bool = False,
    energy_kind: str = "auto",
) -> CircuitSimulationResult:
    """Simulate ``circuit`` (or a named workload) with statevector or shots."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for circuit simulation.")

    qc = circuit or resolve_circuit(
        workload=workload, qubits=qubits, qasm=qasm, bitstring=bitstring
    )
    n = qc.num_qubits
    depth = int(qc.depth())
    sv_circ = strip_measurements(qc)
    sv = Statevector.from_instruction(sv_circ)

    kind = (energy_kind or "auto").lower()
    energy: Optional[float] = None
    used_kind: Optional[str] = None
    if compute_energy or kind in {"maxcut", "qaoa", "ising"}:
        if kind in {"maxcut", "qaoa"} or (kind == "auto" and workload and "qaoa" in workload.lower()):
            energy = _cycle_maxcut_energy(sv, n)
            used_kind = "maxcut_cycle"
        else:
            energy = _ising_energy(sv, n)
            used_kind = "ising_1d"

    if shots and shots > 0:
        try:
            counts_raw = sv.sample_counts(int(shots), seed=seed)
        except TypeError:
            # Qiskit QuantumState.sample_counts has no `seed` on some versions.
            prob_map = sv.probabilities_dict()
            keys = list(prob_map.keys())
            pvals = np.array([float(prob_map[k]) for k in keys], dtype=float)
            total = float(pvals.sum()) or 1.0
            pvals = pvals / total
            rng = np.random.default_rng(seed)
            picks = rng.choice(len(keys), size=int(shots), p=pvals)
            counts_raw = {}
            for idx in picks:
                counts_raw[keys[int(idx)]] = counts_raw.get(keys[int(idx)], 0) + 1
        counts = {str(k): int(v) for k, v in counts_raw.items()}
        total = float(sum(counts.values()) or 1)
        probs = {k: v / total for k, v in counts.items()}
        ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:16]
        return CircuitSimulationResult(
            num_qubits=n,
            depth=depth,
            mode="shots",
            shots=int(shots),
            probabilities={k: float(v) for k, v in ranked},
            counts=counts,
            energy=energy,
            energy_kind=used_kind,
            top_bitstrings=[(k, float(v)) for k, v in ranked],
            seed=seed,
        )

    probs, top = _bitstring_probs(sv)
    return CircuitSimulationResult(
        num_qubits=n,
        depth=depth,
        mode="statevector",
        shots=0,
        probabilities=probs,
        counts={},
        energy=energy,
        energy_kind=used_kind,
        top_bitstrings=top,
        seed=seed,
    )


def circuit_fidelity(a: QuantumCircuit, b: QuantumCircuit) -> float:
    """State fidelity between two circuits (measurements stripped)."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for fidelity.")
    sv_a = Statevector.from_instruction(strip_measurements(a))
    sv_b = Statevector.from_instruction(strip_measurements(b))
    return float(state_fidelity(sv_a, sv_b))
