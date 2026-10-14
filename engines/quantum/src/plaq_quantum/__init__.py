"""
Plaq-Quantum Engine
Fault-tolerant quantum execution planner and cross-layer co-design optimization engine.
"""

from __future__ import annotations

__version__ = "0.3.0"

# Submodule exports
from . import circuits
from . import hardware
from . import cost_model
from . import stim_bridge
from . import optimizer
from . import baselines
from . import search_algorithms
from . import benchmark

from .circuits import (
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
)

from .hardware import (
    HardwareModel,
    DEMO_HARDWARE,
    SUPERCONDUCTING_HERON,
    TRAPPED_ION_FORTE,
    TRAPPED_ION_QUANTINUUM,
    NEUTRAL_ATOM_AQUILA,
    NEUTRAL_ATOM_QUERA,
    QLDPC_BIVARIATE_BICYCLE,
    HARDWARE_CATALOG,
    get_hardware_profile,
)

from .cost_model import (
    CircuitMetrics,
    CostEstimationResult,
    CodeDistanceResult,
    synthesize_rotation_t_count,
    extract_circuit_metrics,
    solve_minimum_code_distance,
    evaluate_fault_tolerant_cost,
)

from .stim_bridge import (
    ThresholdSampleResult,
    wilson_score_interval,
    SurfaceCodeStabilizerSimulator,
    StimSurfaceCodeSimulator,
    run_surface_code_simulation,
    run_threshold_study,
)

from .optimizer import (
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

from .baselines import (
    BaselineComparisonRecord,
    AblationRecord,
    run_four_baselines_protocol,
    run_ablation_study,
)

from .search_algorithms import (
    SearchBenchmarkResult,
    search_exhaustive,
    search_random,
    search_greedy,
    search_simulated_annealing,
    benchmark_search_methods,
)

from .benchmark import (
    run_compiler_baseline,
    run_full_benchmark_suite,
)

__all__ = [
    "__version__",
    # submodules
    "circuits",
    "hardware",
    "cost_model",
    "stim_bridge",
    "optimizer",
    "baselines",
    "search_algorithms",
    "benchmark",
    # circuits
    "make_test_circuit",
    "make_qaoa_circuit",
    "make_qft_circuit",
    "make_bernstein_vazirani_circuit",
    "make_random_clifford_t_circuit",
    "make_chemistry_ansatz_circuit",
    "make_chemistry_ansatz",
    "make_shor_modexp_circuit",
    "get_benchmark_workloads",
    "get_workload_manifest",
    "WORKLOAD_MANIFEST",
    # hardware
    "HardwareModel",
    "DEMO_HARDWARE",
    "SUPERCONDUCTING_HERON",
    "TRAPPED_ION_FORTE",
    "TRAPPED_ION_QUANTINUUM",
    "NEUTRAL_ATOM_AQUILA",
    "NEUTRAL_ATOM_QUERA",
    "QLDPC_BIVARIATE_BICYCLE",
    "HARDWARE_CATALOG",
    "get_hardware_profile",
    # cost_model
    "CircuitMetrics",
    "CostEstimationResult",
    "CodeDistanceResult",
    "synthesize_rotation_t_count",
    "extract_circuit_metrics",
    "solve_minimum_code_distance",
    "evaluate_fault_tolerant_cost",
    # stim_bridge
    "ThresholdSampleResult",
    "wilson_score_interval",
    "SurfaceCodeStabilizerSimulator",
    "StimSurfaceCodeSimulator",
    "run_surface_code_simulation",
    "run_threshold_study",
    # optimizer
    "ExecutionPlan",
    "EvaluatedPlan",
    "CompilationCache",
    "compute_compilation_fingerprint",
    "generate_candidate_space",
    "evaluate_plan",
    "extract_pareto_frontier",
    "filter_pareto_frontier",
    "search_pareto_optimizer",
    "compare_sequential_vs_joint",
    # baselines
    "BaselineComparisonRecord",
    "AblationRecord",
    "run_four_baselines_protocol",
    "run_ablation_study",
    # search_algorithms
    "SearchBenchmarkResult",
    "search_exhaustive",
    "search_random",
    "search_greedy",
    "search_simulated_annealing",
    "benchmark_search_methods",
    # benchmark
    "run_compiler_baseline",
    "run_full_benchmark_suite",
]
