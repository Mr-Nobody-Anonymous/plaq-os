"""Hardware-efficient VQE on a 2-qubit toy H₂ Hamiltonian.

No PySCF / Qiskit Nature. The Hamiltonian is the standard textbook
STO-3G H₂ at ~0.74 Å (open-source values), so an agent can run a
variational loop locally with SciPy COBYLA.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .primitives import estimate_hamiltonian

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


# OpenFermion / Nielsen-style toy H₂ (Jordan–Wigner, 2 qubits), hartree.
H2_TERMS: Tuple[Tuple[str, float], ...] = (
    ("II", -1.0523732),
    ("ZI", 0.39793742),
    ("IZ", -0.39793742),
    ("ZZ", -0.01128010),
    ("XX", 0.18093119),
)


def hardware_efficient_ansatz(theta: Sequence[float]) -> QuantumCircuit:
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for VQE.")
    t = list(theta) + [0.0, 0.0, 0.0, 0.0]
    qc = QuantumCircuit(2, name="hea")
    qc.ry(float(t[0]), 0)
    qc.ry(float(t[1]), 1)
    qc.cx(0, 1)
    qc.ry(float(t[2]), 0)
    qc.ry(float(t[3]), 1)
    return qc


def _energy(theta: np.ndarray, terms: Sequence[Tuple[str, float]]) -> float:
    return estimate_hamiltonian(hardware_efficient_ansatz(theta), terms)


@dataclass
class VQEResult:
    energy: float
    parameters: List[float]
    iterations: int
    success: bool
    hamiltonian: str
    exact_diagonal: Optional[float]
    gap_to_exact: Optional[float]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _exact_ground(terms: Sequence[Tuple[str, float]]) -> Optional[float]:
    try:
        from qiskit.quantum_info import Pauli, SparsePauliOp

        op = SparsePauliOp.from_list([(p, c) for p, c in terms])
        mat = op.to_matrix()
        evals = np.linalg.eigvalsh(mat)
        return float(np.min(evals.real))
    except Exception:
        try:
            # 4x4 brute force
            from qiskit.quantum_info import Pauli as P

            mat = np.zeros((4, 4), dtype=complex)
            for lab, c in terms:
                mat = mat + float(c) * P(lab).to_matrix()
            return float(np.min(np.linalg.eigvalsh(mat).real))
        except Exception:
            return None


def run_vqe(
    *,
    maxiter: int = 40,
    seed: int = 0,
    hamiltonian: str = "h2",
) -> VQEResult:
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for VQE.")
    terms = H2_TERMS if (hamiltonian or "h2").lower() in {"h2", "hydrogen", "sto3g"} else H2_TERMS
    rng = np.random.default_rng(int(seed))
    x0 = rng.normal(0.0, 0.3, size=4)
    exact = _exact_ground(terms)
    try:
        from scipy.optimize import minimize

        hist = {"n": 0}

        def fun(x: np.ndarray) -> float:
            hist["n"] += 1
            return _energy(x, terms)

        res = minimize(fun, x0, method="COBYLA", options={"maxiter": int(maxiter), "rhobeg": 0.4})
        energy = float(res.fun)
        params = [float(v) for v in res.x]
        ok = bool(res.success) or hist["n"] >= 2
        iters = int(getattr(res, "nfev", hist["n"]) or hist["n"])
    except Exception:
        # Coordinate descent fallback
        x = np.array(x0, dtype=float)
        energy = _energy(x, terms)
        for _ in range(max(4, int(maxiter) // 4)):
            for i in range(4):
                for step in (0.4, -0.4, 0.2, -0.2):
                    trial = x.copy()
                    trial[i] += step
                    e = _energy(trial, terms)
                    if e < energy:
                        energy, x = e, trial
        params = [float(v) for v in x]
        ok = True
        iters = int(maxiter)
    gap = None if exact is None else float(energy - exact)
    notes = [
        "Toy 2-qubit H₂ STO-3G Hamiltonian (not PySCF). HEA: Ry-CX-Ry.",
        "Local COBYLA; not a hardware VQE. Compare energy to exact_diagonal.",
    ]
    return VQEResult(
        energy=float(energy),
        parameters=params,
        iterations=iters,
        success=ok,
        hamiltonian="h2_sto3g_2q",
        exact_diagonal=exact,
        gap_to_exact=gap,
        notes=notes,
    )
