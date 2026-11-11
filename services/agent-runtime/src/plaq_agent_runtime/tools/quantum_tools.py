"""Quantum engine tools wrapping plaq_quantum for the agent runtime and MCP."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import time
from typing import Any, List, Optional

from pydantic import Field
from plaq_contracts.common import PlaqBaseModel
from plaq_contracts.tool import ToolResult
import plaq_quantum
from plaq_quantum.workloads import (
    list_hardware_profiles,
    list_workloads,
    resolve_circuit,
)


def _json_default(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, (set, tuple)):
        return list(obj)
    return str(obj)


def _ok(t0: float, data: Any) -> ToolResult:
    return ToolResult(
        success=True,
        output=json.dumps(data, indent=2, default=_json_default),
        duration_ms=(time.perf_counter() - t0) * 1000,
        exit_code=0,
        modified_files=[],
    )


def _err(t0: float, exc: Any) -> ToolResult:
    return ToolResult(
        success=False,
        output="",
        error=str(exc),
        duration_ms=(time.perf_counter() - t0) * 1000,
        exit_code=1,
        modified_files=[],
    )


class QuantumCompileParams(PlaqBaseModel):
    """Parameters for quantum.compile."""

    workload: Optional[str] = Field(default=None, description="Circuit workload identifier (e.g. 'bv', 'qaoa', 'qft')")
    qubits: Optional[int] = Field(default=None, description="Number of qubits")
    bitstring: Optional[str] = Field(default=None, description="Bitstring for Bernstein-Vazirani")
    qasm: Optional[str] = Field(default=None, description="Raw OpenQASM 2.0 circuit string")
    rotation_angle: Optional[float] = Field(default=None, description="Single-qubit rotation angle in radians")
    synth_precision: float = Field(default=1e-10, description="Target precision for T-count synthesis")
    p_layers: int = Field(default=2, description="QAOA p-layers")


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
    workload: Optional[str] = Field(default=None, description="If set, metrics are taken from this compiled workload")


class QuantumSimulateParams(PlaqBaseModel):
    """Parameters for quantum.simulate (surface-code QEC)."""

    code_distance: int = Field(default=3, description="Surface code distance d (odd integer >= 3)")
    physical_error_rate: float = Field(default=0.001, description="Physical error rate")
    shots: int = Field(default=1000, description="Number of Monte Carlo detector shots")
    rounds: Optional[int] = Field(default=None, description="Number of syndrome measurement rounds")
    seed: int = Field(default=42, description="RNG seed")

    def model_post_init(self, __context: Any) -> None:
        extra = getattr(self, "__pydantic_extra__", None) or {}
        if "distance" in extra and extra["distance"] is not None:
            self.code_distance = int(extra["distance"])


class QuantumRunParams(PlaqBaseModel):
    """Parameters for quantum.run (circuit-level simulation)."""

    workload: Optional[str] = Field(default="bell", description="Named workload or alias")
    qubits: Optional[int] = Field(default=None, description="Override qubit count")
    qasm: Optional[str] = Field(default=None, description="OpenQASM 2.0 body")
    bitstring: Optional[str] = Field(default=None, description="Bernstein-Vazirani hidden string")
    shots: int = Field(default=0, description="0 = statevector probabilities; >0 = sampled counts")
    seed: int = Field(default=42, description="RNG seed")
    compute_energy: bool = Field(default=False, description="Evaluate MaxCut/Ising energy on the statevector")


class QuantumOptimizeParams(PlaqBaseModel):
    """Parameters for quantum.optimize."""

    workload: str = Field(default="test_rz_cx_5q")
    hardware_profile: str = Field(default="superconducting_heron")
    target_epsilon: float = Field(default=1e-3)
    candidate_limit: int = Field(default=12)
    qubits: Optional[int] = None


class QuantumBaselinesParams(PlaqBaseModel):
    """Parameters for quantum.baselines."""

    workload: str = Field(default="test_rz_cx_5q")
    hardware_profile: str = Field(default="demo-illustrative")
    target_epsilon: float = Field(default=1e-3)
    qubits: Optional[int] = None


class QuantumThresholdParams(PlaqBaseModel):
    """Parameters for quantum.threshold."""

    distances: Optional[List[int]] = Field(default=None)
    physical_error_rates: Optional[List[float]] = Field(default=None)
    shots_per_point: int = Field(default=40)


class QuantumQasmParams(PlaqBaseModel):
    """Parameters for quantum.qasm."""

    qasm: str = Field(..., description="OpenQASM 2.0 body")


class QuantumWorkloadsParams(PlaqBaseModel):
    """Parameters for quantum.workloads (none required)."""


class QuantumHardwareParams(PlaqBaseModel):
    """Parameters for quantum.hardware (none required)."""


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

        qc = resolve_circuit(
            workload=params.workload,
            qubits=params.qubits,
            bitstring=params.bitstring,
            qasm=params.qasm,
            p_layers=params.p_layers,
        )
        metrics = plaq_quantum.cost_model.extract_circuit_metrics(qc)
        out_data = {
            "num_qubits": metrics.num_qubits,
            "depth": metrics.depth,
            "t_ops": metrics.t_ops + synth_t_count,
            "t_depth": metrics.t_depth,
            "total_ops": metrics.total_ops,
            "synthesis_t_count": synth_t_count,
            "workload": params.workload,
            "summary": (
                f"Circuit compiled: {metrics.num_qubits} qubits, "
                f"depth={metrics.depth}, T-count={metrics.t_ops + synth_t_count}"
            ),
        }
        return _ok(t0, out_data)
    except Exception as exc:
        return _err(t0, exc)


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

        if params.workload:
            qc = resolve_circuit(workload=params.workload, qubits=params.num_qubits)
            metrics = plaq_quantum.cost_model.extract_circuit_metrics(qc)
            num_qubits, circuit_depth, t_count, t_depth = (
                metrics.num_qubits,
                metrics.depth,
                metrics.t_ops,
                metrics.t_depth,
            )
        else:
            num_qubits = params.num_qubits
            circuit_depth = params.circuit_depth
            t_count = params.t_count
            t_depth = params.t_depth
            metrics = plaq_quantum.cost_model.CircuitMetrics(
                num_qubits=num_qubits,
                depth=circuit_depth,
                total_ops=circuit_depth * num_qubits,
                single_qubit_ops=max(0, circuit_depth * num_qubits - t_count),
                two_qubit_ops=num_qubits,
                t_ops=t_count,
                t_depth=t_depth,
                measurement_ops=num_qubits,
                operation_counts={"t": t_count},
                synthesis_t_count=0,
            )

        stv = params.spacetime_volume or (num_qubits * circuit_depth)

        if params.code_distance is not None:
            code_d = params.code_distance
            feasible = p_err < hw.surface_code_threshold
            f_reason = (
                "Code distance specified directly"
                if feasible
                else f"Physical error rate {p_err} exceeds threshold {hw.surface_code_threshold}"
            )
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
            "hardware_profile": hw.name,
            "num_qubits": num_qubits,
            "circuit_depth": circuit_depth,
            "t_count": t_count,
            "summary": (
                f"Metrics extracted: code_distance={cost_res.code_distance}, "
                f"physical_qubits={cost_res.physical_qubits}, "
                f"runtime_s={cost_res.runtime_seconds:.4e}"
            ),
        }
        return _ok(t0, out_data)
    except Exception as exc:
        return _err(t0, exc)


def quantum_simulate(params: QuantumSimulateParams, context: Any) -> ToolResult:
    """Simulate rotated surface code syndrome measurements and MWPM decoding."""
    t0 = time.perf_counter()
    try:
        if params.code_distance < 3 or params.code_distance % 2 == 0:
            return _err(
                t0,
                f"Surface code distance d must be an odd integer >= 3, got {params.code_distance}",
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
            "summary": (
                f"Simulation completed: d={sim_res.code_distance}, shots={sim_res.total_shots}, "
                f"errors={sim_res.logical_errors}, p_L={sim_res.empirical_logical_error_rate:.4e}"
            ),
        }
        return _ok(t0, out_data)
    except Exception as exc:
        return _err(t0, exc)


def quantum_run(params: QuantumRunParams, context: Any) -> ToolResult:
    """Statevector or shot-based circuit simulation for agent experiments."""
    t0 = time.perf_counter()
    try:
        res = plaq_quantum.simulation.run_circuit_simulation(
            workload=params.workload,
            qubits=params.qubits,
            qasm=params.qasm,
            bitstring=params.bitstring,
            shots=params.shots,
            seed=params.seed,
            compute_energy=params.compute_energy,
        )
        data = res.to_dict()
        data["summary"] = (
            f"Circuit simulation ({res.mode}): n={res.num_qubits} depth={res.depth} "
            f"top={res.top_bitstrings[:3]}"
        )
        return _ok(t0, data)
    except Exception as exc:
        return _err(t0, exc)


def quantum_optimize(params: QuantumOptimizeParams, context: Any) -> ToolResult:
    """Pareto co-design search over compiler / factories / decoder / QEC."""
    t0 = time.perf_counter()
    try:
        qc = resolve_circuit(workload=params.workload, qubits=params.qubits)
        hw = plaq_quantum.hardware.get_hardware_profile(params.hardware_profile)
        _, pareto = plaq_quantum.optimizer.search_pareto_optimizer(
            circuit=qc,
            hardware=hw,
            target_epsilon=params.target_epsilon,
            candidate_limit=params.candidate_limit,
        )
        rows = [p.to_row() for p in pareto]
        return _ok(
            t0,
            {
                "hardware": hw.name,
                "workload": params.workload,
                "pareto_points": len(rows),
                "frontier": rows,
                "summary": f"Pareto frontier: {len(rows)} non-dominated plans on {hw.name}",
            },
        )
    except Exception as exc:
        return _err(t0, exc)


def quantum_baselines(params: QuantumBaselinesParams, context: Any) -> ToolResult:
    """Four-baselines co-design protocol."""
    t0 = time.perf_counter()
    try:
        qc = resolve_circuit(workload=params.workload, qubits=params.qubits)
        hw = plaq_quantum.hardware.get_hardware_profile(params.hardware_profile)
        records = plaq_quantum.baselines.run_four_baselines_protocol(
            circuit=qc, hardware=hw, target_epsilon=params.target_epsilon
        )
        return _ok(
            t0,
            {
                "hardware": hw.name,
                "workload": params.workload,
                "comparisons": [asdict(r) for r in records],
                "summary": f"Four-baselines protocol completed ({len(records)} records)",
            },
        )
    except Exception as exc:
        return _err(t0, exc)


def quantum_threshold(params: QuantumThresholdParams, context: Any) -> ToolResult:
    """Stim surface-code threshold sweep."""
    t0 = time.perf_counter()
    try:
        results = plaq_quantum.stim_bridge.run_threshold_study(
            distances=params.distances or [3],
            physical_error_rates=params.physical_error_rates or [0.001, 0.01],
            shots_per_point=params.shots_per_point,
        )
        return _ok(
            t0,
            {
                "samples": [asdict(r) for r in results],
                "summary": f"Threshold study: {len(results)} (d, p) samples",
            },
        )
    except Exception as exc:
        return _err(t0, exc)


def quantum_qasm(params: QuantumQasmParams, context: Any) -> ToolResult:
    """Compile an OpenQASM 2.0 body and extract metrics."""
    compile_params = QuantumCompileParams(qasm=params.qasm)
    return quantum_compile(compile_params, context)


def quantum_workloads(params: QuantumWorkloadsParams, context: Any) -> ToolResult:
    """List named workloads agents can compile / simulate / optimize."""
    t0 = time.perf_counter()
    try:
        return _ok(t0, {"workloads": list_workloads()})
    except Exception as exc:
        return _err(t0, exc)


def quantum_hardware(params: QuantumHardwareParams, context: Any) -> ToolResult:
    """List calibrated hardware profiles."""
    t0 = time.perf_counter()
    try:
        return _ok(t0, {"profiles": list_hardware_profiles()})
    except Exception as exc:
        return _err(t0, exc)
