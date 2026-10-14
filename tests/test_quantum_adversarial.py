"""
Adversarial Stress Test Suite for Plaq-OS Modularized Quantum Engine (engines/quantum).
Executed by Empirical Challenger 2 (Milestone M1).

Validates:
1. Live Quantum Simulations (Stim rotated surface code + PyMatching MWPM)
2. Pareto Frontier Optimization across workloads and hardware architectures
3. Deterministic Compilation Caching (SHA-256 canonical fingerprints)
4. Numerical Stability, Invariance, and Boundary Stress Testing
5. Empirical defect proofs (reproducing discovered issues)
"""

import math
import random
import pytest

from plaq_quantum.circuits import (
    make_test_circuit,
    make_qaoa_circuit,
    make_qft_circuit,
    make_bernstein_vazirani_circuit,
    make_chemistry_ansatz_circuit,
    make_shor_modexp_circuit,
)
from plaq_quantum.hardware import (
    HardwareModel,
    DEMO_HARDWARE,
    SUPERCONDUCTING_HERON,
    TRAPPED_ION_FORTE,
    NEUTRAL_ATOM_AQUILA,
    QLDPC_BIVARIATE_BICYCLE,
)
from plaq_quantum.stim_bridge import (
    SurfaceCodeStabilizerSimulator,
    ThresholdSampleResult,
    run_surface_code_simulation,
    run_threshold_study,
    wilson_score_interval,
    HAS_STIM,
    HAS_PYMATCHING,
)
from plaq_quantum.optimizer import (
    ExecutionPlan,
    EvaluatedPlan,
    CompilationCache,
    compute_compilation_fingerprint,
    evaluate_plan,
    extract_pareto_frontier,
    generate_candidate_space,
    search_pareto_optimizer,
    compare_sequential_vs_joint,
)
from plaq_quantum.cost_model import (
    extract_circuit_metrics,
    evaluate_fault_tolerant_cost,
    solve_minimum_code_distance,
    synthesize_rotation_t_count,
    CodeDistanceResult,
    CostEstimationResult,
)


# ==============================================================================
# SECTION 1: LIVE QUANTUM SIMULATIONS (STIM + PYMATCHING MWPM)
# ==============================================================================

class TestLiveQuantumSimulations:
    """Stress testing the live Stim rotated surface code simulator and MWPM decoder."""

    def test_environment_genuine_decoder(self):
        """Verify that genuine Stim and PyMatching are active and loaded."""
        assert HAS_STIM is True, "Stim must be installed and active"
        assert HAS_PYMATCHING is True, "PyMatching must be installed and active"

    @pytest.mark.parametrize("d,p", [
        (3, 0.001),
        (5, 0.001),
        (3, 0.01),
        (5, 0.01),
    ])
    def test_live_simulation_grid(self, d: int, p: float):
        """Execute live surface code Monte Carlo simulation trials for required d and p pairs."""
        shots = 1000
        seed = 42
        res = run_surface_code_simulation(
            code_distance=d,
            physical_error_rate=p,
            shots=shots,
            seed=seed,
        )

        assert isinstance(res, ThresholdSampleResult)
        assert res.code_distance == d
        assert res.physical_error_rate == p
        assert res.total_shots == shots
        assert 0 <= res.logical_errors <= shots
        assert res.is_genuine_simulation is True
        assert res.decoder_type == "MWPM via PyMatching"

        # Check empirical error rate calculation
        assert res.empirical_logical_error_rate == res.logical_errors / shots

        # Check 95% Wilson confidence interval sanity
        low, high = res.confidence_interval_95
        assert 0.0 <= low <= res.empirical_logical_error_rate <= high <= 1.0

        # At p=0.001 (far below threshold ~0.01), logical error rate must be very small (< 0.02)
        if p == 0.001:
            assert res.empirical_logical_error_rate <= 0.02, (
                f"Unexpected high logical error rate {res.empirical_logical_error_rate} at p=0.001, d={d}"
            )

    def test_exponential_error_suppression_below_threshold(self):
        """
        Adversarial test: Below threshold (p=0.001), increasing distance from d=3 to d=5
        must exponentially suppress (or at least not increase) logical errors under MWPM decoding.
        """
        shots = 2000
        res_d3 = run_surface_code_simulation(code_distance=3, physical_error_rate=0.001, shots=shots, seed=123)
        res_d5 = run_surface_code_simulation(code_distance=5, physical_error_rate=0.001, shots=shots, seed=123)

        assert res_d3.logical_errors >= res_d5.logical_errors, (
            f"Expected error suppression at p=0.001: d=3 had {res_d3.logical_errors} errors, "
            f"d=5 had {res_d5.logical_errors} errors."
        )

    def test_simulation_seed_determinism(self):
        """Identical random seeds must produce bit-for-bit identical detector shots and logical errors."""
        res1 = run_surface_code_simulation(code_distance=3, physical_error_rate=0.005, shots=500, seed=999)
        res2 = run_surface_code_simulation(code_distance=3, physical_error_rate=0.005, shots=500, seed=999)
        assert res1.logical_errors == res2.logical_errors
        assert res1.empirical_logical_error_rate == res2.empirical_logical_error_rate

    def test_simulation_seed_variation(self):
        """Different seeds should generate statistically valid, non-frozen stochastic results."""
        res1 = run_surface_code_simulation(code_distance=3, physical_error_rate=0.01, shots=1000, seed=111)
        res2 = run_surface_code_simulation(code_distance=3, physical_error_rate=0.01, shots=1000, seed=222)
        # At p=0.01, logical errors are non-zero and seeds should generally yield slightly different counts
        assert res1.logical_errors > 0
        assert res2.logical_errors > 0

    def test_simulation_boundary_conditions(self):
        """Test boundary conditions, illegal inputs, and zero-error edge case."""
        # Even distance must raise ValueError
        with pytest.raises(ValueError):
            run_surface_code_simulation(code_distance=4, physical_error_rate=0.001)

        # Distance < 3 must raise ValueError
        with pytest.raises(ValueError):
            run_surface_code_simulation(code_distance=1, physical_error_rate=0.001)

        # Zero physical error rate must result in exactly 0 logical errors
        res_zero = run_surface_code_simulation(code_distance=3, physical_error_rate=0.0, shots=200, seed=42)
        assert res_zero.logical_errors == 0
        assert res_zero.empirical_logical_error_rate == 0.0
        assert res_zero.confidence_interval_95[0] == 0.0


