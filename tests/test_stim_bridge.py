import pytest
from stim_bridge import (
    SurfaceCodeStabilizerSimulator,
    ThresholdSampleResult,
    run_threshold_study,
)


def test_stim_simulator_initialization():
    sim = SurfaceCodeStabilizerSimulator(code_distance=3)
    assert sim.d == 3
    assert sim.num_data_qubits == 9
    assert sim.num_ancilla_qubits == 8

    # Even distance must raise ValueError
    with pytest.raises(ValueError):
        SurfaceCodeStabilizerSimulator(code_distance=4)

    # Distance < 3 must raise ValueError
    with pytest.raises(ValueError):
        SurfaceCodeStabilizerSimulator(code_distance=1)


def test_generate_stim_circuit_str():
    sim = SurfaceCodeStabilizerSimulator(code_distance=3, rounds=2)
    stim_text = sim.generate_stim_circuit_str(p=0.001)
    assert isinstance(stim_text, str)
    assert "DEPOLARIZE1" in stim_text
    assert "DEPOLARIZE2" in stim_text
    assert "TICK" in stim_text
    assert "MR" in stim_text


def test_sample_logical_errors():
    sim = SurfaceCodeStabilizerSimulator(code_distance=3)
    res = sim.sample_logical_errors(p=0.001, shots=100, seed=42)
    assert isinstance(res, ThresholdSampleResult)
    assert res.code_distance == 3
    assert res.total_shots == 100
    assert 0 <= res.logical_errors <= 100
    assert 0.0 <= res.empirical_logical_error_rate <= 1.0
    assert 0.0 < res.predicted_logical_error_rate <= 1.0


def test_run_threshold_study():
    results = run_threshold_study(distances=[3], physical_error_rates=[0.001, 0.005], shots_per_point=50)
    assert len(results) == 2
    assert all(isinstance(r, ThresholdSampleResult) for r in results)
