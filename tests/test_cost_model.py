"""
Unit tests for fault-tolerant cost model and resource scaling.
"""

import pytest
from circuits import make_test_circuit
from hardware import DEMO_HARDWARE, SUPERCONDUCTING_HERON, QLDPC_BIVARIATE_BICYCLE
from cost_model import (
    extract_circuit_metrics,
    solve_minimum_code_distance,
    evaluate_fault_tolerant_cost,
)


def test_extract_circuit_metrics():
    qc = make_test_circuit(5)
    metrics = extract_circuit_metrics(qc)
    assert metrics.num_qubits == 5
    assert metrics.depth > 0
    assert metrics.two_qubit_ops > 0
    assert metrics.single_qubit_ops > 0


def test_solve_minimum_code_distance():
    d1 = solve_minimum_code_distance(
        physical_error=1e-3,
        threshold=0.01,
        spacetime_volume=1000,
        allocated_error_budget=1e-3,
    )
    assert d1 % 2 == 1
    assert d1 >= 3

    d2 = solve_minimum_code_distance(
        physical_error=1e-3,
        threshold=0.01,
        spacetime_volume=10_000_000,
        allocated_error_budget=1e-4,
    )
    assert d2 >= d1
    assert d2 % 2 == 1


def test_evaluate_fault_tolerant_cost_structure():
    qc = make_test_circuit(5)
    metrics = extract_circuit_metrics(qc)
    cost = evaluate_fault_tolerant_cost(
        metrics=metrics,
        hardware=SUPERCONDUCTING_HERON,
        target_epsilon=1e-3,
        num_magic_factories=2,
    )

    assert cost.valid is True
    assert cost.physical_qubits > 0
    assert cost.code_distance % 2 == 1
    assert cost.factory_physical_qubits > 0
    assert cost.physical_qubits == cost.data_physical_qubits + cost.factory_physical_qubits
    assert cost.runtime_seconds > 0


def test_qldpc_cost_scaling():
    qc = make_test_circuit(5)
    metrics = extract_circuit_metrics(qc)
    cost = evaluate_fault_tolerant_cost(
        metrics=metrics,
        hardware=QLDPC_BIVARIATE_BICYCLE,
        code_family="qldpc",
    )
    assert cost.valid is True
    assert cost.data_physical_qubits > 0


def test_decoder_stall_behavior():
    qc = make_test_circuit(4)
    metrics = extract_circuit_metrics(qc)

    slow_cost = evaluate_fault_tolerant_cost(
        metrics=metrics,
        hardware=SUPERCONDUCTING_HERON,
        decoder_latency_ns=2000.0,
    )
    assert slow_cost.decoder_stall_factor == 2.0

    fast_cost = evaluate_fault_tolerant_cost(
        metrics=metrics,
        hardware=SUPERCONDUCTING_HERON,
        decoder_latency_ns=200.0,
    )
    assert fast_cost.decoder_stall_factor == 1.0
