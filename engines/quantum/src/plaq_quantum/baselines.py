"""
Q-Day OS Four-Baselines & Ablation Study Suite

Implements Section 8 & Section 9 of the research roadmap:
1. Four-Baselines Comparative Protocol:
   - Baseline 1: Original Circuit (Uncompiled raw gate structure)
   - Baseline 2: Standard Compiler Settings (Qiskit Level 3 default)
   - Baseline 3: Decoupled Resource Estimator (Microsoft QRE-style decoupled QEC allocation)
   - Baseline 4: Q-Day Joint Optimizer (Full cross-layer co-optimization)

2. Systematic Ablation Study:
   - Evaluates performance impact when individual optimization dimensions are removed:
     * Full Joint Optimizer
     * Without Decoder Co-Design (forced CPU decoder)
     * Without Factory Parallelism (forced 1 factory)
     * Without Routing / Layout Exploration (forced basic routing)
     * Without Code Distance Optimization (forced conservative code distance)
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd

try:
    from .hardware import HardwareModel, DEMO_HARDWARE
    from .cost_model import extract_circuit_metrics, evaluate_fault_tolerant_cost, CostEstimationResult
    from .optimizer import (
        ExecutionPlan,
        EvaluatedPlan,
        evaluate_plan,
        search_pareto_optimizer,
        CompilationCache,
    )
except (ImportError, ValueError):
    try:
        from plaq_quantum.hardware import HardwareModel, DEMO_HARDWARE
        from plaq_quantum.cost_model import extract_circuit_metrics, evaluate_fault_tolerant_cost, CostEstimationResult
        from plaq_quantum.optimizer import (
            ExecutionPlan,
            EvaluatedPlan,
            evaluate_plan,
            search_pareto_optimizer,
            CompilationCache,
        )
    except ImportError:
        from hardware import HardwareModel, DEMO_HARDWARE
        from cost_model import extract_circuit_metrics, evaluate_fault_tolerant_cost, CostEstimationResult
        from optimizer import (
            ExecutionPlan,
            EvaluatedPlan,
            evaluate_plan,
            search_pareto_optimizer,
            CompilationCache,
        )

try:
    from qiskit import QuantumCircuit
    HAS_QISKIT = True
except ImportError:
    HAS_QISKIT = False


@dataclass(frozen=True)
class BaselineComparisonRecord:
    """Record representing performance under one of the four established baselines."""
    baseline_id: str
    baseline_name: str
    description: str
    physical_qubits: int
    runtime_seconds: float
    code_distance: int
    failure_probability: float
    decoder_stall_factor: float
    total_cost_score: float
    relative_reduction_vs_original: float  # S = 1 - C / C_orig
    relative_reduction_vs_compiler: float  # S = 1 - C / C_compiler


@dataclass(frozen=True)
class AblationRecord:
    """Performance record representing an ablation test point."""
    configuration_name: str
    disabled_component: str
    physical_qubits: int
    runtime_seconds: float
    code_distance: int
    total_cost_score: float
    cost_penalty_percent: float  # % cost increase when this component is removed


def run_four_baselines_protocol(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    compilation_cache: Optional[CompilationCache] = None,
) -> List[BaselineComparisonRecord]:
    """
    Executes the 4-Baselines protocol defined in Section 9 of the startup plan:
    1. Original Circuit (uncompiled raw metrics)
    2. Standard Compiler Settings (Qiskit Opt 3 default)
    3. Existing Resource Estimator (Decoupled Microsoft QRE style)
    4. Q-Day Joint Optimizer
    """
    if compilation_cache is None:
        compilation_cache = CompilationCache()

    # Baseline 1: Original Uncompiled Circuit
    raw_metrics = extract_circuit_metrics(circuit)
    cost_b1 = evaluate_fault_tolerant_cost(
        metrics=raw_metrics,
        hardware=hardware,
        target_epsilon=target_epsilon,
        num_magic_factories=1,
        decoder_latency_ns=hardware.decoder_latency_ns_per_cycle,
    )
    c_b1 = cost_b1.total_cost_score

    # Baseline 2: Standard Compiler Settings (Qiskit Level 3 default)
    plan_b2 = ExecutionPlan(
        optimization_level=3,
        routing_method="basic",
        layout_method="trivial",
        num_magic_factories=1,
        code_distance_strategy="minimal_safe",
        decoder_architecture="distributed_cpu",
    )
    eval_b2 = evaluate_plan(circuit, hardware, plan_b2, target_epsilon, compilation_cache=compilation_cache)
    c_b2 = eval_b2.total_cost_score

    # Baseline 3: Existing Resource Estimator (Decoupled QEC Allocation, standard 2 factories, no decoder co-design)
    plan_b3 = ExecutionPlan(
        optimization_level=3,
        routing_method="basic",
        layout_method="trivial",
        num_magic_factories=2,
        code_distance_strategy="minimal_safe",
        decoder_architecture="distributed_cpu",
    )
    eval_b3 = evaluate_plan(circuit, hardware, plan_b3, target_epsilon, compilation_cache=compilation_cache)
    c_b3 = eval_b3.total_cost_score

    # Baseline 4: Q-Day Joint Optimizer
    all_evaluated, pareto_frontier = search_pareto_optimizer(
        circuit=circuit,
        hardware=hardware,
        target_epsilon=target_epsilon,
        compilation_cache=compilation_cache,
    )
    valid_plans = [p for p in all_evaluated if p.valid]
    best_b4 = min(valid_plans, key=lambda x: x.total_cost_score) if valid_plans else eval_b2
    c_b4 = best_b4.total_cost_score

    records: List[BaselineComparisonRecord] = [
        BaselineComparisonRecord(
            baseline_id="B1",
            baseline_name="Original Circuit",
            description="Uncompiled logical circuit structure; minimal error mitigation.",
            physical_qubits=cost_b1.physical_qubits,
            runtime_seconds=cost_b1.runtime_seconds,
            code_distance=cost_b1.code_distance,
            failure_probability=cost_b1.failure_probability,
            decoder_stall_factor=cost_b1.decoder_stall_factor,
            total_cost_score=c_b1,
            relative_reduction_vs_original=0.0,
            relative_reduction_vs_compiler=round((1.0 - c_b1 / c_b2) * 100, 2),
        ),
        BaselineComparisonRecord(
            baseline_id="B2",
            baseline_name="Standard Compiler Settings",
            description="Qiskit Level 3 transpilation with standard single-factory layout and CPU decoder.",
            physical_qubits=eval_b2.physical_qubits,
            runtime_seconds=eval_b2.runtime_seconds,
            code_distance=eval_b2.code_distance,
            failure_probability=eval_b2.failure_probability,
            decoder_stall_factor=eval_b2.cost_result.decoder_stall_factor,
            total_cost_score=c_b2,
            relative_reduction_vs_original=round((1.0 - c_b2 / c_b1) * 100, 2),
            relative_reduction_vs_compiler=0.0,
        ),
        BaselineComparisonRecord(
            baseline_id="B3",
            baseline_name="Decoupled Estimator Baseline (MS QRE Pattern)",
            description="Decoupled resource estimation pattern (inspired by Azure QRE decoupled workflow): fixed circuit transpilation with separate post-facto QEC allocation.",
            physical_qubits=eval_b3.physical_qubits,
            runtime_seconds=eval_b3.runtime_seconds,
            code_distance=eval_b3.code_distance,
            failure_probability=eval_b3.failure_probability,
            decoder_stall_factor=eval_b3.cost_result.decoder_stall_factor,
            total_cost_score=c_b3,
            relative_reduction_vs_original=round((1.0 - c_b3 / c_b1) * 100, 2),
            relative_reduction_vs_compiler=round((1.0 - c_b3 / c_b2) * 100, 2),
        ),
        BaselineComparisonRecord(
            baseline_id="B4",
            baseline_name="Plaq Joint Optimizer",
            description="Joint cross-layer co-optimization across transpilation, routing, factories, and decoder ASIC.",
            physical_qubits=best_b4.physical_qubits,
            runtime_seconds=best_b4.runtime_seconds,
            code_distance=best_b4.code_distance,
            failure_probability=best_b4.failure_probability,
            decoder_stall_factor=best_b4.cost_result.decoder_stall_factor,
            total_cost_score=c_b4,
            relative_reduction_vs_original=round((1.0 - c_b4 / c_b1) * 100, 2),
            relative_reduction_vs_compiler=round((1.0 - c_b4 / c_b2) * 100, 2),
        ),
    ]

    return records


def run_ablation_study(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    compilation_cache: Optional[CompilationCache] = None,
) -> List[AblationRecord]:
    """
    Executes systematic ablation experiments (Section 8 of prompt):
    Measures the exact cost penalty when key optimization components are disabled.
    """
    if compilation_cache is None:
        compilation_cache = CompilationCache()

    # Full Joint Optimizer
    all_evaluated, _ = search_pareto_optimizer(circuit, hardware, target_epsilon, compilation_cache=compilation_cache)
    valid_plans = [p for p in all_evaluated if p.valid]
    full_best = min(valid_plans, key=lambda x: x.total_cost_score) if valid_plans else None
    c_full = full_best.total_cost_score if full_best else 1.0

    # 1. Ablate Decoder Co-Design: force distributed CPU decoder (with backlog stall)
    abl_decoder = [p for p in valid_plans if p.plan.decoder_architecture == "distributed_cpu"]
    best_no_dec = min(abl_decoder, key=lambda x: x.total_cost_score) if abl_decoder else full_best

    # 2. Ablate Factory Parallelism: force single factory (f = 1)
    abl_factory = [p for p in valid_plans if p.plan.num_magic_factories == 1]
    best_no_fac = min(abl_factory, key=lambda x: x.total_cost_score) if abl_factory else full_best

    # 3. Ablate Routing Exploration: force basic linear routing only
    abl_routing = [p for p in valid_plans if p.plan.routing_method == "basic"]
    best_no_rout = min(abl_routing, key=lambda x: x.total_cost_score) if abl_routing else full_best

    # 4. Ablate Code Distance Optimization: force conservative distance offset
    abl_qec = [p for p in valid_plans if p.plan.code_distance_strategy == "conservative"]
    best_no_qec = min(abl_qec, key=lambda x: x.total_cost_score) if abl_qec else full_best

    ablations = [
        ("Full Joint Optimizer", "None (All dimensions active)", full_best),
        ("No Decoder Co-Design", "Disabled: Streaming ASIC/FPGA decoder (forced CPU)", best_no_dec),
        ("No Factory Scaling", "Disabled: Parallel magic state factories (forced f=1)", best_no_fac),
        ("No Routing Optimization", "Disabled: Sabre/Lookahead layout passes (forced basic)", best_no_rout),
        ("No QEC Distance Optimization", "Disabled: Minimal distance solver (forced conservative d+2)", best_no_qec),
    ]

    records: List[AblationRecord] = []
    for name, disabled_desc, plan_res in ablations:
        c_val = plan_res.total_cost_score if plan_res else c_full
        penalty = max(0.0, ((c_val - c_full) / c_full) * 100.0) if c_full > 0 else 0.0

        records.append(
            AblationRecord(
                configuration_name=name,
                disabled_component=disabled_desc,
                physical_qubits=plan_res.physical_qubits if plan_res else 0,
                runtime_seconds=round(plan_res.runtime_seconds, 6) if plan_res else 0.0,
                code_distance=plan_res.code_distance if plan_res else 0,
                total_cost_score=round(c_val, 4),
                cost_penalty_percent=round(penalty, 2),
            )
        )

    return records
