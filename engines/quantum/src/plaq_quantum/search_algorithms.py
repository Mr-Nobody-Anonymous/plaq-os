"""
Q-Day OS Search Algorithms Suite

Implements and benchmarks multiple optimization search strategies:
1. Exhaustive Grid Search (Ground Truth reference)
2. Greedy Optimization (Fast step-wise heuristic)
3. Random Uniform Search (Stochastic baseline)
4. Simulated Annealing (Combinatorial Metropolis-Hastings optimization)

Provides comparative benchmarking of search runtime, evaluation count,
regret relative to ground truth, and Pareto coverage.
"""

from __future__ import annotations
import math
import time
import random
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional

try:
    from .hardware import HardwareModel, DEMO_HARDWARE
    from .cost_model import CostEstimationResult
    from .optimizer import (
        ExecutionPlan,
        EvaluatedPlan,
        evaluate_plan,
        extract_pareto_frontier,
        generate_candidate_space,
        CompilationCache,
    )
except (ImportError, ValueError):
    try:
        from plaq_quantum.hardware import HardwareModel, DEMO_HARDWARE
        from plaq_quantum.cost_model import CostEstimationResult
        from plaq_quantum.optimizer import (
            ExecutionPlan,
            EvaluatedPlan,
            evaluate_plan,
            extract_pareto_frontier,
            generate_candidate_space,
            CompilationCache,
        )
    except ImportError:
        from hardware import HardwareModel, DEMO_HARDWARE
        from cost_model import CostEstimationResult
        from optimizer import (
            ExecutionPlan,
            EvaluatedPlan,
            evaluate_plan,
            extract_pareto_frontier,
            generate_candidate_space,
            CompilationCache,
        )

try:
    from qiskit import QuantumCircuit
    HAS_QISKIT = True
except ImportError:
    HAS_QISKIT = False


@dataclass(frozen=True)
class SearchBenchmarkResult:
    """Quantitative performance comparison for an optimization search strategy."""
    algorithm_name: str
    search_time_seconds: float
    total_evaluations: int
    best_cost_score: float
    best_physical_qubits: int
    best_runtime_seconds: float
    best_code_distance: int
    optimality_gap_percent: float  # Regret: (C - C_star) / C_star * 100%
    pareto_frontier_count: int
    pareto_coverage_percent: float  # % of true Pareto frontier points found
    best_plan: Dict[str, Any]


def search_exhaustive(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    compilation_cache: Optional[CompilationCache] = None,
) -> Tuple[List[EvaluatedPlan], float]:
    """Exhaustive search over full candidate space."""
    start_time = time.perf_counter()
    candidates = generate_candidate_space()
    if compilation_cache is None:
        compilation_cache = CompilationCache()

    evaluated: List[EvaluatedPlan] = []
    for plan in candidates:
        res = evaluate_plan(
            circuit=circuit,
            hardware=hardware,
            plan=plan,
            target_epsilon=target_epsilon,
            compilation_cache=compilation_cache,
        )
        evaluated.append(res)

    duration = time.perf_counter() - start_time
    return evaluated, duration


def search_random(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    max_evaluations: int = 35,
    seed: int = 42,
    compilation_cache: Optional[CompilationCache] = None,
) -> Tuple[List[EvaluatedPlan], float]:
    """Uniform random sampling across the candidate space."""
    start_time = time.perf_counter()
    candidates = generate_candidate_space()
    rng = random.Random(seed)

    sample_size = min(len(candidates), max_evaluations)
    sampled_candidates = rng.sample(candidates, sample_size)

    if compilation_cache is None:
        compilation_cache = CompilationCache()

    evaluated: List[EvaluatedPlan] = []
    for plan in sampled_candidates:
        res = evaluate_plan(
            circuit=circuit,
            hardware=hardware,
            plan=plan,
            target_epsilon=target_epsilon,
            compilation_cache=compilation_cache,
        )
        evaluated.append(res)

    duration = time.perf_counter() - start_time
    return evaluated, duration


