"""
Root-level backward compatibility shim for plaq_quantum.cost_model.
Re-exports fault-tolerant cost models, distance solvers, and synthesis functions.
"""

from __future__ import annotations
import plaq_bootstrap  # noqa: F401
from plaq_quantum.cost_model import *
from plaq_quantum.cost_model import (
    CircuitMetrics,
    CostEstimationResult,
    CodeDistanceResult,
    synthesize_rotation_t_count,
    extract_circuit_metrics,
    solve_minimum_code_distance,
    evaluate_fault_tolerant_cost,
    HAS_QISKIT,
)
