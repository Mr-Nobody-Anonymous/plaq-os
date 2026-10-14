"""
Unit tests for the joint optimizer and Pareto frontier extraction.
"""

import pytest
from circuits import make_test_circuit
from hardware import DEMO_HARDWARE, SUPERCONDUCTING_HERON
from optimizer import (
    ExecutionPlan,
    CompilationCache,
    compute_compilation_fingerprint,
    evaluate_plan,
    extract_pareto_frontier,
    generate_candidate_space,
    search_pareto_optimizer,
    compare_sequential_vs_joint,
)


def test_generate_candidate_space():
    space = generate_candidate_space(
        opt_levels=[0, 1],
        routing_methods=["basic"],
        factories=[1, 2],
        qec_strategies=["minimal_safe"],
        decoders=["streaming_asic"],
    )
    assert len(space) == 4


def test_evaluate_plan():
    qc = make_test_circuit(4)
    plan = ExecutionPlan(
        optimization_level=1,
        routing_method="basic",
        layout_method="trivial",
        num_magic_factories=2,
        code_distance_strategy="minimal_safe",
        decoder_architecture="embedded_fpga",
    )
    evaluated = evaluate_plan(
        circuit=qc,
        hardware=DEMO_HARDWARE,
        plan=plan,
        target_epsilon=1e-3,
    )
    assert evaluated.valid is True
    assert evaluated.physical_qubits > 0
    assert evaluated.runtime_seconds > 0
    assert evaluated.code_distance % 2 == 1


def test_pareto_frontier_filtering():
    qc = make_test_circuit(4)
    evaluated_list, pareto_frontier = search_pareto_optimizer(
        circuit=qc,
        hardware=DEMO_HARDWARE,
        target_epsilon=1e-3,
        candidate_limit=15,
    )
    assert len(evaluated_list) > 0
    assert len(pareto_frontier) > 0

    for p in pareto_frontier:
        assert p.valid is True
        assert p.is_pareto_optimal is True

    for i, p1 in enumerate(pareto_frontier):
        for j, p2 in enumerate(pareto_frontier):
            if i != j:
                strictly_better = (
                    p1.physical_qubits < p2.physical_qubits or
                    p1.runtime_seconds < p2.runtime_seconds or
                    p1.failure_probability < p2.failure_probability
                )
                better_or_equal = (
                    p1.physical_qubits <= p2.physical_qubits and
                    p1.runtime_seconds <= p2.runtime_seconds and
                    p1.failure_probability <= p2.failure_probability
                )
                assert not (better_or_equal and strictly_better)


def test_compare_sequential_vs_joint():
    qc = make_test_circuit(4)
    res = compare_sequential_vs_joint(
        circuit=qc,
        hardware=DEMO_HARDWARE,
        target_epsilon=1e-3,
    )
    assert "sequential_baseline" in res
    assert "joint_optimized" in res
    assert "relative_cost_reduction_percent" in res
    assert "trade_off_classification" in res
    assert res["pareto_frontier_size"] > 0


def test_compilation_cache_fingerprint():
    qc1 = make_test_circuit(4)
    qc2 = make_test_circuit(5)

    fp1 = compute_compilation_fingerprint(qc1, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
    fp2 = compute_compilation_fingerprint(qc2, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
    fp3 = compute_compilation_fingerprint(qc1, DEMO_HARDWARE, opt_level=2, routing_method="basic", layout_method="trivial", seed=42)

    assert isinstance(fp1, str) and len(fp1) == 64
    assert fp1 != fp2
    assert fp1 != fp3

    cache = CompilationCache()
    m1 = cache.get_or_compile(qc1, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial")
    assert m1 is not None
    assert len(cache._cache) == 1

