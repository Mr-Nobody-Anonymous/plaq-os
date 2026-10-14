"""
Q-Day OS Joint Cross-Layer Quantum Execution Optimizer

Searches for Pareto-optimal execution plans across:
1. Compiler optimization levels (0, 1, 2, 3)
2. Routing & layout passes (sabre, lookahead, basic)
3. Magic state factory parallelization (1, 2, 4, 8)
4. Surface code & qLDPC distance strategies (minimal safe, conservative)
5. Classical decoder architectures (streaming ASIC, FPGA, distributed CPU)

Extracts multi-objective Pareto frontiers (Physical Qubits vs Wall-Clock Runtime vs Failure Probability).
Features compilation caching for ultra-fast, scalable parameter space exploration.
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional, Set
import pandas as pd

try:
    from .hardware import HardwareModel, DEMO_HARDWARE
    from .cost_model import (
        extract_circuit_metrics,
        evaluate_fault_tolerant_cost,
        CostEstimationResult,
        CircuitMetrics,
    )
except (ImportError, ValueError):
    try:
        from plaq_quantum.hardware import HardwareModel, DEMO_HARDWARE
        from plaq_quantum.cost_model import (
            extract_circuit_metrics,
            evaluate_fault_tolerant_cost,
            CostEstimationResult,
            CircuitMetrics,
        )
    except ImportError:
        from hardware import HardwareModel, DEMO_HARDWARE
        from cost_model import (
            extract_circuit_metrics,
            evaluate_fault_tolerant_cost,
            CostEstimationResult,
            CircuitMetrics,
        )

try:
    from qiskit import transpile, QuantumCircuit
    from qiskit.transpiler import CouplingMap
    HAS_QISKIT = True
except ImportError:
    HAS_QISKIT = False


@dataclass(frozen=True)
class ExecutionPlan:
    """Candidate fault-tolerant execution configuration."""
    optimization_level: int
    routing_method: str  # 'sabre', 'lookahead', 'basic'
    layout_method: str   # 'sabre', 'dense', 'trivial'
    num_magic_factories: int
    code_distance_strategy: str  # 'minimal_safe', 'conservative'
    decoder_architecture: str    # 'streaming_asic', 'embedded_fpga', 'distributed_cpu'
    code_family: str = "surface_code_rotated"  # 'surface_code_rotated', 'qldpc'
    transpiler_seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opt_level": self.optimization_level,
            "routing": self.routing_method,
            "layout": self.layout_method,
            "factories": self.num_magic_factories,
            "qec_strategy": self.code_distance_strategy,
            "decoder": self.decoder_architecture,
            "code_family": self.code_family,
        }


@dataclass(frozen=True)
class EvaluatedPlan:
    """Evaluated execution plan with physical performance figures."""
    plan: ExecutionPlan
    cost_result: CostEstimationResult
    physical_qubits: int
    runtime_seconds: float
    failure_probability: float
    code_distance: int
    total_cost_score: float
    valid: bool
    is_pareto_optimal: bool = False

    def to_row(self) -> Dict[str, Any]:
        return {
            "opt_level": self.plan.optimization_level,
            "routing": self.plan.routing_method,
            "layout": self.plan.layout_method,
            "factories": self.plan.num_magic_factories,
            "qec_strategy": self.plan.code_distance_strategy,
            "decoder": self.plan.decoder_architecture,
            "code_family": self.plan.code_family,
            "valid": self.valid,
            "physical_qubits": self.physical_qubits,
            "runtime_s": round(self.runtime_seconds, 6),
            "failure_prob": self.failure_probability,
            "code_distance": self.code_distance,
            "total_cost": round(self.total_cost_score, 4),
            "pareto": self.is_pareto_optimal,
        }


DECODER_LATENCY_SPECS: Dict[str, float] = {
    "streaming_asic": 80.0,     # Ultra-fast real-time custom ASIC
    "embedded_fpga": 350.0,     # Low-latency cryogenic/warm FPGA decoder
    "distributed_cpu": 1200.0,  # Standard networked CPU (causes cycle stall)
}


import hashlib

def compute_compilation_fingerprint(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    opt_level: int,
    routing_method: str,
    layout_method: str,
    seed: int,
) -> str:
    """
    Generate cryptographically unique SHA-256 canonical fingerprint for a compilation pass.
    Includes ordered gates, parameter floats, qubit registers, coupling graph, and compiler seed.
    """
    hasher = hashlib.sha256()
    hasher.update(f":qubits={circuit.num_qubits}:clbits={circuit.num_clbits}:".encode("utf-8"))
    for inst in circuit.data:
        op = inst.operation
        q_indices = [circuit.find_bit(q).index for q in inst.qubits]
        c_indices = [circuit.find_bit(c).index for c in inst.clbits]
        params_str = ",".join(
            f"{float(p):.8f}" if isinstance(p, (int, float)) else str(p)
            for p in op.params
        )
        cl_str = f"->{','.join(map(str, c_indices))}" if c_indices else ""
        hasher.update(f"{op.name}[{','.join(map(str, q_indices))}{cl_str}]:{params_str};".encode("utf-8"))

    edges_str = str(sorted(hardware.get_coupling_edges(circuit.num_qubits)))
    basis_str = ",".join(sorted(hardware.basis_gates)) if hardware.basis_gates else ""
    hasher.update(f":hw={hardware.name}:{edges_str}:basis={basis_str}:".encode("utf-8"))
    hasher.update(f":opt={opt_level}:rout={routing_method}:lay={layout_method}:seed={seed}:".encode("utf-8"))
    try:
        import qiskit
        hasher.update(f"qiskit={qiskit.__version__}".encode("utf-8"))
    except Exception:
        pass
    return hasher.hexdigest()


class CompilationCache:
    """
    Caches compiled circuit metrics using canonical SHA-256 fingerprints
    to avoid redundant transpilation passes while preventing cache collisions.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Optional[CircuitMetrics]] = {}
        self.last_errors: Dict[str, str] = {}

    def get_or_compile(
        self,
        circuit: QuantumCircuit,
        hardware: HardwareModel,
        opt_level: int,
        routing_method: str,
        layout_method: str,
        seed: int = 42,
    ) -> Optional[CircuitMetrics]:
        key = compute_compilation_fingerprint(
            circuit=circuit,
            hardware=hardware,
            opt_level=opt_level,
            routing_method=routing_method,
            layout_method=layout_method,
            seed=seed,
        )
        if key in self._cache:
            return self._cache[key]

        edges = hardware.get_coupling_edges(circuit.num_qubits)
        coupling_map = CouplingMap(edges)

        try:
            compiled = transpile(
                circuit,
                coupling_map=coupling_map,
                basis_gates=list(hardware.basis_gates),
                optimization_level=opt_level,
                routing_method=routing_method,
                layout_method=layout_method,
                seed_transpiler=seed,
            )
            metrics = extract_circuit_metrics(compiled)
            self._cache[key] = metrics
            return metrics
        except Exception as exc:
            self.last_errors[key] = f"{type(exc).__name__}: {str(exc)}"
            self._cache[key] = None
            return None


