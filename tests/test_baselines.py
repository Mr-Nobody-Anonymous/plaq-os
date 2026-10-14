import pytest
from circuits import make_test_circuit
from hardware import DEMO_HARDWARE
from optimizer import CompilationCache
from baselines import run_four_baselines_protocol, run_ablation_study


@pytest.fixture
def test_setup():
    circuit = make_test_circuit(n_qubits=4)
    hardware = DEMO_HARDWARE
    cache = CompilationCache()
    return circuit, hardware, cache


def test_four_baselines_protocol(test_setup):
    circuit, hardware, cache = test_setup
    records = run_four_baselines_protocol(
        circuit=circuit,
        hardware=hardware,
        target_epsilon=1e-3,
        compilation_cache=cache,
    )

    assert len(records) == 4
    ids = [r.baseline_id for r in records]
    assert ids == ["B1", "B2", "B3", "B4"]

    b1, b2, b3, b4 = records
    assert b1.physical_qubits > 0
    assert b2.physical_qubits > 0
    assert b3.physical_qubits > 0
    assert b4.physical_qubits > 0

    assert b4.total_cost_score <= b2.total_cost_score
    assert b4.relative_reduction_vs_compiler >= 0.0


def test_ablation_study(test_setup):
    circuit, hardware, cache = test_setup
    abl_records = run_ablation_study(
        circuit=circuit,
        hardware=hardware,
        target_epsilon=1e-3,
        compilation_cache=cache,
    )

    assert len(abl_records) == 5
    names = [r.configuration_name for r in abl_records]
    assert "Full Joint Optimizer" in names
    assert "No Decoder Co-Design" in names
    assert "No Factory Scaling" in names

    full_record = abl_records[0]
    assert full_record.cost_penalty_percent == 0.0
    for r in abl_records[1:]:
        assert r.cost_penalty_percent >= 0.0
