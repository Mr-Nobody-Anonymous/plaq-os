import pytest
from stim_bridge import (
    SurfaceCodeStabilizerSimulator,
    ThresholdSampleResult,
    run_threshold_study,
    wilson_score_interval,
    HAS_STIM,
    HAS_PYMATCHING,
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


def test_wilson_score_interval():
    low, high = wilson_score_interval(errors=5, n=100)
    assert 0.0 <= low < 0.05
    assert 0.05 < high <= 1.0


def test_genuine_stim_circuit():
    if not HAS_STIM:
        pytest.skip("Stim not installed")
    sim = SurfaceCodeStabilizerSimulator(code_distance=3, rounds=3)
    circuit = sim.generate_stim_circuit(p=0.001)
    # Surface code d=3 has 9 data + 8 ancilla = 17 qubits minimum
    assert circuit.num_qubits >= 17
    assert circuit.num_detectors > 0
    assert circuit.num_observables == 1


def test_genuine_mwpm_decoding():
    sim = SurfaceCodeStabilizerSimulator(code_distance=3, rounds=3)
    res = sim.sample_logical_errors(p=0.001, shots=200, seed=42)
    assert isinstance(res, ThresholdSampleResult)
    assert res.code_distance == 3
    assert res.total_shots == 200
    assert 0 <= res.logical_errors <= 200
    assert 0.0 <= res.empirical_logical_error_rate <= 1.0
    assert res.confidence_interval_95[0] <= res.empirical_logical_error_rate <= res.confidence_interval_95[1]

    if HAS_STIM and HAS_PYMATCHING:
        assert res.is_genuine_simulation is True
        assert "MWPM" in res.decoder_type


def test_run_threshold_study():
    results = run_threshold_study(distances=[3], physical_error_rates=[0.001, 0.005], shots_per_point=50)
    assert len(results) == 2
    assert all(isinstance(r, ThresholdSampleResult) for r in results)