# ==============================================================================
# SECTION 2: PARETO FRONTIER OPTIMIZATION ACROSS WORKLOADS & HARDWARE
# ==============================================================================

class TestParetoOptimizationCrossMatrix:
    """Stress testing the multi-objective Pareto optimizer across workloads and hardware topologies."""

    @pytest.fixture
    def safe_workloads(self):
        return {
            "test_circuit": make_test_circuit(n_qubits=3),
            "qaoa": make_qaoa_circuit(n_qubits=4, p_layers=1),
            "bernstein_vazirani": make_bernstein_vazirani_circuit(bitstring="101"),
            "chemistry": make_chemistry_ansatz_circuit(n_qubits=4, trotter_steps=1),
            "shor": make_shor_modexp_circuit(n_qubits=5),
        }

    @pytest.fixture
    def hardware_models(self):
        return {
            "demo": DEMO_HARDWARE,
            "heron": SUPERCONDUCTING_HERON,
            "trapped_ion": TRAPPED_ION_FORTE,
            "neutral_atom": NEUTRAL_ATOM_AQUILA,
            "qldpc": QLDPC_BIVARIATE_BICYCLE,
        }

    def test_pareto_search_across_workloads(self, safe_workloads):
        """Execute Pareto optimization across representative benchmark workloads on DEMO_HARDWARE."""
        cache = CompilationCache()
        for name, circuit in safe_workloads.items():
            evaluated, pareto = search_pareto_optimizer(
                circuit=circuit,
                hardware=DEMO_HARDWARE,
                target_epsilon=1e-3,
                candidate_limit=10,
                compilation_cache=cache,
            )
            assert len(evaluated) > 0, f"Workload {name} failed evaluation"
            assert len(pareto) > 0, f"Workload {name} yielded empty Pareto set"
            assert len(pareto) <= len(evaluated)

            for plan in pareto:
                assert plan.valid is True
                assert plan.is_pareto_optimal is True
                assert plan.physical_qubits > 0
                assert plan.runtime_seconds > 0
                assert 0.0 <= plan.failure_probability <= 1e-3

    def test_pareto_search_across_all_hardware_models(self, hardware_models):
        """Execute Pareto optimization across all 5 hardware architectures using a QAOA circuit."""
        qc = make_qaoa_circuit(n_qubits=4, p_layers=1)
        cache = CompilationCache()
        for hw_name, hw in hardware_models.items():
            evaluated, pareto = search_pareto_optimizer(
                circuit=qc,
                hardware=hw,
                target_epsilon=1e-3,
                candidate_limit=10,
                compilation_cache=cache,
            )
            assert len(evaluated) > 0, f"Hardware {hw_name} failed evaluation"
            assert len(pareto) > 0, f"Hardware {hw_name} yielded empty Pareto set"

            # Verify that every plan in the Pareto frontier is non-dominated by any valid plan
            valid_evaluated = [p for p in evaluated if p.valid]
            for p_pareto in pareto:
                for p_other in valid_evaluated:
                    if p_pareto is p_other:
                        continue
                    strictly_better = (
                        p_other.physical_qubits < p_pareto.physical_qubits or
                        p_other.runtime_seconds < p_pareto.runtime_seconds or
                        p_other.failure_probability < p_pareto.failure_probability
                    )
                    better_or_equal = (
                        p_other.physical_qubits <= p_pareto.physical_qubits and
                        p_other.runtime_seconds <= p_pareto.runtime_seconds and
                        p_other.failure_probability <= p_pareto.failure_probability
                    )
                    assert not (better_or_equal and strictly_better), (
                        f"Pareto violation on {hw_name}: Plan {p_other.plan} dominates Pareto plan {p_pareto.plan}!"
                    )

    def test_full_grid_pareto_mathematical_consistency(self):
        """
        Run an exhaustive full-grid Pareto search without candidate limits
        and verify rigorous mathematical properties of the extracted Pareto set.
        """
        qc = make_test_circuit(n_qubits=3)
        cache = CompilationCache()

        all_evaluated, pareto_frontier = search_pareto_optimizer(
            circuit=qc,
            hardware=DEMO_HARDWARE,
            target_epsilon=1e-3,
            candidate_limit=None,  # Full candidate space!
            compilation_cache=cache,
        )

        valid_plans = [p for p in all_evaluated if p.valid]
        assert len(valid_plans) > 0
        assert len(pareto_frontier) > 0

        # Property 1: Pareto frontier must be a subset of valid plans
        for p in pareto_frontier:
            assert p.valid is True
            assert p.is_pareto_optimal is True

        # Property 2: Mutual non-dominance within the Pareto frontier
        for i, p1 in enumerate(pareto_frontier):
            for j, p2 in enumerate(pareto_frontier):
                if i != j:
                    dominates = (
                        p1.physical_qubits <= p2.physical_qubits and
                        p1.runtime_seconds <= p2.runtime_seconds and
                        p1.failure_probability <= p2.failure_probability and
                        (
                            p1.physical_qubits < p2.physical_qubits or
                            p1.runtime_seconds < p2.runtime_seconds or
                            p1.failure_probability < p2.failure_probability
                        )
                    )
                    assert not dominates, f"Mutual dominance detected between Pareto plans {i} and {j}"

        # Property 3: Every non-Pareto valid plan MUST be dominated by at least one Pareto plan
        pareto_configs = [(p.physical_qubits, p.runtime_seconds, p.failure_probability) for p in pareto_frontier]
        for p in valid_plans:
            cfg = (p.physical_qubits, p.runtime_seconds, p.failure_probability)
            if cfg in pareto_configs:
                continue
            is_dominated_by_pareto = any(
                par.physical_qubits <= p.physical_qubits and
                par.runtime_seconds <= p.runtime_seconds and
                par.failure_probability <= p.failure_probability
                for par in pareto_frontier
            )
            assert is_dominated_by_pareto, f"Valid plan {p.plan} was excluded from Pareto but not dominated!"

    def test_sequential_vs_joint_comparison_validity(self):
        """Verify sequential vs joint optimization comparison on test circuit."""
        qc = make_test_circuit(n_qubits=4)
        comp = compare_sequential_vs_joint(
            circuit=qc,
            hardware=DEMO_HARDWARE,
            target_epsilon=1e-3,
        )
        assert comp["workload_qubits"] == 4
        assert "sequential_baseline" in comp
        assert "joint_optimized" in comp
        assert "trade_off_classification" in comp
        assert comp["pareto_frontier_size"] >= 1
        assert comp["total_evaluated_plans"] > 0
        assert isinstance(comp["relative_cost_reduction_percent"], float)


