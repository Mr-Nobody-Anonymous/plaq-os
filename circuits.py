"""
Q-Day OS Circuit Generators & Workload Benchmarks

Generates reproducible quantum algorithm workloads:
- Deterministic RZ/CX test circuits
- QAOA MaxCut ansatz circuits
- Quantum Fourier Transform (QFT)
- Bernstein-Vazirani circuits
- Random Clifford+T circuits for magic state distillation benchmarking
- Molecular Quantum Chemistry Hamiltonian ansatz (FeMoCo / Molecular VQE)
- Cryptographic Shor Modular Exponentiation benchmark
"""

from __future__ import annotations
import math
import random
from typing import Dict, Any, Optional

try:
    from qiskit import QuantumCircuit
    HAS_QISKIT = True
except ImportError:
    HAS_QISKIT = False


def make_test_circuit(n_qubits: int = 5, measure: bool = True) -> QuantumCircuit:
    """Standard deterministic test circuit."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")

    circuit = QuantumCircuit(n_qubits)
    for q in range(n_qubits):
        circuit.h(q)
    for q in range(n_qubits - 1):
        circuit.cx(q, q + 1)
    for q in range(n_qubits):
        circuit.rz(0.31 * (q + 1), q)
    for q in range(n_qubits - 1):
        circuit.cx(q, q + 1)
    if measure:
        circuit.measure_all()
    return circuit


def make_qaoa_circuit(n_qubits: int = 6, p_layers: int = 2, gamma: float = 0.45, beta: float = 0.72) -> QuantumCircuit:
    """Generate a QAOA MaxCut ansatz circuit on a cyclic graph."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")

    qc = QuantumCircuit(n_qubits)
    for q in range(n_qubits):
        qc.h(q)

    for layer in range(p_layers):
        for i in range(n_qubits):
            j = (i + 1) % n_qubits
            qc.cx(i, j)
            qc.rz(2 * gamma * (layer + 1), j)
            qc.cx(i, j)

        for q in range(n_qubits):
            qc.rx(2 * beta * (layer + 1), q)

    qc.measure_all()
    return qc


def make_qft_circuit(n_qubits: int = 6, approximation_degree: int = 0) -> QuantumCircuit:
    """Generate a Quantum Fourier Transform circuit."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")

    qc = QuantumCircuit(n_qubits)
    for i in range(n_qubits):
        qc.h(i)
        for j in range(i + 1, n_qubits):
            k = j - i + 1
            if approximation_degree > 0 and k > approximation_degree:
                continue
            angle = math.pi / (2 ** (j - i))
            qc.cp(angle, j, i)
    for i in range(n_qubits // 2):
        qc.swap(i, n_qubits - 1 - i)

    qc.measure_all()
    return qc


def make_bernstein_vazirani_circuit(bitstring: str = "10110") -> QuantumCircuit:
    """Generate a Bernstein-Vazirani oracle and solver circuit."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")

    n = len(bitstring)
    qc = QuantumCircuit(n + 1, n)
    qc.x(n)
    for i in range(n + 1):
        qc.h(i)

    for i, bit in enumerate(reversed(bitstring)):
        if bit == "1":
            qc.cx(i, n)

    for i in range(n):
        qc.h(i)
        qc.measure(i, i)

    return qc


