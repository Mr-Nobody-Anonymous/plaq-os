"""
Q-Day OS Benchmark Suite

Executes reproducible transpilation baselines across multiple compiler
optimization levels, connectivity graphs, and workload families.
Produces benchmark_results.csv and summary statistics.
"""

from __future__ import annotations
import os
import sys
from time import perf_counter
from typing import List, Dict, Any, Optional
import pandas as pd

from circuits import make_test_circuit, get_benchmark_workloads
from hardware import HardwareModel, DEMO_HARDWARE, HARDWARE_CATALOG
from cost_model import extract_circuit_metrics, evaluate_fault_tolerant_cost

try:
    from qiskit import transpile, QuantumCircuit
    from qiskit.transpiler import CouplingMap
    HAS_QISKIT = True
except ImportError:
    HAS_QISKIT = False


def run_compiler_baseline(
    circuit: QuantumCircuit,
    hardware: HardwareModel = DEMO_HARDWARE,
    seed_transpiler: int = 42,
    target_epsilon: float = 1e-3,
) -> pd.DataFrame:
    """
    Benchmark Qiskit's transpiler across optimization levels 0, 1, 2, 3
    under target hardware connectivity and basis gates.
    """
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required to run transpiler baselines.")

    edges = hardware.get_coupling_edges(circuit.num_qubits)
    coupling_map = CouplingMap(edges)

    rows: List[Dict[str, Any]] = []

    for level in range(4):
        start_time = perf_counter()
        compiled = transpile(
            circuit,
            coupling_map=coupling_map,
            basis_gates=list(hardware.basis_gates),
            optimization_level=level,
            seed_transpiler=seed_transpiler,
        )
        compilation_time = perf_counter() - start_time

        metrics = extract_circuit_metrics(compiled)

        ft_cost = evaluate_fault_tolerant_cost(
            metrics=metrics,
            hardware=hardware,
            target_epsilon=target_epsilon,
            num_magic_factories=2,
        )

        rows.append({
            "optimization_level": level,
            "logical_qubits": compiled.num_qubits,
            "circuit_depth": metrics.depth,
            "total_ops": metrics.total_ops,
            "two_qubit_cx_ops": metrics.two_qubit_ops,
            "single_qubit_ops": metrics.single_qubit_ops,
            "t_ops": metrics.t_ops,
            "compilation_time_s": round(compilation_time, 5),
            "ft_valid": ft_cost.valid,
            "ft_physical_qubits": ft_cost.physical_qubits,
            "ft_runtime_s": round(ft_cost.runtime_seconds, 6),
            "ft_code_distance": ft_cost.code_distance,
            "ft_failure_prob": ft_cost.failure_probability,
            "decoder_stall": ft_cost.decoder_stall_factor,
        })

    return pd.DataFrame(rows)


def run_full_benchmark_suite(
    output_dir: str = "results",
    hardware_name: str = "superconducting",
    target_epsilon: float = 1e-3,
) -> pd.DataFrame:
    """Run benchmarks over all standard workloads in the catalog and save to CSV."""
    os.makedirs(output_dir, exist_ok=True)
    hardware = HARDWARE_CATALOG.get(hardware_name, DEMO_HARDWARE)
    workloads = get_benchmark_workloads()

    all_results: List[pd.DataFrame] = []

    print(f"\n=======================================================", flush=True)
    print(f"  Q-Day OS: Running Compiler & Fault-Tolerant Baselines", flush=True)
    print(f"  Hardware: {hardware.name} ({hardware.technology})", flush=True)
    print(f"  Target Reliability Budget: epsilon = {target_epsilon}", flush=True)
    print(f"=======================================================\n", flush=True)

    for w_name, qc in workloads.items():
        print(f"[*] Benchmarking workload: {w_name} ({qc.num_qubits} qubits)...", flush=True)
        df = run_compiler_baseline(
            circuit=qc,
            hardware=hardware,
            seed_transpiler=42,
            target_epsilon=target_epsilon,
        )
        df.insert(0, "workload", w_name)
        all_results.append(df)

    final_df = pd.concat(all_results, ignore_index=True)
    csv_path = os.path.join(output_dir, "benchmark_results.csv")
    final_df.to_csv(csv_path, index=False)
    print(f"\n[+] Successfully saved benchmark results to: {csv_path}", flush=True)

    summary_cols = [
        "workload", "optimization_level", "circuit_depth", "two_qubit_cx_ops",
        "ft_physical_qubits", "ft_runtime_s", "ft_code_distance", "compilation_time_s"
    ]
    print("\n--- Benchmark Baseline Summary ---", flush=True)
    print(final_df[summary_cols].to_string(index=False), flush=True)
    return final_df


if __name__ == "__main__":
    hw_choice = sys.argv[1] if len(sys.argv) > 1 else "superconducting"
    run_full_benchmark_suite(hardware_name=hw_choice)