def search_greedy(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    compilation_cache: Optional[CompilationCache] = None,
) -> Tuple[List[EvaluatedPlan], float]:
    """
    Greedy coordinate-descent search:
    Iteratively optimizes each parameter (opt_level -> routing -> factories -> decoder)
    keeping previous choices fixed.
    """
    start_time = time.perf_counter()
    if compilation_cache is None:
        compilation_cache = CompilationCache()

    evaluated: List[EvaluatedPlan] = []

    # Current baseline choice
    curr_opt = 2
    curr_routing = "basic"
    curr_layout = "trivial"
    curr_factories = 2
    curr_qec = "minimal_safe"
    curr_dec = "streaming_asic"

    # Stage 1: Optimize compiler level
    best_opt = curr_opt
    best_cost = float("inf")
    for opt in [0, 1, 2, 3]:
        plan = ExecutionPlan(
            optimization_level=opt,
            routing_method=curr_routing,
            layout_method="sabre" if curr_routing == "sabre" else "trivial",
            num_magic_factories=curr_factories,
            code_distance_strategy=curr_qec,
            decoder_architecture=curr_dec,
        )
        res = evaluate_plan(circuit, hardware, plan, target_epsilon, compilation_cache=compilation_cache)
        evaluated.append(res)
        if res.valid and res.total_cost_score < best_cost:
            best_cost = res.total_cost_score
            best_opt = opt

    curr_opt = best_opt

    # Stage 2: Optimize routing method
    best_routing = curr_routing
    for r_m in ["basic", "lookahead", "sabre"]:
        l_m = "sabre" if r_m == "sabre" else "dense"
        plan = ExecutionPlan(
            optimization_level=curr_opt,
            routing_method=r_m,
            layout_method=l_m,
            num_magic_factories=curr_factories,
            code_distance_strategy=curr_qec,
            decoder_architecture=curr_dec,
        )
        res = evaluate_plan(circuit, hardware, plan, target_epsilon, compilation_cache=compilation_cache)
        evaluated.append(res)
        if res.valid and res.total_cost_score < best_cost:
            best_cost = res.total_cost_score
            best_routing = r_m

    curr_routing = best_routing

    # Stage 3: Optimize factory parallelism
    best_factories = curr_factories
    for f in [1, 2, 4, 8]:
        plan = ExecutionPlan(
            optimization_level=curr_opt,
            routing_method=curr_routing,
            layout_method="sabre" if curr_routing == "sabre" else "dense",
            num_magic_factories=f,
            code_distance_strategy=curr_qec,
            decoder_architecture=curr_dec,
        )
        res = evaluate_plan(circuit, hardware, plan, target_epsilon, compilation_cache=compilation_cache)
        evaluated.append(res)
        if res.valid and res.total_cost_score < best_cost:
            best_cost = res.total_cost_score
            best_factories = f

    curr_factories = best_factories

    # Stage 4: Optimize classical decoder architecture
    for dec in ["streaming_asic", "embedded_fpga", "distributed_cpu"]:
        plan = ExecutionPlan(
            optimization_level=curr_opt,
            routing_method=curr_routing,
            layout_method="sabre" if curr_routing == "sabre" else "dense",
            num_magic_factories=curr_factories,
            code_distance_strategy=curr_qec,
            decoder_architecture=dec,
        )
        res = evaluate_plan(circuit, hardware, plan, target_epsilon, compilation_cache=compilation_cache)
        evaluated.append(res)

    duration = time.perf_counter() - start_time
    return evaluated, duration


def search_simulated_annealing(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    initial_temp: float = 1000.0,
    cooling_rate: float = 0.90,
    iterations: int = 40,
    seed: int = 42,
    compilation_cache: Optional[CompilationCache] = None,
) -> Tuple[List[EvaluatedPlan], float]:
    """
    Combinatorial Simulated Annealing with Metropolis-Hastings acceptance.
    """
    start_time = time.perf_counter()
    rng = random.Random(seed)
    if compilation_cache is None:
        compilation_cache = CompilationCache()

    opt_choices = [0, 1, 2, 3]
    routing_choices = ["basic", "lookahead", "sabre"]
    factory_choices = [1, 2, 4, 8]
    qec_choices = ["minimal_safe", "conservative"]
    decoder_choices = ["streaming_asic", "embedded_fpga", "distributed_cpu"]

    # Initial random state
    current_plan = ExecutionPlan(
        optimization_level=rng.choice(opt_choices),
        routing_method=rng.choice(routing_choices),
        layout_method="sabre",
        num_magic_factories=rng.choice(factory_choices),
        code_distance_strategy=rng.choice(qec_choices),
        decoder_architecture=rng.choice(decoder_choices),
    )

    current_eval = evaluate_plan(circuit, hardware, current_plan, target_epsilon, compilation_cache=compilation_cache)
    evaluated: List[EvaluatedPlan] = [current_eval]

    best_eval = current_eval
    temp = initial_temp

    for _ in range(iterations):
        # Mutate one parameter randomly
        mutation_type = rng.choice(["opt", "routing", "factory", "qec", "decoder"])
        new_opt = current_plan.optimization_level
        new_routing = current_plan.routing_method
        new_factory = current_plan.num_magic_factories
        new_qec = current_plan.code_distance_strategy
        new_decoder = current_plan.decoder_architecture

        if mutation_type == "opt":
            new_opt = rng.choice(opt_choices)
        elif mutation_type == "routing":
            new_routing = rng.choice(routing_choices)
        elif mutation_type == "factory":
            new_factory = rng.choice(factory_choices)
        elif mutation_type == "qec":
            new_qec = rng.choice(qec_choices)
        elif mutation_type == "decoder":
            new_decoder = rng.choice(decoder_choices)

        new_plan = ExecutionPlan(
            optimization_level=new_opt,
            routing_method=new_routing,
            layout_method="sabre" if new_routing == "sabre" else "dense",
            num_magic_factories=new_factory,
            code_distance_strategy=new_qec,
            decoder_architecture=new_decoder,
        )

        candidate_eval = evaluate_plan(circuit, hardware, new_plan, target_epsilon, compilation_cache=compilation_cache)
        evaluated.append(candidate_eval)

        # Cost delta
        c_curr = current_eval.total_cost_score if current_eval.valid else 1e9
        c_cand = candidate_eval.total_cost_score if candidate_eval.valid else 1e9
        delta = c_cand - c_curr

        # Metropolis-Hastings acceptance
        if delta < 0 or (temp > 1e-4 and rng.random() < math.exp(-delta / temp)):
            current_plan = new_plan
            current_eval = candidate_eval

            if candidate_eval.valid and candidate_eval.total_cost_score < (best_eval.total_cost_score if best_eval.valid else 1e9):
                best_eval = candidate_eval

        temp *= cooling_rate

    duration = time.perf_counter() - start_time
    return evaluated, duration


