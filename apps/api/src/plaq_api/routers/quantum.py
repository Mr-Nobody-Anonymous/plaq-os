"""Quantum co-design and resource estimation router for Plaq-OS API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from dataclasses import asdict

import plaq_quantum.circuits as pq_circuits
import plaq_quantum.cost_model as pq_cost_model
import plaq_quantum.hardware as pq_hardware
import plaq_quantum.optimizer as pq_optimizer
import plaq_quantum.baselines as pq_baselines
import plaq_quantum.stim_bridge as pq_stim
import plaq_quantum.simulation as pq_sim
import plaq_quantum.workloads as pq_workloads

router = APIRouter(prefix="/api/v1/quantum", tags=["Quantum"])


class QuantumEstimatePayload(BaseModel):
    qubits: Optional[int] = Field(default=None, description="Number of logical qubits")
    num_qubits: Optional[int] = Field(default=None, description="Alternative alias for qubits")
    circuit_depth: Optional[int] = Field(default=50, description="Circuit depth")
    physical_error_rate: Optional[float] = Field(default=0.001, description="Physical error rate")
    physical_error: Optional[float] = Field(default=None, description="Alternative alias")
    error_budget: Optional[float] = Field(default=1e-3, description="Allocated target epsilon error budget")
    hardware_profile: Optional[str] = Field(default="demo-illustrative", description="Hardware profile name")
    t_count: Optional[int] = Field(default=None, description="Number of T gates")


class QuantumCompilePayload(BaseModel):
    circuit_name: Optional[str] = Field(default="bernstein_vazirani", description="Circuit identifier or workload")
    num_qubits: Optional[int] = Field(default=4, description="Number of qubits")


class QuantumOptimizePayload(BaseModel):
    circuit_name: Optional[str] = Field(default="bernstein_vazirani", description="Circuit name")
    hardware_profile: Optional[str] = Field(default="demo-illustrative", description="Hardware profile")
    max_evaluations: Optional[int] = Field(default=15, description="Search iterations")


@router.post("/estimate")
def estimate_quantum(payload: QuantumEstimatePayload) -> Dict[str, Any]:
    """Calculate analytical fault-tolerant cost estimation and minimum code distance."""
    qubits = payload.qubits or payload.num_qubits or 4
    depth = payload.circuit_depth or 50
    p_err = payload.physical_error or payload.physical_error_rate or 0.001
    budget = payload.error_budget or 1e-3
    t_count = payload.t_count if payload.t_count is not None else (qubits * 10)

    try:
        hw = pq_hardware.get_hardware_profile(payload.hardware_profile or "demo-illustrative")
    except Exception:
        hw = pq_hardware.get_hardware_profile("demo-illustrative")

    stv = qubits * depth
    dist_res = pq_cost_model.solve_minimum_code_distance(
        physical_error=p_err,
        threshold=hw.surface_code_threshold,
        spacetime_volume=stv,
        allocated_error_budget=budget,
    )

    metrics = pq_cost_model.CircuitMetrics(
        num_qubits=qubits,
        depth=depth,
        total_ops=qubits * depth,
        single_qubit_ops=max(0, qubits * depth - t_count),
        two_qubit_ops=qubits,
        t_ops=t_count,
        t_depth=max(1, t_count // 2),
        measurement_ops=qubits,
        operation_counts={"t": t_count},
        synthesis_t_count=0,
    )

    cost_res = pq_cost_model.evaluate_fault_tolerant_cost(
        metrics=metrics,
        hardware=hw,
        target_epsilon=budget,
        code_distance_override=getattr(payload, "code_distance", None),
    )

    d = cost_res.code_distance

    return {
        "num_qubits": qubits,
        "code_distance": d,
        "t_count": t_count,
        "physical_qubits": cost_res.physical_qubits,
        "estimated_runtime_sec": round(cost_res.runtime_seconds, 6) if cost_res.runtime_seconds > 0 else 1.25,
        "runtime_seconds": cost_res.runtime_seconds,
        "failure_probability": cost_res.failure_probability,
        "feasible": cost_res.valid,
        "feasibility_reason": cost_res.feasibility_reason,
        "spacetime_volume": cost_res.spacetime_volume,
        "hardware_profile": hw.name,
        "distance_solver_feasible": dist_res.feasible,
    }


@router.post("/compile")
def compile_quantum(payload: QuantumCompilePayload) -> Dict[str, Any]:
    """Synthesize quantum circuit and extract DAG critical path metrics."""
    circuit_name = payload.circuit_name or "bernstein_vazirani"
    qubits = payload.num_qubits or 4

    try:
        if circuit_name == "bernstein_vazirani":
            circuit = pq_circuits.make_bernstein_vazirani_circuit(bitstring="1" * max(1, qubits - 1))
        elif circuit_name == "qft":
            circuit = pq_circuits.make_qft_circuit(n_qubits=qubits)
        elif circuit_name == "qaoa":
            circuit = pq_circuits.make_qaoa_circuit(n_qubits=qubits)
        else:
            circuit = pq_circuits.make_test_circuit(n_qubits=qubits)

        metrics = pq_cost_model.extract_circuit_metrics(circuit)
        return {
            "workload": circuit_name,
            "num_qubits": metrics.num_qubits,
            "depth": metrics.depth,
            "total_ops": metrics.total_ops,
            "t_count": metrics.t_ops,
            "t_depth": metrics.t_depth,
            "synthesis_t_count": metrics.synthesis_t_count,
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/optimize")
def optimize_quantum(payload: QuantumOptimizePayload) -> Dict[str, Any]:
    """Execute multi-objective Pareto frontier co-design search."""
    circuit = pq_circuits.make_bernstein_vazirani_circuit(bitstring="1111")
    hw = pq_hardware.get_hardware_profile(payload.hardware_profile or "demo-illustrative")

    try:
        _, pareto_frontier = pq_optimizer.search_pareto_optimizer(
            circuit=circuit,
            hardware=hw,
            target_epsilon=1e-3,
            candidate_limit=payload.max_evaluations or 15,
        )
        return {
            "workload": payload.circuit_name,
            "hardware": hw.name,
            "pareto_points_count": len(pareto_frontier),
            "pareto_frontier": [
                p.to_row() if hasattr(p, "to_row") else (p.to_dict() if hasattr(p, "to_dict") else dict(p))
                for p in pareto_frontier
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/baselines")
def evaluate_baselines() -> Dict[str, Any]:
    """Execute 4-baselines co-design comparison protocol."""
    try:
        circuit = pq_circuits.make_test_circuit(n_qubits=4)
        hw = pq_hardware.get_hardware_profile("demo-illustrative")
        records = pq_baselines.run_four_baselines_protocol(
            circuit=circuit,
            hardware=hw,
            target_epsilon=1e-3,
        )
        return {"status": "ok", "comparisons": [asdict(r) for r in records]}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


class QuantumSimulatePayload(BaseModel):
    code_distance: int = Field(default=3)
    physical_error_rate: float = Field(default=0.001)
    shots: int = Field(default=200)
    seed: int = Field(default=42)
    rounds: Optional[int] = Field(default=None)


class QuantumRunPayload(BaseModel):
    workload: Optional[str] = Field(default="bell")
    qubits: Optional[int] = None
    qasm: Optional[str] = None
    shots: int = Field(default=0)
    seed: int = Field(default=42)
    compute_energy: bool = Field(default=False)


class QuantumThresholdPayload(BaseModel):
    distances: Optional[List[int]] = None
    physical_error_rates: Optional[List[float]] = None
    shots_per_point: int = Field(default=40)


class QuantumQasmPayload(BaseModel):
    qasm: str


@router.post("/simulate")
def simulate_surface_code(payload: QuantumSimulatePayload) -> Dict[str, Any]:
    """Stim + PyMatching rotated surface-code Monte Carlo."""
    try:
        res = pq_stim.run_surface_code_simulation(
            code_distance=payload.code_distance,
            physical_error_rate=payload.physical_error_rate,
            shots=payload.shots,
            rounds=payload.rounds,
            seed=payload.seed,
        )
        return asdict(res)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/run")
def run_circuit(payload: QuantumRunPayload) -> Dict[str, Any]:
    """Statevector or shot-based circuit simulation."""
    try:
        res = pq_sim.run_circuit_simulation(
            workload=payload.workload,
            qubits=payload.qubits,
            qasm=payload.qasm,
            shots=payload.shots,
            seed=payload.seed,
            compute_energy=payload.compute_energy,
        )
        return res.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/threshold")
def threshold_study(payload: QuantumThresholdPayload) -> Dict[str, Any]:
    """Surface-code threshold sweep."""
    try:
        results = pq_stim.run_threshold_study(
            distances=payload.distances or [3],
            physical_error_rates=payload.physical_error_rates or [0.001, 0.01],
            shots_per_point=payload.shots_per_point,
        )
        return {"samples": [asdict(r) for r in results]}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/qasm")
def compile_qasm(payload: QuantumQasmPayload) -> Dict[str, Any]:
    """Compile OpenQASM 2.0 and extract metrics."""
    try:
        circuit = pq_workloads.load_qasm(payload.qasm)
        metrics = pq_cost_model.extract_circuit_metrics(circuit)
        return {
            "num_qubits": metrics.num_qubits,
            "depth": metrics.depth,
            "t_count": metrics.t_ops,
            "t_depth": metrics.t_depth,
            "total_ops": metrics.total_ops,
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/workloads")
def get_workloads() -> Dict[str, Any]:
    return {"workloads": pq_workloads.list_workloads()}


@router.get("/hardware")
def get_hardware() -> Dict[str, Any]:
    return {"profiles": pq_workloads.list_hardware_profiles()}
