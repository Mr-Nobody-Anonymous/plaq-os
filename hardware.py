"""
Q-Day OS Hardware Specifications & Models

Defines realistic quantum processor models across Superconducting,
Trapped Ion, Neutral Atom, and Quantum LDPC architectures, capturing gate errors,
coherence times (T1, T2), operation latencies, surface code cycle times, and connectivity graphs.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import math


@dataclass(frozen=True)
class HardwareModel:
    """
    Representation of target quantum hardware architecture, coherence properties,
    and physical noise characteristics.
    """
    name: str
    technology: str  # 'superconducting', 'trapped_ion', 'neutral_atom', 'qldpc'
    single_qubit_error: float
    two_qubit_error: float
    measurement_error: float
    single_qubit_time_ns: float
    two_qubit_time_ns: float
    measurement_time_ns: float
    surface_code_cycle_time_ns: float  # Time required for one round of stabilizer syndrome extraction
    t1_relaxation_us: float = 120.0    # T1 relaxation time in microseconds
    t2_dephasing_us: float = 90.0      # T2 dephasing time in microseconds
    crosstalk_penalty: float = 1.15    # Multiplier on error rate under concurrent execution
    surface_code_threshold: float = 0.01  # Typical threshold p_th ~ 1% for standard surface code
    decoder_latency_ns_per_cycle: float = 500.0  # Classical decoding latency per cycle
    max_physical_qubits: int = 250_000
    basis_gates: tuple = ("rz", "sx", "x", "cx")
    topology_type: str = "grid"  # 'linear', 'grid', 'heavy_hex', 'all_to_all', 'bivariate_bicycle'

    def get_coupling_edges(self, num_qubits: int) -> List[Tuple[int, int]]:
        """
        Generate directed coupling graph edges for the specified number of qubits.
        Bidirectional coupling is represented by (u, v) and (v, u).
        """
        edges: List[Tuple[int, int]] = []
        if self.topology_type == "linear":
            for i in range(num_qubits - 1):
                edges.append((i, i + 1))
                edges.append((i + 1, i))
        elif self.topology_type == "all_to_all":
            for i in range(num_qubits):
                for j in range(num_qubits):
                    if i != j:
                        edges.append((i, j))
        elif self.topology_type in ("grid", "bivariate_bicycle"):
            cols = math.ceil(math.sqrt(num_qubits))
            rows = math.ceil(num_qubits / cols)
            for r in range(rows):
                for c in range(cols):
                    idx = r * cols + c
                    if idx >= num_qubits:
                        continue
                    if c + 1 < cols and (idx + 1) < num_qubits:
                        edges.append((idx, idx + 1))
                        edges.append((idx + 1, idx))
                    if r + 1 < rows and (idx + cols) < num_qubits:
                        edges.append((idx, idx + cols))
                        edges.append((idx + cols, idx))
            # If bivariate bicycle qLDPC, add long-range periodic torus couplers
            if self.topology_type == "bivariate_bicycle":
                for r in range(rows):
                    start = r * cols
                    end = min(num_qubits - 1, start + cols - 1)
                    if start < end:
                        edges.append((start, end))
                        edges.append((end, start))
        elif self.topology_type == "heavy_hex":
            cols = math.ceil(math.sqrt(num_qubits))
            for i in range(num_qubits - 1):
                edges.append((i, i + 1))
                edges.append((i + 1, i))
            step = max(2, cols)
            for i in range(0, num_qubits - step, 2):
                if i + step < num_qubits:
                    edges.append((i, i + step))
                    edges.append((i + step, i))
        else:
            for i in range(num_qubits - 1):
                edges.append((i, i + 1))
                edges.append((i + 1, i))
        return edges

    def to_dict(self) -> Dict[str, Any]:
        """Serialize hardware specification."""
        return {
            "name": self.name,
            "technology": self.technology,
            "single_qubit_error": self.single_qubit_error,
            "two_qubit_error": self.two_qubit_error,
            "measurement_error": self.measurement_error,
            "single_qubit_time_ns": self.single_qubit_time_ns,
            "two_qubit_time_ns": self.two_qubit_time_ns,
            "measurement_time_ns": self.measurement_time_ns,
            "surface_code_cycle_time_ns": self.surface_code_cycle_time_ns,
            "t1_relaxation_us": self.t1_relaxation_us,
            "t2_dephasing_us": self.t2_dephasing_us,
            "surface_code_threshold": self.surface_code_threshold,
            "decoder_latency_ns_per_cycle": self.decoder_latency_ns_per_cycle,
            "max_physical_qubits": self.max_physical_qubits,
            "basis_gates": list(self.basis_gates),
            "topology_type": self.topology_type,
        }


# Reference industrial models based on published benchmarks

DEMO_HARDWARE = HardwareModel(
    name="demo-illustrative",
    technology="superconducting",
    single_qubit_error=1e-4,
    two_qubit_error=1e-3,
    measurement_error=1e-3,
    single_qubit_time_ns=30.0,
    two_qubit_time_ns=200.0,
    measurement_time_ns=500.0,
    surface_code_cycle_time_ns=1000.0,
    t1_relaxation_us=100.0,
    t2_dephasing_us=80.0,
    surface_code_threshold=0.01,
    decoder_latency_ns_per_cycle=400.0,
    max_physical_qubits=50_000,
    topology_type="linear",
)

SUPERCONDUCTING_HERON = HardwareModel(
    name="ibm-heron-like-superconducting",
    technology="superconducting",
    single_qubit_error=1.5e-4,
    two_qubit_error=1.2e-3,
    measurement_error=8e-4,
    single_qubit_time_ns=25.0,
    two_qubit_time_ns=180.0,
    measurement_time_ns=450.0,
    surface_code_cycle_time_ns=1000.0,  # 1.0 us
    t1_relaxation_us=150.0,
    t2_dephasing_us=110.0,
    surface_code_threshold=0.01,
    decoder_latency_ns_per_cycle=950.0,  # High decoder throughput pressure
    max_physical_qubits=250_000,
    topology_type="heavy_hex",
)

TRAPPED_ION_FORTE = HardwareModel(
    name="trapped-ion-high-fidelity",
    technology="trapped_ion",
    single_qubit_error=1.0e-5,
    two_qubit_error=1.0e-4,
    measurement_error=3.0e-4,
    single_qubit_time_ns=10_000.0,
    two_qubit_time_ns=150_000.0,
    measurement_time_ns=100_000.0,
    surface_code_cycle_time_ns=150_000.0,
    t1_relaxation_us=10_000_000.0,  # > 10 seconds
    t2_dephasing_us=1_000_000.0,    # > 1 second
    surface_code_threshold=0.015,
    decoder_latency_ns_per_cycle=10_000.0,
    max_physical_qubits=10_000,
    topology_type="all_to_all",
)

NEUTRAL_ATOM_AQUILA = HardwareModel(
    name="neutral-atom-grid",
    technology="neutral_atom",
    single_qubit_error=5.0e-5,
    two_qubit_error=5.0e-4,
    measurement_error=5.0e-4,
    single_qubit_time_ns=500.0,
    two_qubit_time_ns=2_000.0,
    measurement_time_ns=5_000.0,
    surface_code_cycle_time_ns=20_000.0,
    t1_relaxation_us=500_000.0,
    t2_dephasing_us=100_000.0,
    surface_code_threshold=0.012,
    decoder_latency_ns_per_cycle=3_000.0,
    max_physical_qubits=100_000,
    topology_type="grid",
)

QLDPC_BIVARIATE_BICYCLE = HardwareModel(
    name="ibm-qldpc-bivariate-bicycle",
    technology="qldpc",
    single_qubit_error=1.0e-4,
    two_qubit_error=8.0e-4,
    measurement_error=6.0e-4,
    single_qubit_time_ns=25.0,
    two_qubit_time_ns=180.0,
    measurement_time_ns=400.0,
    surface_code_cycle_time_ns=1200.0,
    t1_relaxation_us=180.0,
    t2_dephasing_us=130.0,
    surface_code_threshold=0.008,
    decoder_latency_ns_per_cycle=800.0,
    max_physical_qubits=500_000,
    topology_type="bivariate_bicycle",
)

HARDWARE_CATALOG: Dict[str, HardwareModel] = {
    "demo": DEMO_HARDWARE,
    "superconducting": SUPERCONDUCTING_HERON,
    "trapped_ion": TRAPPED_ION_FORTE,
    "neutral_atom": NEUTRAL_ATOM_AQUILA,
    "qldpc": QLDPC_BIVARIATE_BICYCLE,
}