def evaluate_plan(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    plan: ExecutionPlan,
    target_epsilon: float = 1e-3,
    weight_qubits: float = 1.0,
    weight_time: float = 500.0,
    compilation_cache: Optional[CompilationCache] = None,
) -> EvaluatedPlan:
    """Evaluate a candidate execution plan under target hardware and error budget."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to compile and evaluate candidate plans.")

    if compilation_cache is None:
        compilation_cache = CompilationCache()

    metrics = compilation_cache.get_or_compile(
        circuit=circuit,
        hardware=hardware,
        opt_level=plan.optimization_level,
        routing_method=plan.routing_method,
        layout_method=plan.layout_method,
        seed=plan.transpiler_seed,
    )

    if metrics is None:
        dummy_result = CostEstimationResult(
            valid=False,
            feasibility_reason="Compilation failed with given routing/layout options.",
            physical_qubits=999_999,
            runtime_seconds=999.0,
            failure_probability=1.0,
            code_distance=0,
            factory_code_distance=0,
            num_factories=plan.num_magic_factories,
            data_physical_qubits=0,
            factory_physical_qubits=0,
            total_surface_code_cycles=0,
            decoder_stall_factor=1.0,
            spacetime_volume=0,
            total_cost_score=float("inf"),
            assumptions={},
            diagnostics=["Compilation failed with given routing/layout options."],
        )
        return EvaluatedPlan(
            plan=plan,
            cost_result=dummy_result,
            physical_qubits=999_999,
            runtime_seconds=999.0,
            failure_probability=1.0,
            code_distance=0,
            total_cost_score=float("inf"),
            valid=False,
        )

    d_offset = 0 if plan.code_distance_strategy == "minimal_safe" else 2
    decoder_latency = DECODER_LATENCY_SPECS.get(plan.decoder_architecture, hardware.decoder_latency_ns_per_cycle)

    cost_result = evaluate_fault_tolerant_cost(
        metrics=metrics,
        hardware=hardware,
        target_epsilon=target_epsilon,
        num_magic_factories=plan.num_magic_factories,
        code_family=plan.code_family,
        decoder_latency_ns=decoder_latency,
        weight_qubits=weight_qubits,
        weight_time=weight_time,
    )

    if d_offset > 0 and cost_result.valid:
        new_d = cost_result.code_distance + d_offset
        cost_result = evaluate_fault_tolerant_cost(
            metrics=metrics,
            hardware=hardware,
            target_epsilon=target_epsilon,
            num_magic_factories=plan.num_magic_factories,
            code_family=plan.code_family,
            code_distance_override=new_d,
            decoder_latency_ns=decoder_latency,
            weight_qubits=weight_qubits,
            weight_time=weight_time,
        )

    return EvaluatedPlan(
        plan=plan,
        cost_result=cost_result,
        physical_qubits=cost_result.physical_qubits,
        runtime_seconds=cost_result.runtime_seconds,
        failure_probability=cost_result.failure_probability,
        code_distance=cost_result.code_distance,
        total_cost_score=cost_result.total_cost_score,
        valid=cost_result.valid,
    )


def extract_pareto_frontier(evaluated_plans: List[EvaluatedPlan]) -> List[EvaluatedPlan]:
    """
    Extract the multi-objective Pareto frontier among valid plans.
    A candidate plan is dominated if there exists another plan that is
    <= in physical qubits, <= in runtime, <= in failure probability,
    and strictly < in at least one of these three metrics.
    """
    valid_plans = [p for p in evaluated_plans if p.valid]
    if not valid_plans:
        return []

    pareto_set: List[EvaluatedPlan] = []

    for candidate in valid_plans:
        is_dominated = False
        for other in valid_plans:
            if candidate is other:
                continue

            better_or_equal = (
                other.physical_qubits <= candidate.physical_qubits and
                other.runtime_seconds <= candidate.runtime_seconds and
                other.failure_probability <= candidate.failure_probability
            )
            strictly_better = (
                other.physical_qubits < candidate.physical_qubits or
                other.runtime_seconds < candidate.runtime_seconds or
                other.failure_probability < candidate.failure_probability
            )

            if better_or_equal and strictly_better:
                is_dominated = True
                break

        if not is_dominated:
            pareto_set.append(
                EvaluatedPlan(
                    plan=candidate.plan,
                    cost_result=candidate.cost_result,
                    physical_qubits=candidate.physical_qubits,
                    runtime_seconds=candidate.runtime_seconds,
                    failure_probability=candidate.failure_probability,
                    code_distance=candidate.code_distance,
                    total_cost_score=candidate.total_cost_score,
                    valid=True,
                    is_pareto_optimal=True,
                )
            )

    return pareto_set


def filter_pareto_frontier(candidates: List[Any]) -> List[Any]:
    """Filter candidate plans or evaluations to extract the non-dominated Pareto frontier."""
    if not candidates:
        return []
    if isinstance(candidates[0], EvaluatedPlan):
        return extract_pareto_frontier(candidates)
    return candidates


def generate_candidate_space(
    *args: Any,
    opt_levels: Optional[List[int]] = None,
    routing_methods: Optional[List[str]] = None,
    factories: Optional[List[int]] = None,
    qec_strategies: Optional[List[str]] = None,
    decoders: Optional[List[str]] = None,
    code_families: Optional[List[str]] = None,
    **kwargs: Any,
) -> List[Any]:
    """Generate combinatorial grid of candidate execution plans or evaluated candidates."""
    circuit = None
    hardware = None
    if len(args) >= 1:
        circuit = args[0]
    if len(args) >= 2:
        hardware = args[1]
    if "circuit" in kwargs:
        circuit = kwargs["circuit"]
    if "backend" in kwargs:
        hardware = kwargs["backend"]
    elif "hardware" in kwargs:
        hardware = kwargs["hardware"]

    levels = opt_levels or ([0, 1] if circuit is not None else [0, 1, 2, 3])
    routings = routing_methods or (["basic"] if circuit is not None else ["basic", "lookahead", "sabre"])
    factory_counts = factories or ([1, 2] if circuit is not None else [1, 2, 4, 8])
    qec_opts = qec_strategies or ["minimal_safe", "conservative"]
    decoder_opts = decoders or (["streaming_asic"] if circuit is not None else ["streaming_asic", "embedded_fpga", "distributed_cpu"])
    families = code_families or ["surface_code_rotated"]

    candidates: List[ExecutionPlan] = []
    for opt in levels:
        for r_m in routings:
            l_m = "sabre" if r_m == "sabre" else ("dense" if opt > 1 else "trivial")
            for f in factory_counts:
                for qec in qec_opts:
                    for dec in decoder_opts:
                        for fam in families:
                            candidates.append(
                                ExecutionPlan(
                                    optimization_level=opt,
                                    routing_method=r_m,
                                    layout_method=l_m,
                                    num_magic_factories=f,
                                    code_distance_strategy=qec,
                                    decoder_architecture=dec,
                                    code_family=fam,
                                )
                            )

    if circuit is not None and hardware is not None:
        evaluated: List[EvaluatedPlan] = []
        cache = CompilationCache()
        for plan in candidates:
            res = evaluate_plan(circuit, hardware, plan, compilation_cache=cache)
            if res.valid:
                evaluated.append(res)
        return evaluated if evaluated else candidates

    return candidates


def search_pareto_optimizer(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    candidate_limit: Optional[int] = None,
    compilation_cache: Optional[CompilationCache] = None,
) -> Tuple[List[EvaluatedPlan], List[EvaluatedPlan]]:
    """Searches candidate execution space and extracts the Pareto frontier."""
    candidates = generate_candidate_space()
    if candidate_limit and candidate_limit < len(candidates):
        random.seed(42)
        candidates = random.sample(candidates, candidate_limit)

    if compilation_cache is None:
        compilation_cache = CompilationCache()

    evaluated_plans: List[EvaluatedPlan] = []
    for plan in candidates:
        eval_res = evaluate_plan(
            circuit=circuit,
            hardware=hardware,
            plan=plan,
            target_epsilon=target_epsilon,
            compilation_cache=compilation_cache,
        )
        evaluated_plans.append(eval_res)

    pareto_frontier = extract_pareto_frontier(evaluated_plans)
    return evaluated_plans, pareto_frontier


def compare_sequential_vs_joint(
    circuit: QuantumCircuit,
    hardware: HardwareModel,
    target_epsilon: float = 1e-3,
    compilation_cache: Optional[CompilationCache] = None,
) -> Dict[str, Any]:
    """Compares the standard Sequential Pipeline against Q-Day OS Joint Optimizer."""
    if compilation_cache is None:
        compilation_cache = CompilationCache()

    # 1. Sequential Baseline
    sequential_plan = ExecutionPlan(
        optimization_level=3,
        routing_method="basic",
        layout_method="trivial",
        num_magic_factories=1,
        code_distance_strategy="minimal_safe",
        decoder_architecture="distributed_cpu",
        code_family="surface_code_rotated",
    )
    seq_eval = evaluate_plan(
        circuit=circuit,
        hardware=hardware,
        plan=sequential_plan,
        target_epsilon=target_epsilon,
        compilation_cache=compilation_cache,
    )

    # 2. Joint Optimizer
    all_evaluated, pareto_frontier = search_pareto_optimizer(
        circuit=circuit,
        hardware=hardware,
        target_epsilon=target_epsilon,
        compilation_cache=compilation_cache,
    )

    if not pareto_frontier:
        valid = [p for p in all_evaluated if p.valid]
        best_joint = min(valid, key=lambda x: x.total_cost_score) if valid else seq_eval
    else:
        best_joint = min(pareto_frontier, key=lambda x: x.total_cost_score)

    c_seq = seq_eval.total_cost_score
    c_joint = best_joint.total_cost_score

    if c_seq > 0 and math.isfinite(c_seq):
        relative_reduction = 1.0 - (c_joint / c_seq)
    else:
        relative_reduction = 0.0

    qubit_delta = seq_eval.physical_qubits - best_joint.physical_qubits
    runtime_speedup = round(seq_eval.runtime_seconds / max(1e-9, best_joint.runtime_seconds), 2)
    failure_delta = best_joint.failure_probability - seq_eval.failure_probability

    if qubit_delta < 0 and runtime_speedup > 1.0:
        trade_off_class = "Pareto trade-off (higher physical qubits for runtime speedup)"
    elif qubit_delta >= 0 and runtime_speedup >= 1.0:
        trade_off_class = "Strict multi-objective Pareto dominance"
    else:
        trade_off_class = "Domain-constrained trade-off"

    return {
        "workload_qubits": circuit.num_qubits,
        "sequential_baseline": seq_eval.to_row(),
        "joint_optimized": best_joint.to_row(),
        "relative_cost_reduction_percent": round(relative_reduction * 100, 2),
        "qubit_savings": qubit_delta,
        "runtime_speedup": runtime_speedup,
        "failure_probability_delta": round(failure_delta, 8),
        "trade_off_classification": trade_off_class,
        "pareto_frontier_size": len(pareto_frontier),
        "total_evaluated_plans": len(all_evaluated),
    }
