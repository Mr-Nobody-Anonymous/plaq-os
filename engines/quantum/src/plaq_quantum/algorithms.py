"""Small textbook algorithms agents can compile and simulate.

These are exact, tiny circuits (2–4 qubits) used as NISQ lab workloads.
They do not replace the FTQC cost-model workloads in ``circuits.py``.
"""

from __future__ import annotations

from typing import Any

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


def _require() -> None:
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")


def make_deutsch_jozsa_circuit(balanced: bool = True) -> QuantumCircuit:
    """2-qubit Deutsch–Jozsa: constant (identity) vs balanced (CNOT) oracle."""
    _require()
    qc = QuantumCircuit(2, name="deutsch_jozsa")
    qc.x(1)
    qc.h(0)
    qc.h(1)
    if balanced:
        qc.cx(0, 1)
    qc.h(0)
    return qc


def make_grover_circuit(n_qubits: int = 2, marked: str = "11") -> QuantumCircuit:
    """n-qubit Grover with one iteration. Default marks |11…1⟩ (optimal at n=2)."""
    _require()
    n = max(2, int(n_qubits))
    bits = (marked or "1" * n).replace(" ", "")
    if len(bits) != n:
        bits = ("1" * n)[-n:]
    qc = QuantumCircuit(n, name="grover")
    for i in range(n):
        qc.h(i)
    # Oracle: phase flip on the marked basis state
    zeros = [i for i, b in enumerate(reversed(bits)) if b == "0"]
    for i in zeros:
        qc.x(i)
    if n == 1:
        qc.z(0)
    elif n == 2:
        qc.cz(0, 1)
    else:
        qc.h(n - 1)
        qc.mcx(list(range(n - 1)), n - 1)
        qc.h(n - 1)
    for i in zeros:
        qc.x(i)
    # Diffuser
    for i in range(n):
        qc.h(i)
        qc.x(i)
    if n == 2:
        qc.cz(0, 1)
    else:
        qc.h(n - 1)
        qc.mcx(list(range(n - 1)), n - 1)
        qc.h(n - 1)
    for i in range(n):
        qc.x(i)
        qc.h(i)
    return qc


def make_teleport_circuit() -> QuantumCircuit:
    """3-qubit teleportation *encoding* (Bell pair + Bell measurement gates, no collapse)."""
    _require()
    qc = QuantumCircuit(3, name="teleport")
    qc.h(0)  # message |+⟩
    qc.h(1)
    qc.cx(1, 2)
    qc.cx(0, 1)
    qc.h(0)
    return qc


def make_qpe_circuit() -> QuantumCircuit:
    """3-qubit QPE of S on |1⟩ (eigenphase 1/4). Counting register peaks near 01."""
    _require()
    qc = QuantumCircuit(3, name="qpe")
    qc.x(2)  # eigenstate |1⟩ of S
    qc.h(0)
    qc.h(1)
    # qubit 1 = LSB counting bit: controlled-S = cp(π/2)
    qc.cp(1.5707963267948966, 1, 2)
    # qubit 0 = 2^1: controlled-S^2 = Z = cp(π)
    qc.cp(3.141592653589793, 0, 2)
    # Inverse QFT on the 2 counting qubits
    qc.h(0)
    qc.cp(-1.5707963267948966, 0, 1)
    qc.h(1)
    return qc


def make_toffoli_circuit() -> QuantumCircuit:
    """3-qubit Toffoli (CCX) — a non-Clifford kernel used in arithmetic."""
    _require()
    qc = QuantumCircuit(3, name="toffoli")
    qc.h(0)
    qc.h(1)
    qc.ccx(0, 1, 2)
    return qc
