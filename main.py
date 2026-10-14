"""
Q-Day OS: Fault-Tolerant Quantum Execution Planner & Resource Optimizer
CLI Entrypoint & Research Pipeline Runner

Usage:
  python main.py --run-all
  python main.py --benchmark
  python main.py --optimize --workload chemistry_femoco_6q
  python main.py --compare --hardware superconducting
  python main.py --dashboard
  python main.py --plot
"""

from __future__ import annotations
import os
import sys
import argparse
import json
import pandas as pd
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from hardware import HARDWARE_CATALOG, DEMO_HARDWARE, HardwareModel
from circuits import get_benchmark_workloads, make_test_circuit
from benchmark import run_full_benchmark_suite
from optimizer import (
    search_pareto_optimizer,
    compare_sequential_vs_joint,
    ExecutionPlan,
    EvaluatedPlan,
    CompilationCache,
)
from dashboard import generate_html_dashboard
from baselines import run_four_baselines_protocol, run_ablation_study
from search_algorithms import benchmark_search_methods
from server import start_quantum_server


def export_pareto_plot(
    evaluated_plans: list[EvaluatedPlan],
    pareto_plans: list[EvaluatedPlan],
    output_path: str = "results/pareto_frontier.png",
    workload_name: str = "Workload",
) -> None:
    """Generate publication-grade scatter plot illustrating the Pareto frontier."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 6), dpi=150)

    all_valid = [p for p in evaluated_plans if p.valid]
    if all_valid:
        x_all = [p.runtime_seconds * 1e3 for p in all_valid]
        y_all = [p.physical_qubits for p in all_valid]
        ax.scatter(
            x_all, y_all,
            color="#94a3b8", alpha=0.6, s=40,
            label="Candidate Plans (Dominated)",
            edgecolors="none",
        )

    if pareto_plans:
        sorted_pareto = sorted(pareto_plans, key=lambda p: p.runtime_seconds)
        x_p = [p.runtime_seconds * 1e3 for p in sorted_pareto]
        y_p = [p.physical_qubits for p in sorted_pareto]

        ax.plot(x_p, y_p, "--", color="#2563eb", alpha=0.7, linewidth=1.5)
        ax.scatter(
            x_p, y_p,
            color="#dc2626", s=85,
            label="Pareto Frontier (Non-dominated)",
            zorder=5, edgecolors="#991b1b", linewidth=1.5,
        )

        for i, p in enumerate(sorted_pareto):
            label_text = f"P{i+1}: f={p.plan.num_magic_factories}, {p.plan.decoder_architecture[:5]}"
            ax.annotate(
                label_text,
                (p.runtime_seconds * 1e3, p.physical_qubits),
                textcoords="offset points",
                xytext=(8, 5),
                fontsize=8,
                color="#1e293b",
                fontweight="medium",
            )

    ax.set_title(f"Q-Day OS Pareto Trade-off: {workload_name}", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Wall-Clock Execution Runtime (ms)", fontsize=11)
    ax.set_ylabel("Total Physical Qubits ($Q_{data} + Q_{factories}$)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(frameon=True, facecolor="white", framealpha=0.9)

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    print(f"[+] Saved Pareto frontier visualization to: {output_path}", flush=True)


def run_optimization_action(args: argparse.Namespace, cache: CompilationCache | None = None) -> None:
    """Run cross-layer joint optimization and display Pareto frontier."""
    workloads = get_benchmark_workloads()
    w_name = args.workload if args.workload in workloads else "test_rz_cx_5q"
    circuit = workloads[w_name]
    hardware = HARDWARE_CATALOG.get(args.hardware, DEMO_HARDWARE)
    if cache is None:
        cache = CompilationCache()

    print(f"\n=======================================================", flush=True)
    print(f"  Q-Day OS: Joint Cross-Layer Optimization", flush=True)
    print(f"  Workload: {w_name} ({circuit.num_qubits} qubits)", flush=True)
    print(f"  Hardware: {hardware.name}", flush=True)
    print(f"  Target Reliability Budget: epsilon = {args.epsilon}", flush=True)
    print(f"=======================================================\n", flush=True)

    print("[*] Generating candidate execution space and searching Pareto frontier...", flush=True)
    all_evaluated, pareto_frontier = search_pareto_optimizer(
        circuit=circuit,
        hardware=hardware,
        target_epsilon=args.epsilon,
        compilation_cache=cache,
    )

    print(f"[+] Evaluated {len(all_evaluated)} configurations.", flush=True)
    print(f"[+] Discovered {len(pareto_frontier)} Pareto-optimal execution plans!\n", flush=True)

    if pareto_frontier:
        pareto_rows = [p.to_row() for p in pareto_frontier]
        df_pareto = pd.DataFrame(pareto_rows)
        disp_cols = [
            "opt_level", "routing", "factories", "decoder",
            "physical_qubits", "runtime_s", "code_distance", "failure_prob"
        ]
        print(df_pareto[disp_cols].to_string(index=False), flush=True)

        os.makedirs("results", exist_ok=True)
        json_path = f"results/pareto_{w_name}.json"
        with open(json_path, "w") as f:
            json.dump([p.to_row() for p in pareto_frontier], f, indent=2)
        print(f"\n[+] Exported Pareto frontier JSON to: {json_path}", flush=True)

        plot_path = f"results/pareto_{w_name}.png"
        export_pareto_plot(
            evaluated_plans=all_evaluated,
            pareto_plans=pareto_frontier,
            output_path=plot_path,
            workload_name=w_name,
        )


def run_comparison_action(args: argparse.Namespace, cache: CompilationCache | None = None) -> None:
    """Compare Sequential Baseline vs Q-Day OS Joint Optimizer."""
    workloads = get_benchmark_workloads()
    hardware = HARDWARE_CATALOG.get(args.hardware, DEMO_HARDWARE)
    if cache is None:
        cache = CompilationCache()

    print(f"\n=======================================================", flush=True)
    print(f"  Q-Day OS: Hypothesis Testing & Baseline Comparison", flush=True)
    print(f"  Hypothesis: Joint cross-layer optimization reduces", flush=True)
    print(f"              execution cost vs sequential compilation.", flush=True)
    print(f"  Hardware: {hardware.name}", flush=True)
    print(f"  Target Reliability Budget: epsilon = {args.epsilon}", flush=True)
    print(f"=======================================================\n", flush=True)

    target_workloads = [args.workload] if args.workload != "all" and args.workload in workloads else list(workloads.keys())

    comparison_results = []
    for w_name in target_workloads:
        qc = workloads[w_name]
        print(f"[*] Testing workload: {w_name}...", flush=True)
        res = compare_sequential_vs_joint(
            circuit=qc,
            hardware=hardware,
            target_epsilon=args.epsilon,
            compilation_cache=cache,
        )
        res["workload"] = w_name
        comparison_results.append(res)

    print("\n-------------------------------------------------------------", flush=True)
    print("  RESEARCH HYPOTHESIS TEST RESULTS", flush=True)
    print("-------------------------------------------------------------", flush=True)
    for r in comparison_results:
        seq = r["sequential_baseline"]
        joint = r["joint_optimized"]
        print(f"\nWorkload: {r['workload']}", flush=True)
        print(f"  Sequential Baseline: Qubits = {seq['physical_qubits']}, Runtime = {seq['runtime_s']}s (Opt Level {seq['opt_level']}, {seq['decoder']})", flush=True)
        print(f"  Joint Optimized:     Qubits = {joint['physical_qubits']}, Runtime = {joint['runtime_s']}s (Opt Level {joint['opt_level']}, {joint['factories']} factories, {joint['decoder']})", flush=True)
        print(f"  -> Physical Qubit Delta: {r['qubit_savings']} qubits", flush=True)
        print(f"  -> Runtime Speedup:      {r['runtime_speedup']}x", flush=True)
        print(f"  -> Relative Cost Reduction: {r['relative_cost_reduction_percent']}%", flush=True)

    os.makedirs("results", exist_ok=True)
    with open("results/hypothesis_comparison.json", "w") as f:
        json.dump(comparison_results, f, indent=2)
    print(f"\n[+] Saved hypothesis comparison report to results/hypothesis_comparison.json", flush=True)


def run_baselines_action(args: argparse.Namespace, cache: CompilationCache | None = None) -> None:
    """Run Section 9 Four-Baselines comparative protocol."""
    workloads = get_benchmark_workloads()
    hardware = HARDWARE_CATALOG.get(args.hardware, DEMO_HARDWARE)
    if cache is None:
        cache = CompilationCache()

    target_qc = workloads.get(args.workload, workloads["chemistry_femoco_6q"])
    print(f"\n=======================================================", flush=True)
    print(f"  Q-Day OS: Four-Baselines Comparative Protocol", flush=True)
    print(f"  Workload: {args.workload} | Hardware: {hardware.name}", flush=True)
    print(f"=======================================================\n", flush=True)

    records = run_four_baselines_protocol(target_qc, hardware, args.epsilon, compilation_cache=cache)
    for r in records:
        print(f"[{r.baseline_id}] {r.baseline_name:<30} | Qubits: {r.physical_qubits:<6} | Runtime: {r.runtime_seconds*1000:>7.2f}ms | Cost: {r.total_cost_score:>8.1f} | Delta vs Base: {r.relative_reduction_vs_compiler}%", flush=True)

    os.makedirs("results", exist_ok=True)
    with open("results/baselines_comparison.json", "w") as f:
        json.dump([r.__dict__ for r in records], f, indent=2)
    print(f"\n[+] Saved baselines report to results/baselines_comparison.json", flush=True)


def run_ablation_action(args: argparse.Namespace, cache: CompilationCache | None = None) -> None:
    """Run Section 8 systematic ablation study."""
    workloads = get_benchmark_workloads()
    hardware = HARDWARE_CATALOG.get(args.hardware, DEMO_HARDWARE)
    if cache is None:
        cache = CompilationCache()

    target_qc = workloads.get(args.workload, workloads["chemistry_femoco_6q"])
    print(f"\n=======================================================", flush=True)
    print(f"  Q-Day OS: Systematic Ablation Study", flush=True)
    print(f"  Workload: {args.workload} | Hardware: {hardware.name}", flush=True)
    print(f"=======================================================\n", flush=True)

    records = run_ablation_study(target_qc, hardware, args.epsilon, compilation_cache=cache)
    for r in records:
        print(f"[*] {r.configuration_name:<30} | Cost: {r.total_cost_score:>8.1f} | Penalty: +{r.cost_penalty_percent:>5.1f}% | {r.disabled_component}", flush=True)

    os.makedirs("results", exist_ok=True)
    with open("results/ablation_study.json", "w") as f:
        json.dump([r.__dict__ for r in records], f, indent=2)
    print(f"\n[+] Saved ablation report to results/ablation_study.json", flush=True)


def run_search_bench_action(args: argparse.Namespace, cache: CompilationCache | None = None) -> None:
    """Run search algorithms comparative evaluation."""
    workloads = get_benchmark_workloads()
    hardware = HARDWARE_CATALOG.get(args.hardware, DEMO_HARDWARE)
    if cache is None:
        cache = CompilationCache()

    target_qc = workloads.get(args.workload, workloads["chemistry_femoco_6q"])
    print(f"\n=======================================================", flush=True)
    print(f"  Q-Day OS: Search Algorithms Benchmark Suite", flush=True)
    print(f"  Workload: {args.workload} | Hardware: {hardware.name}", flush=True)
    print(f"=======================================================\n", flush=True)

    records = benchmark_search_methods(target_qc, hardware, args.epsilon, compilation_cache=cache)
    for r in records:
        print(f"[*] {r.algorithm_name:<25} | Time: {r.search_time_seconds:>6.3f}s | Evals: {r.total_evaluations:>3} | Cost: {r.best_cost_score:>8.1f} | Regret: {r.optimality_gap_percent:>5.1f}% | Coverage: {r.pareto_coverage_percent:>5.1f}%", flush=True)

    os.makedirs("results", exist_ok=True)
    with open("results/search_benchmarks.json", "w") as f:
        json.dump([r.__dict__ for r in records], f, indent=2)
    print(f"\n[+] Saved search benchmark report to results/search_benchmarks.json", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Q-Day OS: Fault-Tolerant Quantum Execution Planner & Resource Optimizer"
    )
    parser.add_argument("--run-all", action="store_true", help="Execute complete R&D research workflow today")
    parser.add_argument("--benchmark", action="store_true", help="Run compiler baseline benchmarks")
    parser.add_argument("--optimize", action="store_true", help="Run joint cross-layer Pareto optimization")
    parser.add_argument("--compare", action="store_true", help="Compare Sequential baseline vs Joint Optimizer")
    parser.add_argument("--baselines", action="store_true", help="Run 4-Baselines comparative protocol")
    parser.add_argument("--ablation", action="store_true", help="Run systematic ablation study")
    parser.add_argument("--search-bench", action="store_true", help="Benchmark optimization search algorithms")
    parser.add_argument("--dashboard", action="store_true", help="Generate executive HTML interactive dashboard")
    parser.add_argument("--ui", action="store_true", help="Launch interactive cyber-quantum mission control web UI")
    parser.add_argument("--port", type=int, default=8500, help="Web server port for UI")
    parser.add_argument("--workload", type=str, default="chemistry_femoco_6q", help="Target workload or 'all'")
    parser.add_argument("--hardware", type=str, default="superconducting", choices=list(HARDWARE_CATALOG.keys()))
    parser.add_argument("--epsilon", type=float, default=1e-3, help="Maximum acceptable failure probability")

    args = parser.parse_args()

    if not any([args.run_all, args.benchmark, args.optimize, args.compare, args.baselines, args.ablation, args.search_bench, args.dashboard, args.ui]):
        args.run_all = True

    shared_cache = CompilationCache()

    if args.ui:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{args.port}")
        start_quantum_server(port=args.port)
        return

    if args.run_all:
        print("\n>>> STARTING COMPLETE 1-DAY RESEARCH & DEVELOPMENT RUN <<<\n", flush=True)
        run_full_benchmark_suite(hardware_name=args.hardware, target_epsilon=args.epsilon)
        run_optimization_action(args, cache=shared_cache)
        run_comparison_action(args, cache=shared_cache)
        run_baselines_action(args, cache=shared_cache)
        run_ablation_action(args, cache=shared_cache)
        run_search_bench_action(args, cache=shared_cache)
        generate_html_dashboard()
        print("\n>>> COMPLETE 1-DAY WORKFLOW COMPLETED SUCCESSFULLY! <<<\n", flush=True)
    else:
        if args.benchmark:
            run_full_benchmark_suite(hardware_name=args.hardware, target_epsilon=args.epsilon)
        if args.optimize:
            run_optimization_action(args, cache=shared_cache)
        if args.compare:
            run_comparison_action(args, cache=shared_cache)
        if args.baselines:
            run_baselines_action(args, cache=shared_cache)
        if args.ablation:
            run_ablation_action(args, cache=shared_cache)
        if args.search_bench:
            run_search_bench_action(args, cache=shared_cache)
        if args.dashboard:
            generate_html_dashboard()


if __name__ == "__main__":
    main()
