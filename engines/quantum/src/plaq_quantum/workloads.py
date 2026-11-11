"""Named workload resolver, OpenQASM loader, and hardware listing helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .circuits import (
    WORKLOAD_MANIFEST,
    get_benchmark_workloads,
    make_bernstein_vazirani_circuit,
    make_chemistry_ansatz_circuit,
    make_qaoa_circuit,
    make_qft_circuit,
    make_random_clifford_t_circuit,
    make_shor_modexp_circuit,
    make_test_circuit,
)
from .hardware import HARDWARE_CATALOG, HardwareModel

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


WORKLOAD_ALIASES: Dict[str, str] = {
    "bv": "bv_oracle_6q",
    "bernstein": "bv_oracle_6q",
    "bernstein_vazirani": "bv_oracle_6q",
    "qaoa": "qaoa_cycle_6q",
    "maxcut": "qaoa_cycle_6q",
    "qft": "qft_6q",
    "chemistry": "chemistry_femoco_6q",
    "vqe": "chemistry_femoco_6q",
    "femoco": "chemistry_femoco_6q",
    "shor": "shor_rsa_kernel_7q",
    "rsa": "shor_rsa_kernel_7q",
    "clifford": "clifford_t_5q",
    "clifford_t": "clifford_t_5q",
    "test": "test_rz_cx_5q",
    "rz_cx": "test_rz_cx_5q",
    "bell": "bell",
    "ghz": "ghz",
}


def make_bell_circuit() -> QuantumCircuit:
    """2-qubit Bell state |Φ+⟩ = (|00⟩+|11⟩)/√2."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")
    qc = QuantumCircuit(2, name="bell")
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


def make_ghz_circuit(n_qubits: int = 3) -> QuantumCircuit:
    """n-qubit GHZ state (|0…0⟩+|1…1⟩)/√2."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to generate QuantumCircuit objects.")
    n = max(2, int(n_qubits))
    qc = QuantumCircuit(n, name="ghz")
    qc.h(0)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    qc.measure_all()
    return qc


def load_qasm(qasm: str) -> QuantumCircuit:
    """Parse an OpenQASM 2.0 string into a QuantumCircuit."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to parse OpenQASM.")
    text = (qasm or "").strip()
    if not text:
        raise ValueError("OpenQASM string is empty.")
    try:
        from qiskit.qasm2 import loads as qasm2_loads

        return qasm2_loads(text)
    except Exception:
        if hasattr(QuantumCircuit, "from_qasm_str"):
            return QuantumCircuit.from_qasm_str(text)
        raise ValueError("Unable to parse OpenQASM 2.0 circuit.")


def _normalize(name: str) -> str:
    return name.lower().replace("-", "_").replace(" ", "_").strip()


