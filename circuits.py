"""
Root-level backward compatibility shim for plaq_quantum.circuits.
Re-exports all circuit generators, workload definitions, and manifests.
"""

from __future__ import annotations
import plaq_bootstrap  # noqa: F401
from plaq_quantum.circuits import *
from plaq_quantum.circuits import (
    make_test_circuit,
    make_qaoa_circuit,
    make_qft_circuit,
    make_bernstein_vazirani_circuit,
    make_random_clifford_t_circuit,
    make_chemistry_ansatz_circuit,
    make_chemistry_ansatz,
    make_shor_modexp_circuit,
    get_benchmark_workloads,
    get_workload_manifest,
    WORKLOAD_MANIFEST,
    HAS_QISKIT,
)