def make_random_clifford_t_circuit(
    n_qubits: int = 5,
    depth: int = 15,
    t_density: float = 0.35,
    seed: int = 42
) -> QuantumCircuit:
    """Generate a random Clifford+T circuit."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")

    rng = random.Random(seed)
    qc = QuantumCircuit(n_qubits)
    single_clifford = ["h", "s", "x", "z"]

    for d in range(depth):
        for q in range(n_qubits):
            roll = rng.random()
            if roll < t_density:
                qc.t(q)
            elif roll < 0.75:
                gate = rng.choice(single_clifford)
                getattr(qc, gate)(q)

        pairs = list(range(n_qubits - 1))
        rng.shuffle(pairs)
        for p in pairs[: max(1, n_qubits // 2)]:
            qc.cx(p, p + 1)

    qc.measure_all()
    return qc


def make_chemistry_ansatz_circuit(n_qubits: int = 6, trotter_steps: int = 2) -> QuantumCircuit:
    """
    Generate a Unitary Coupled Cluster / Trotterized electronic structure
    Hamiltonian circuit representing molecular orbital simulation (e.g., FeMoCo / LiH).
    Features high density of non-Clifford phase rotations and entangling chains.
    """
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")

    qc = QuantumCircuit(n_qubits)
    qc.x(0)
    qc.x(1)

    for step in range(trotter_steps):
        for i in range(0, n_qubits - 1, 2):
            qc.h(i)
            qc.h(i + 1)
            qc.cx(i, i + 1)
            qc.rz(0.42 * (step + 1), i + 1)
            qc.cx(i, i + 1)
            qc.h(i)
            qc.h(i + 1)

        for i in range(n_qubits - 3):
            qc.cx(i, i + 1)
            qc.cx(i + 1, i + 2)
            qc.cx(i + 2, i + 3)
            qc.t(i + 3)
            qc.rz(0.18 * (step + 1), i + 3)
            qc.cx(i + 2, i + 3)
            qc.cx(i + 1, i + 2)
            qc.cx(i, i + 1)

    qc.measure_all()
    return qc


def make_shor_modexp_circuit(n_qubits: int = 7) -> QuantumCircuit:
    """
    Generate modular exponentiation kernel for Shor's factoring algorithm.
    Represents cryptanalytic factoring workloads with deep arithmetic carry chains.
    """
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")

    qc = QuantumCircuit(n_qubits)
    ctrl_qubits = n_qubits // 2
    for c in range(ctrl_qubits):
        qc.h(c)

    for c in range(ctrl_qubits):
        for target in range(ctrl_qubits, n_qubits - 1):
            qc.cx(c, target)
            qc.t(target)
            qc.cx(target, target + 1)
            qc.tdg(target + 1)
            qc.cx(c, target + 1)

    for i in range(ctrl_qubits):
        qc.h(i)
        for j in range(i + 1, ctrl_qubits):
            angle = -math.pi / (2 ** (j - i))
            qc.cp(angle, j, i)

    qc.measure_all()
    return qc


WORKLOAD_MANIFEST: Dict[str, Dict[str, Any]] = {
    "test_rz_cx_5q": {
        "family": "synthetic_verification",
        "mathematical_task": "Deterministic alternating Hadamard, Entangling CX, and RZ rotation layers",
        "semantics": "Single-qubit superposition followed by 1D nearest-neighbor CX chain and arbitrary phase shifts",
        "logical_qubits": 5,
        "literature_reference": "Standard Qiskit transpiler regression suite",
        "correctness_criteria": "Unitary equivalence under statevector simulation",
    },
    "test_rz_cx_8q": {
        "family": "synthetic_verification",
        "mathematical_task": "8-qubit deterministic alternating Hadamard, Entangling CX, and RZ rotation layers",
        "semantics": "Medium-width linear entanglement verification kernel",
        "logical_qubits": 8,
        "literature_reference": "Standard Qiskit transpiler regression suite",
        "correctness_criteria": "Unitary equivalence under statevector simulation",
    },
    "qaoa_cycle_6q": {
        "family": "combinatorial_optimization",
        "mathematical_task": "Quantum Approximate Optimization Algorithm for MaxCut on 6-node ring graph",
        "semantics": "Cost Hamiltonian exp(-i gamma C) followed by Mixer Hamiltonian exp(-i beta B) for p=2 steps",
        "logical_qubits": 6,
        "literature_reference": "Farhi, Goldstone, Gutmann (2014) arXiv:1411.4028",
        "correctness_criteria": "Statevector expectation value of MaxCut cost Hamiltonian <C> > 0.7 * C_max",
    },
    "qft_6q": {
        "family": "quantum_arithmetic",
        "mathematical_task": "Discrete Quantum Fourier Transform on 6 logical qubits",
        "semantics": "Unitary mapping |j> -> 1/sqrt(N) sum_k exp(2 pi i j k / N) |k> with controlled phase gates",
        "logical_qubits": 6,
        "literature_reference": "Nielsen & Chuang (2010) Quantum Computation and Quantum Information, Ch. 5",
        "correctness_criteria": "Exact unitary matrix matching classical DFT Vandermonde matrix",
    },
    "bv_oracle_6q": {
        "family": "oracle_search",
        "mathematical_task": "Bernstein-Vazirani single-query hidden bitstring recovery for s = 110101",
        "semantics": "Inner product oracle f(x) = s . x (mod 2) with Hadamard interferometry",
        "logical_qubits": 6,
        "literature_reference": "Bernstein & Vazirani (1997) SIAM J. Comput. 26(5)",
        "correctness_criteria": "Deterministic measurement outcome probability P(s='110101') == 1.0",
    },
    "clifford_t_5q": {
        "family": "fault_tolerant_benchmarking",
        "mathematical_task": "Random Clifford+T benchmark circuit with controlled non-Clifford density",
        "semantics": "Haar-like pseudorandom state generation composed strictly of Clifford generators and T-gates",
        "logical_qubits": 5,
        "literature_reference": "Bravyi & Kitaev (2005) Universal quantum computation with ideal Clifford gates and noisy ancillas",
        "correctness_criteria": "Gate set restricted strictly to H, S, CX, and T",
    },
    "chemistry_femoco_6q": {
        "family": "quantum_chemistry",
        "mathematical_task": "Second-quantized electronic structure Hamiltonian Trotter step for nitrogenase active site model",
        "semantics": "Jordan-Wigner mapped fermionic excitation operators exp(-i H t) with electron hopping and Coulomb terms",
        "logical_qubits": 6,
        "literature_reference": "Reiher et al. (2017) PNAS 114(29): Elucidating reaction mechanisms on quantum computers",
        "correctness_criteria": "Fermionic parity conservation under unitary Trotter step",
    },
    "shor_rsa_kernel_7q": {
        "family": "cryptanalysis",
        "mathematical_task": "In-place modular multiplication and semiclassical QFT for Shor period finding",
        "semantics": "Toffoli-derived modular addition carry networks followed by controlled phase rotation readout",
        "logical_qubits": 7,
        "literature_reference": "Shor (1994) / Beauregard (2003) Circuit for Shor's algorithm using 2n+3 qubits",
        "correctness_criteria": "Deterministic phase extraction for coprime base a=2 (mod 15)",
    },
}


def get_benchmark_workloads() -> Dict[str, QuantumCircuit]:
    """Convenience dictionary of standard benchmarking workloads."""
    return {
        "test_rz_cx_5q": make_test_circuit(5),
        "test_rz_cx_8q": make_test_circuit(8),
        "qaoa_cycle_6q": make_qaoa_circuit(6, p_layers=2),
        "qft_6q": make_qft_circuit(6),
        "bv_oracle_6q": make_bernstein_vazirani_circuit("110101"),
        "clifford_t_5q": make_random_clifford_t_circuit(5, depth=12, t_density=0.4, seed=123),
        "chemistry_femoco_6q": make_chemistry_ansatz_circuit(6, trotter_steps=2),
        "shor_rsa_kernel_7q": make_shor_modexp_circuit(7),
    }


def get_workload_manifest() -> Dict[str, Dict[str, Any]]:
    """Return complete semantic manifest for all benchmark workloads."""
    return WORKLOAD_MANIFEST

