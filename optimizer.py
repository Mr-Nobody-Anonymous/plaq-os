"""
Root-level backward compatibility shim for plaq_quantum.optimizer.
Re-exports Pareto optimization, compilation cache, and search procedures.
"""

from __future__ import annotations
import plaq_bootstrap  # noqa: F401
from plaq_quantum.optimizer import *
from plaq_quantum.optimizer import (
    ExecutionPlan,
    EvaluatedPlan,
    CompilationCache,
    compute_compilation_fingerprint,
    generate_candidate_space,
    evaluate_plan,
    extract_pareto_frontier,
    filter_pareto_frontier,
    search_pareto_optimizer,
    compare_sequential_vs_joint,
)
