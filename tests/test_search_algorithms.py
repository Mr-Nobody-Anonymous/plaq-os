import pytest
from circuits import make_test_circuit
from hardware import DEMO_HARDWARE
from optimizer import CompilationCache
from search_algorithms import (
    search_exhaustive,
    search_random,
    search_greedy,
    search_simulated_annealing,
    benchmark_search_methods,
)


@pytest.fixture
def test_setup():
    circuit = make_test_circuit(n_qubits=4)
    hardware = DEMO_HARDWARE
    cache = CompilationCache()
    return circuit, hardware, cache


def test_search_exhaustive(test_setup):
    circuit, hardware, cache = test_setup
    evals, duration = search_exhaustive(circuit, hardware, target_epsilon=1e-3, compilation_cache=cache)
    assert len(evals) > 0
    assert duration > 0.0
    assert any(p.valid for p in evals)


def test_search_random(test_setup):
    circuit, hardware, cache = test_setup
    evals, duration = search_random(circuit, hardware, target_epsilon=1e-3, max_evaluations=10, seed=42, compilation_cache=cache)
    assert len(evals) <= 10
    assert duration > 0.0


def test_search_greedy(test_setup):
    circuit, hardware, cache = test_setup
    evals, duration = search_greedy(circuit, hardware, target_epsilon=1e-3, compilation_cache=cache)
    assert len(evals) > 0
    assert duration > 0.0


def test_search_simulated_annealing(test_setup):
    circuit, hardware, cache = test_setup
    evals, duration = search_simulated_annealing(
        circuit, hardware, target_epsilon=1e-3, iterations=10, compilation_cache=cache
    )
    assert len(evals) > 0
    assert duration > 0.0


def test_benchmark_search_methods(test_setup):
    circuit, hardware, cache = test_setup
    results = benchmark_search_methods(circuit, hardware, target_epsilon=1e-3, compilation_cache=cache)
    assert len(results) == 4
    names = [r.algorithm_name for r in results]
    assert "Exhaustive Search" in names
    assert "Greedy Optimization" in names
    assert "Simulated Annealing" in names
    assert "Random Search (N=35)" in names

    # Ground truth (Exhaustive) should have 0% optimality gap
    ex = next(r for r in results if r.algorithm_name == "Exhaustive Search")
    assert ex.optimality_gap_percent == 0.0
    assert ex.pareto_coverage_percent == 100.0