def resolve_circuit(
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    bitstring: Optional[str] = None,
    qasm: Optional[str] = None,
    p_layers: int = 2,
    seed: int = 42,
    t_density: float = 0.4,
    trotter_steps: int = 2,
) -> QuantumCircuit:
    """Build a Qiskit circuit from a named workload, bitstring, or OpenQASM body."""
    if qasm:
        return load_qasm(qasm)
    if bitstring:
        return make_bernstein_vazirani_circuit(bitstring)

    key = _normalize(workload or "")
    if not key:
        return make_test_circuit(qubits or 4)
    key = WORKLOAD_ALIASES.get(key, key)

    if key == "bell":
        return make_bell_circuit()
    if key == "ghz":
        return make_ghz_circuit(qubits or 3)

    n = qubits
    factories = {
        "test_rz_cx_5q": lambda: make_test_circuit(n or 5),
        "test_rz_cx_8q": lambda: make_test_circuit(n or 8),
        "qaoa_cycle_6q": lambda: make_qaoa_circuit(n or 6, p_layers=p_layers),
        "qft_6q": lambda: make_qft_circuit(n or 6),
        "bv_oracle_6q": lambda: make_bernstein_vazirani_circuit(
            bitstring or ("1" * max(1, (n or 6) - 1) + "0")[: max(1, (n or 6) - 1)]
            if n
            else "110101"
        ),
        "clifford_t_5q": lambda: make_random_clifford_t_circuit(
            n or 5, depth=12, t_density=t_density, seed=seed
        ),
        "chemistry_femoco_6q": lambda: make_chemistry_ansatz_circuit(
            n or 6, trotter_steps=trotter_steps
        ),
        "shor_rsa_kernel_7q": lambda: make_shor_modexp_circuit(n or 7),
    }
    if key in factories:
        return factories[key]()

    if "qaoa" in key or "maxcut" in key:
        return make_qaoa_circuit(n or 6, p_layers=p_layers)
    if "qft" in key:
        return make_qft_circuit(n or 4)
    if "chem" in key or "vqe" in key or "femoco" in key:
        return make_chemistry_ansatz_circuit(n or 4, trotter_steps=trotter_steps)
    if "shor" in key:
        return make_shor_modexp_circuit(n or 7)
    if "bv" in key or "bernstein" in key:
        return make_bernstein_vazirani_circuit("101")
    if "clifford" in key:
        return make_random_clifford_t_circuit(n or 5, depth=12, t_density=t_density, seed=seed)
    if "ghz" in key:
        return make_ghz_circuit(n or 3)
    if "bell" in key:
        return make_bell_circuit()
    return make_test_circuit(n or 4)


def list_workloads() -> List[Dict[str, Any]]:
    """Return workload catalog entries with family, qubits, and aliases."""
    reverse_aliases: Dict[str, List[str]] = {}
    for alias, target in WORKLOAD_ALIASES.items():
        reverse_aliases.setdefault(target, []).append(alias)

    out: List[Dict[str, Any]] = []
    for name, meta in WORKLOAD_MANIFEST.items():
        row = dict(meta)
        row["id"] = name
        row["aliases"] = sorted(reverse_aliases.get(name, []))
        out.append(row)
    out.append(
        {
            "id": "bell",
            "family": "entanglement",
            "mathematical_task": "Prepare the 2-qubit Bell state |Φ+⟩",
            "logical_qubits": 2,
            "aliases": ["bell"],
        }
    )
    out.append(
        {
            "id": "ghz",
            "family": "entanglement",
            "mathematical_task": "Prepare an n-qubit GHZ state",
            "logical_qubits": 3,
            "aliases": ["ghz"],
        }
    )
    return out


def list_hardware_profiles() -> List[Dict[str, Any]]:
    """Serialize HARDWARE_CATALOG for agents / API / MCP."""
    rows: List[Dict[str, Any]] = []
    for key, hw in HARDWARE_CATALOG.items():
        rows.append(_hardware_row(key, hw))
    return rows


def _hardware_row(key: str, hw: HardwareModel) -> Dict[str, Any]:
    return {
        "id": key,
        "name": hw.name,
        "technology": hw.technology,
        "two_qubit_error": hw.two_qubit_error,
        "single_qubit_error": hw.single_qubit_error,
        "measurement_error": hw.measurement_error,
        "surface_code_threshold": hw.surface_code_threshold,
        "topology": hw.topology_type,
        "max_physical_qubits": hw.max_physical_qubits,
        "qec_architecture": hw.qec_architecture,
        "provenance": hw.provenance,
    }


def circuit_to_qasm(circuit: QuantumCircuit) -> str:
    """Best-effort OpenQASM 2 dump."""
    if hasattr(circuit, "qasm"):
        try:
            return circuit.qasm()
        except Exception:
            pass
    try:
        from qiskit.qasm2 import dumps

        return dumps(circuit)
    except Exception:
        return ""


def available_workload_ids() -> List[str]:
    return sorted(set(get_benchmark_workloads().keys()) | set(WORKLOAD_ALIASES.keys()) | {"bell", "ghz"})
