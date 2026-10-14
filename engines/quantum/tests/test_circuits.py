"""
Unit tests for circuit generation.
"""

import pytest
try:
    from plaq_quantum.circuits import (
        make_test_circuit,
        make_qaoa_circuit,
        make_qft_circuit,
        make_bernstein_vazirani_circuit,
        make_random_clifford_t_circuit,
        make_chemistry_ansatz_circuit,
        make_shor_modexp_circuit,
        get_benchmark_workloads,
        get_workload_manifest,
    )
except ImportError:
    from circuits import (
    make_test_circuit,
    make_qaoa_circuit,
    make_qft_circuit,
    make_bernstein_vazirani_circuit,
    make_random_clifford_t_circuit,
    make_chemistry_ansatz_circuit,
    make_shor_modexp_circuit,
    get_benchmark_workloads,
    get_workload_manifest,
)


def test_make_test_circuit():
    qc = make_test_circuit(5)
    assert qc.num_qubits == 5
    assert qc.size() > 0
    ops = qc.count_ops()
    assert "h" in ops
    assert "cx" in ops
    assert "rz" in ops


def test_make_qaoa_circuit():
    qc = make_qaoa_circuit(n_qubits=4, p_layers=2)
    assert qc.num_qubits == 4
    ops = qc.count_ops()
    assert "cx" in ops
    assert "rz" in ops
    assert "rx" in ops


def test_make_qft_circuit():
    qc = make_qft_circuit(n_qubits=4)
    assert qc.num_qubits == 4
    ops = qc.count_ops()
    assert "h" in ops


def test_make_bernstein_vazirani_circuit():
    qc = make_bernstein_vazirani_circuit("101")
    assert qc.num_qubits == 4
    ops = qc.count_ops()
    assert "cx" in ops
    assert "h" in ops


def test_make_random_clifford_t():
    qc = make_random_clifford_t_circuit(n_qubits=5, depth=10, t_density=0.5, seed=99)
    assert qc.num_qubits == 5
    ops = qc.count_ops()
    assert "t" in ops


def test_make_chemistry_ansatz():
    qc = make_chemistry_ansatz_circuit(n_qubits=6, trotter_steps=1)
    assert qc.num_qubits == 6
    ops = qc.count_ops()
    assert "t" in ops or "rz" in ops


def test_make_shor_modexp():
    qc = make_shor_modexp_circuit(n_qubits=7)
    assert qc.num_qubits == 7
    assert qc.size() > 0


def test_get_benchmark_workloads():
    workloads = get_benchmark_workloads()
    assert len(workloads) >= 6
    for name, qc in workloads.items():
        assert qc.num_qubits >= 4


def test_workload_manifest():
    manifest = get_workload_manifest()
    workloads = get_benchmark_workloads()
    for name in workloads.keys():
        assert name in manifest
        entry = manifest[name]
        assert "family" in entry
        assert "mathematical_task" in entry
        assert "semantics" in entry
        assert "literature_reference" in entry
        assert "correctness_criteria" in entry