def benchmark_search_methods(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    compilation_cache: Optional[CompilationCache] = None,
) -> List[SearchBenchmarkResult]:
    """
    Executes and benchmarks all search algorithms (Exhaustive, Greedy, Random, Annealing)
    relative to true exhaustive ground truth.
    """
    if compilation_cache is None:
        compilation_cache = CompilationCache()

    # 1. Ground Truth: Exhaustive
    ex_evals, ex_time = search_exhaustive(circuit, hardware, target_epsilon, compilation_cache)
    ex_valid = [p for p in ex_evals if p.valid]
    ex_best = min(ex_valid, key=lambda x: x.total_cost_score) if ex_valid else None
    c_star = ex_best.total_cost_score if ex_best else 1.0
    true_pareto = extract_pareto_frontier(ex_evals)
    true_pareto_tuples = {(p.physical_qubits, round(p.runtime_seconds, 6)) for p in true_pareto}

    methods = [
        ("Exhaustive Search", search_exhaustive, {}),
        ("Greedy Optimization", search_greedy, {}),
        ("Simulated Annealing", search_simulated_annealing, {"iterations": 35}),
        ("Random Search (N=35)", search_random, {"max_evaluations": 35}),
    ]

    results: List[SearchBenchmarkResult] = []

    for name, func, kwargs in methods:
        # Use an isolated fresh cache to prevent cache-hit bias across benchmarked methods
        isolated_cache = CompilationCache()
        evals, duration = func(circuit, hardware, target_epsilon, compilation_cache=isolated_cache, **kwargs)
        valid_plans = [p for p in evals if p.valid]
        best_p = min(valid_plans, key=lambda x: x.total_cost_score) if valid_plans else None

        best_cost = best_p.total_cost_score if best_p else float("inf")
        gap = max(0.0, ((best_cost - c_star) / c_star) * 100.0) if c_star > 0 else 0.0

        method_pareto = extract_pareto_frontier(evals)
        method_pareto_tuples = {(p.physical_qubits, round(p.runtime_seconds, 6)) for p in method_pareto}

        # Pareto coverage: what fraction of true non-dominated frontier was captured?
        if true_pareto_tuples:
            overlap = len(method_pareto_tuples.intersection(true_pareto_tuples))
            coverage = (overlap / len(true_pareto_tuples)) * 100.0
        else:
            coverage = 100.0

        results.append(
            SearchBenchmarkResult(
                algorithm_name=name,
                search_time_seconds=round(duration, 4),
                total_evaluations=len(evals),
                best_cost_score=round(best_cost, 4),
                best_physical_qubits=best_p.physical_qubits if best_p else 0,
                best_runtime_seconds=round(best_p.runtime_seconds, 6) if best_p else 0.0,
                best_code_distance=best_p.code_distance if best_p else 0,
                optimality_gap_percent=round(gap, 2),
                pareto_frontier_count=len(method_pareto),
                pareto_coverage_percent=round(coverage, 2),
                best_plan=best_p.plan.to_dict() if best_p else {},
            )
        )

    return results