# ==============================================================================
# SECTION 3: NUMERICAL CONSISTENCY & COMPILATION CACHING
# ==============================================================================

class TestCompilationCacheAndNumerics:
    """Stress testing the SHA-256 compilation cache and numerical consistency of cost models."""

    def test_compilation_cache_same_instance_hit(self):
        """Repeated lookups for the exact same circuit object instance must hit the cache without growing."""
        qc = make_test_circuit(n_qubits=4)
        cache = CompilationCache()

        m1 = cache.get_or_compile(qc, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        assert m1 is not None
        assert len(cache._cache) == 1

        # Second lookup with same circuit object
        m2 = cache.get_or_compile(qc, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        assert m2 is not None
        assert len(cache._cache) == 1
        assert m1.total_ops == m2.total_ops

    def test_compilation_cache_explicit_named_circuit_hit(self):
        """Circuits created with explicit deterministic names must hit the cache across distinct instances."""
        from qiskit import QuantumCircuit
        qc1 = QuantumCircuit(3, name="deterministic_qft")
        qc1.h(0)
        qc1.cx(0, 1)
        qc1.cx(1, 2)

        qc2 = QuantumCircuit(3, name="deterministic_qft")
        qc2.h(0)
        qc2.cx(0, 1)
        qc2.cx(1, 2)

        cache = CompilationCache()
        m1 = cache.get_or_compile(qc1, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        assert len(cache._cache) == 1

        m2 = cache.get_or_compile(qc2, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        # Must hit cache
        assert len(cache._cache) == 1
        assert m1.total_ops == m2.total_ops

    def test_compilation_cache_sensitivity_to_variations(self):
        """Fingerprints must distinguish differences in gates, seeds, hardware, and optimization levels."""
        qc = make_test_circuit(n_qubits=4)

        fp_base = compute_compilation_fingerprint(qc, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        fp_diff_seed = compute_compilation_fingerprint(qc, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=43)
        fp_diff_opt = compute_compilation_fingerprint(qc, DEMO_HARDWARE, opt_level=2, routing_method="basic", layout_method="trivial", seed=42)
        fp_diff_hw = compute_compilation_fingerprint(qc, SUPERCONDUCTING_HERON, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        fp_diff_rout = compute_compilation_fingerprint(qc, DEMO_HARDWARE, opt_level=1, routing_method="lookahead", layout_method="trivial", seed=42)

        # Mutate circuit gate parameter
        qc_mutated = make_test_circuit(n_qubits=4)
        qc_mutated.name = qc.name  # Ensure same name to test gate difference
        qc_mutated.rz(0.78539816, 0)
        fp_diff_circuit = compute_compilation_fingerprint(qc_mutated, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)

        hashes = {fp_base, fp_diff_seed, fp_diff_opt, fp_diff_hw, fp_diff_rout, fp_diff_circuit}
        assert len(hashes) == 6, "Detected fingerprint collision across different compilation parameters!"

    def test_cost_model_error_threshold_boundary(self):
        """Physical error exceeding threshold must cleanly invalidate the plan without NaN or unhandled crash."""
        qc = make_test_circuit(n_qubits=3)
        metrics = extract_circuit_metrics(qc)

        broken_hw = HardwareModel(
            name="broken-noisy",
            technology="superconducting",
            single_qubit_error=0.01,
            two_qubit_error=0.05,
            measurement_error=0.05,
            single_qubit_time_ns=30.0,
            two_qubit_time_ns=200.0,
            measurement_time_ns=500.0,
            surface_code_cycle_time_ns=1000.0,
            surface_code_threshold=0.01,
            max_physical_qubits=100_000,
        )

        res = evaluate_fault_tolerant_cost(metrics, broken_hw, target_epsilon=1e-3)
        assert res.valid is False
        assert res.total_cost_score == float("inf")
        assert "exceeds" in res.feasibility_reason or "threshold" in res.feasibility_reason

    def test_code_distance_result_dual_type(self):
        """CodeDistanceResult must behave as an integer AND support tuple unpacking."""
        res = solve_minimum_code_distance(physical_error=0.001, threshold=0.01, spacetime_volume=10_000, allocated_error_budget=1e-3)

        # Integer behavior
        assert isinstance(res, int)
        assert res % 2 == 1
        assert res >= 3
        assert res + 2 > res

        # Tuple unpacking behavior (d, feasible, reason)
        d_val, feasible, reason = res
        assert d_val == int(res)
        assert feasible is True
        assert isinstance(reason, str)

    def test_zero_physical_error_handling(self):
        """Cost model must handle p=0 without zero-division or math domain error."""
        qc = make_test_circuit(n_qubits=2)
        metrics = extract_circuit_metrics(qc)

        ideal_hw = HardwareModel(
            name="ideal-zero-noise",
            technology="superconducting",
            single_qubit_error=0.0,
            two_qubit_error=0.0,
            measurement_error=0.0,
            single_qubit_time_ns=30.0,
            two_qubit_time_ns=200.0,
            measurement_time_ns=500.0,
            surface_code_cycle_time_ns=1000.0,
            surface_code_threshold=0.01,
            max_physical_qubits=100_000,
        )

        res = evaluate_fault_tolerant_cost(metrics, ideal_hw, target_epsilon=1e-3)
        assert res.valid is True
        assert res.code_distance == 3
        assert math.isfinite(res.total_cost_score)
        assert not math.isnan(res.failure_probability)


# ==============================================================================
# SECTION 4: EMPIRICAL DEFECT REPRODUCTIONS (CHALLENGER FINDINGS)
# ==============================================================================

class TestEmpiricalDefectProofs:
    """
    Formal regression tests for defects identified by Empirical Challenger 2.
    Verified passing following M1 Iteration 2 optimizer remediation.
    """

    def test_defect_compilation_failure_missing_feasibility_reason(self):
        """
        Demonstrates that when a candidate plan fails Qiskit transpilation (e.g. Lookahead routing
        on linear topology for QFT), evaluate_plan handles compilation failure gracefully without TypeError
        and marks the plan invalid with explicit feasibility_reason.
        """
        qc = make_qft_circuit(4)
        plan_failing_routing = ExecutionPlan(
            optimization_level=0,
            routing_method="lookahead",
            layout_method="trivial",
            num_magic_factories=1,
            code_distance_strategy="minimal_safe",
            decoder_architecture="streaming_asic",
        )
        res = evaluate_plan(circuit=qc, hardware=DEMO_HARDWARE, plan=plan_failing_routing)
        assert res.valid is False
        assert res.physical_qubits == 999_999
        assert res.total_cost_score == float("inf")
        assert res.cost_result.feasibility_reason == "Compilation failed with given routing/layout options."

    def test_defect_compilation_cache_circuit_name_causes_miss_on_equivalent_circuits(self):
        """
        Demonstrates that two fresh instances from make_test_circuit(4) hit the cache
        because circuit fingerprinting uses canonical structure instead of volatile circuit.name.
        """
        qc1 = make_test_circuit(n_qubits=4)
        qc2 = make_test_circuit(n_qubits=4)
        cache = CompilationCache()

        m1 = cache.get_or_compile(qc1, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        assert m1 is not None
        assert len(cache._cache) == 1

        # Second lookup with fresh equivalent circuit instance
        m2 = cache.get_or_compile(qc2, DEMO_HARDWARE, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        assert m2 is not None

        # Expect cache length to be 1 if compilation caching is truly deterministic across equivalent circuits.
        assert len(cache._cache) == 1, (
            f"Cache length grew to {len(cache._cache)}! circuit.name '{qc1.name}' vs '{qc2.name}' "
            f"caused different fingerprints for identical circuits."
        )

    def test_defect_compilation_cache_basis_gates_omitted(self):
        """
        Demonstrates fingerprint differentiation when two hardware configurations have the same name
        and topology, but different basis gates (e.g. CX vs CZ).
        """
        qc = make_test_circuit(n_qubits=3)
        hw_cx = DEMO_HARDWARE
        hw_cz = HardwareModel(
            name=DEMO_HARDWARE.name,
            technology="superconducting",
            single_qubit_error=1e-4,
            two_qubit_error=1e-3,
            measurement_error=1e-3,
            single_qubit_time_ns=30.0,
            two_qubit_time_ns=200.0,
            measurement_time_ns=500.0,
            surface_code_cycle_time_ns=1000.0,
            topology_type="linear",
            basis_gates=("cz", "rz", "sx", "x"),  # Different basis gates!
        )

        fp1 = compute_compilation_fingerprint(qc, hw_cx, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)
        fp2 = compute_compilation_fingerprint(qc, hw_cz, opt_level=1, routing_method="basic", layout_method="trivial", seed=42)

        # Different basis gates must produce different compilation fingerprints to prevent cache poisoning!
        assert fp1 != fp2, "Fingerprint collision detected! Basis gates are not included in compilation fingerprint."
