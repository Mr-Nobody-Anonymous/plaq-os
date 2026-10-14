"""Quantum compilation, resource estimation, and benchmarking contracts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from .common import PlaqBaseModel, generate_id


class QuantumCompileRequest(PlaqBaseModel):
    """Request to compile a quantum workload against a hardware profile."""

    workload: Optional[str] = Field(default="test_circuit", description="Name of workload")
    qubits: int = Field(default=4, ge=1, le=1000)
    bitstring: Optional[str] = None
    depth: Optional[int] = None
    qasm: Optional[str] = None
    target_hardware: Optional[str] = "superconducting_heron"
    optimization_level: int = Field(default=1, ge=0, le=3)


class QuantumEstimateRequest(PlaqBaseModel):
    """Request analytical fault-tolerant resource estimation."""

    qubits: int = Field(default=4, ge=1, le=1000)
    physical_error_rate: float = Field(default=0.001, gt=0.0, lt=1.0)
    error_budget: float = Field(default=1e-3, gt=0.0, lt=1.0)
    threshold: float = Field(default=0.01, gt=0.0, lt=1.0)
    spacetime_volume: Optional[float] = None
    hardware_profile: Optional[str] = "superconducting_heron"
    circuit_name: Optional[str] = None


class QuantumBenchmarkRequest(PlaqBaseModel):
    """Request comparative search algorithm and Pareto benchmark suite."""

    workloads: List[str] = Field(default_factory=lambda: ["qaoa", "qft", "bv"])
    hardware_profiles: List[str] = Field(default_factory=lambda: ["superconducting_heron", "trapped_ion_quantinuum"])
    search_methods: List[str] = Field(default_factory=lambda: ["greedy", "simulated_annealing", "pareto"])
    budget_evaluations: int = Field(default=50, ge=1)


class QuantumResult(PlaqBaseModel):
    """Standardized response from compilation, estimation, or optimization."""

    request_id: str = Field(default_factory=generate_id)
    num_qubits: int
    code_distance: int
    physical_qubits: Optional[int] = None
    t_count: int = 0
    circuit_depth: int = 0
    estimated_runtime_sec: float = 0.0
    feasible: bool = True
    pareto_points: Optional[List[Dict[str, Any]]] = None
    metrics: Optional[Dict[str, Any]] = None
    manifest: Optional[Dict[str, Any]] = None
