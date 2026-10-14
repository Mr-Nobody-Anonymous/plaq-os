"""Quantum engine tools wrapping plaq_quantum."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from pydantic import Field
from plaq_contracts.common import PlaqBaseModel
from plaq_contracts.tool import ToolResult
import plaq_quantum


class QuantumCompileParams(PlaqBaseModel):
    """Parameters for quantum.compile."""
    workload: Optional[str] = Field(default=None, description="Circuit workload identifier (e.g. 'bv', 'qaoa', 'qft')")
    qubits: Optional[int] = Field(default=None, description="Number of qubits")
    bitstring: Optional[str] = Field(default=None, description="Bitstring for Bernstein-Vazirani")
    qasm: Optional[str] = Field(default=None, description="Raw QASM circuit string")
    rotation_angle: Optional[float] = Field(default=None, description="Single-qubit rotation angle in radians")
    synth_precision: float = Field(default=1e-10, description="Target precision for T-count synthesis")


class QuantumEstimateParams(PlaqBaseModel):
    """Parameters for quantum.estimate."""
    hardware_profile: str = Field(default="superconducting_heron", description="Hardware profile name")
    code_distance: Optional[int] = Field(default=None, description="Rotated surface code distance d")
    physical_error: Optional[float] = Field(default=None, description="Physical 2-qubit gate error rate")
    target_epsilon: float = Field(default=1e-3, description="Target total logical failure probability")
    num_qubits: int = Field(default=5, description="Number of logical qubits")
    t_count: int = Field(default=100, description="Total T-gate count")
    t_depth: int = Field(default=50, description="T-depth")
    circuit_depth: int = Field(default=100, description="Total circuit depth")
    spacetime_volume: Optional[int] = Field(default=None, description="Total spacetime volume")


class QuantumSimulateParams(PlaqBaseModel):
    """Parameters for quantum.simulate."""
    code_distance: int = Field(default=3, description="Surface code distance d (odd integer >= 3)")
    physical_error_rate: float = Field(default=0.001, description="Physical error rate")
    shots: int = Field(default=1000, description="Number of Monte Carlo detector shots")
    rounds: Optional[int] = Field(default=None, description="Number of syndrome measurement rounds")
    seed: int = Field(default=42, description="RNG seed")

    def model_post_init(self, __context: Any) -> None:
        extra = getattr(self, "__pydantic_extra__", None) or {}
        if "distance" in extra and extra["distance"] is not None:
            self.code_distance = int(extra["distance"])


def quantum_compile(params: QuantumCompileParams, context: Any) -> ToolResult:
    """Synthesize circuit, decompose single-qubit rotations, and extract fault-tolerant metrics."""
    t0 = time.perf_counter()
    try:
        synth_t_count = 0
        if params.rotation_angle is not None:
            synth_t_count = plaq_quantum.cost_model.synthesize_rotation_t_count(
                rotation_angle=params.rotation_angle,
                precision=params.synth_precision,
            )

        # Generate or synthesize circuit
        workload = (params.workload or "").lower()
        if params.bitstring or "bv" in workload or "bernstein" in workload:
            bstring = params.bitstring or "101"
            qc = plaq_quantum.circuits.make_bernstein_vazirani_circuit(bstring)
        elif "qaoa" in workload:
            qc = plaq_quantum.circuits.make_qaoa_circuit(params.qubits or 6)
        elif "qft" in workload:
            qc = plaq_quantum.circuits.make_qft_circuit(params.qubits or 4)
        elif "chemistry" in workload:
            qc = plaq_quantum.circuits.make_chemistry_ansatz_circuit(params.qubits or 4)
        else:
            qc = plaq_quantum.circuits.make_test_circuit(params.qubits or 4)

        metrics = plaq_quantum.cost_model.extract_circuit_metrics(qc)

        out_data = {
            "num_qubits": metrics.num_qubits,
            "depth": metrics.depth,
            "t_ops": metrics.t_ops + synth_t_count,
            "t_depth": metrics.t_depth,
            "total_ops": metrics.total_ops,
            "synthesis_t_count": synth_t_count,
            "summary": f"Circuit compiled: {metrics.num_qubits} qubits, depth={metrics.depth}, T-count={metrics.t_ops + synth_t_count}",
        }

        return ToolResult(
            success=True,
            output=json.dumps(out_data, indent=2),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=0,
            modified_files=[],
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            output="",
            error=str(exc),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )


def quantum_estimate(params: QuantumEstimateParams, context: Any) -> ToolResult:
    """Evaluate fault-tolerant resource requirements and code distance."""
    t0 = time.perf_counter()
    try:
        hw = plaq_quantum.hardware.get_hardware_profile(params.hardware_profile)
        p_err = (
            params.physical_error
            if params.physical_error is not None
            else getattr(hw, "two_qubit_error", getattr(hw, "physical_error_rate", 0.001))
        )
        stv = params.spacetime_volume or (params.num_qubits * params.circuit_depth)

        if params.code_distance is not None:
            code_d = params.code_distance
            feasible = p_err < hw.surface_code_threshold
            f_reason = "Code distance specified directly" if feasible else f"Physical error rate {p_err} exceeds threshold {hw.surface_code_threshold}"
        else:
            dist_res = plaq_quantum.cost_model.solve_minimum_code_distance(
                physical_error=p_err,
                threshold=hw.surface_code_threshold,
                spacetime_volume=stv,
                allocated_error_budget=params.target_epsilon,
            )
            code_d = dist_res.code_distance
            feasible = dist_res.feasible
            f_reason = dist_res.feasibility_reason

        metrics = plaq_quantum.cost_model.CircuitMetrics(
            num_qubits=params.num_qubits,
            depth=params.circuit_depth,
            total_ops=params.circuit_depth * params.num_qubits,
            single_qubit_ops=max(0, params.circuit_depth * params.num_qubits - params.t_count),
            two_qubit_ops=params.num_qubits,
            t_ops=params.t_count,
            t_depth=params.t_depth,
            measurement_ops=params.num_qubits,
            operation_counts={"t": params.t_count},
            synthesis_t_count=0,
        )

        cost_res = plaq_quantum.cost_model.evaluate_fault_tolerant_cost(
            metrics=metrics,
            hardware=hw,
            target_epsilon=params.target_epsilon,
            code_distance_override=code_d,
        )

        out_data = {
            "feasible": cost_res.valid and feasible,
            "valid": cost_res.valid and feasible,
            "feasibility_reason": f_reason or cost_res.feasibility_reason,
            "code_distance": cost_res.code_distance,
            "physical_qubits": cost_res.physical_qubits,
            "runtime_seconds": cost_res.runtime_seconds,
            "failure_probability": cost_res.failure_probability,
            "summary": f"Metrics extracted: code_distance={cost_res.code_distance}, physical_qubits={cost_res.physical_qubits}, runtime_s={cost_res.runtime_seconds:.4e}",
        }

        return ToolResult(
            success=True,
            output=json.dumps(out_data, indent=2),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=0,
            modified_files=[],
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            output="",
            error=str(exc),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )


def quantum_simulate(params: QuantumSimulateParams, context: Any) -> ToolResult:
    """Simulate rotated surface code syndrome measurements and MWPM decoding."""
    t0 = time.perf_counter()
    try:
        # Surface code distance must be odd integer >= 3
        if params.code_distance < 3 or params.code_distance % 2 == 0:
            return ToolResult(
                success=False,
                output="",
                error=f"Surface code distance d must be an odd integer >= 3, got {params.code_distance}",
                duration_ms=(time.perf_counter() - t0) * 1000,
                exit_code=1,
                modified_files=[],
            )

        sim_res = plaq_quantum.stim_bridge.run_surface_code_simulation(
            code_distance=params.code_distance,
            physical_error_rate=params.physical_error_rate,
            shots=params.shots,
            rounds=params.rounds,
            seed=params.seed,
        )

        out_data = {
            "code_distance": sim_res.code_distance,
            "physical_error_rate": sim_res.physical_error_rate,
            "total_shots": sim_res.total_shots,
            "logical_errors": sim_res.logical_errors,
            "empirical_logical_error_rate": sim_res.empirical_logical_error_rate,
            "confidence_interval_95": sim_res.confidence_interval_95,
            "decoder_type": sim_res.decoder_type,
            "summary": f"Simulation completed: d={sim_res.code_distance}, shots={sim_res.total_shots}, errors={sim_res.logical_errors}, p_L={sim_res.empirical_logical_error_rate:.4e}",
        }

        return ToolResult(
            success=True,
            output=json.dumps(out_data, indent=2),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=0,
            modified_files=[],
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            output="",
            error=str(exc),
            duration_ms=(time.perf_counter() - t0) * 1000,
            exit_code=1,
            modified_files=[],
        )
