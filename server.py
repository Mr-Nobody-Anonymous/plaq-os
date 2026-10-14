"""
Q-Day OS Futuristic Quantum Web Server & REST API

Provides a local HTTP server and REST endpoints for the interactive UI:
- /api/optimize: Dynamic Pareto optimization
- /api/baselines: Four-Baselines comparative evaluation
- /api/ablation: Layer ablation analysis
- /api/search-bench: Search algorithms benchmark (Exhaustive, Greedy, Annealing, Random)
- /api/workloads & /api/hardware: Metadata providers
- Static file serving of the futuristic cyber-quantum UI
"""

from __future__ import annotations
import os
import sys
import json
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Dict, Any, List

from hardware import HARDWARE_CATALOG, DEMO_HARDWARE
from circuits import get_benchmark_workloads, make_test_circuit
from optimizer import (
    search_pareto_optimizer,
    compare_sequential_vs_joint,
    ExecutionPlan,
    CompilationCache,
)
from baselines import run_four_baselines_protocol, run_ablation_study
from search_algorithms import benchmark_search_methods

SHARED_CACHE = CompilationCache()
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


class QuantumApiHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving the cool UI and interactive REST endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=UI_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/metadata":
            self.send_json_response({
                "workloads": list(get_benchmark_workloads().keys()),
                "hardware": [
                    {"id": k, "name": v.name, "tech": v.technology, "threshold": v.surface_code_threshold}
                    for k, v in HARDWARE_CATALOG.items()
                ],
                "search_algorithms": ["Exhaustive Grid", "Greedy Coordinate", "Simulated Annealing", "Random Search"],
            })
        elif parsed.path in ("/", "/index.html"):
            index_path = os.path.join(UI_DIR, "index.html")
            if os.path.exists(index_path):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(index_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(post_data) if post_data else {}
        except Exception:
            payload = {}

        w_name = payload.get("workload", "chemistry_femoco_6q")
        hw_name = payload.get("hardware", "superconducting")
        epsilon = float(payload.get("epsilon", 1e-3))

        workloads = get_benchmark_workloads()
        circuit = workloads.get(w_name, workloads["test_rz_cx_5q"])
        hardware = HARDWARE_CATALOG.get(hw_name, DEMO_HARDWARE)

        if parsed.path == "/api/optimize":
            all_evals, pareto_frontier = search_pareto_optimizer(
                circuit=circuit,
                hardware=hardware,
                target_epsilon=epsilon,
                compilation_cache=SHARED_CACHE,
            )
            resp = {
                "workload": w_name,
                "hardware": hardware.name,
                "total_evaluated": len(all_evals),
                "pareto_count": len(pareto_frontier),
                "all_plans": [p.to_row() for p in all_evals if p.valid],
                "pareto_plans": [p.to_row() for p in pareto_frontier],
            }
            self.send_json_response(resp)

        elif parsed.path == "/api/baselines":
            records = run_four_baselines_protocol(
                circuit=circuit,
                hardware=hardware,
                target_epsilon=epsilon,
                compilation_cache=SHARED_CACHE,
            )
            self.send_json_response({
                "workload": w_name,
                "hardware": hardware.name,
                "records": [
                    {
                        "id": r.baseline_id,
                        "name": r.baseline_name,
                        "description": r.description,
                        "physical_qubits": r.physical_qubits,
                        "runtime_s": round(r.runtime_seconds, 6),
                        "code_distance": r.code_distance,
                        "failure_prob": f"{r.failure_probability:.2e}",
                        "decoder_stall": round(r.decoder_stall_factor, 2),
                        "total_cost": round(r.total_cost_score, 2),
                        "reduction_vs_original": r.relative_reduction_vs_original,
                        "reduction_vs_compiler": r.relative_reduction_vs_compiler,
                    }
                    for r in records
                ],
            })

        elif parsed.path == "/api/ablation":
            abl_records = run_ablation_study(
                circuit=circuit,
                hardware=hardware,
                target_epsilon=epsilon,
                compilation_cache=SHARED_CACHE,
            )
            self.send_json_response({
                "workload": w_name,
                "records": [
                    {
                        "name": a.configuration_name,
                        "disabled": a.disabled_component,
                        "qubits": a.physical_qubits,
                        "runtime_s": a.runtime_seconds,
                        "code_distance": a.code_distance,
                        "total_cost": a.total_cost_score,
                        "penalty_percent": a.cost_penalty_percent,
                    }
                    for a in abl_records
                ],
            })

        elif parsed.path == "/api/search-bench":
            search_records = benchmark_search_methods(
                circuit=circuit,
                hardware=hardware,
                target_epsilon=epsilon,
                compilation_cache=SHARED_CACHE,
            )
            self.send_json_response({
                "workload": w_name,
                "records": [
                    {
                        "algorithm": s.algorithm_name,
                        "time_s": s.search_time_seconds,
                        "evaluations": s.total_evaluations,
                        "best_cost": s.best_cost_score,
                        "qubits": s.best_physical_qubits,
                        "runtime_s": s.best_runtime_seconds,
                        "distance": s.best_code_distance,
                        "gap_percent": s.optimality_gap_percent,
                        "pareto_coverage": s.pareto_coverage_percent,
                    }
                    for s in search_records
                ],
            })
        else:
            self.send_error(404, "Unknown API endpoint")

    def send_json_response(self, data: Dict[str, Any], status: int = 200) -> None:
        """Send JSON response with proper CORS headers."""
        resp_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(resp_bytes)


def start_quantum_server(port: int = 8500) -> None:
    """Start the interactive UI HTTP server."""
    os.makedirs(UI_DIR, exist_ok=True)
    server = HTTPServer(("127.0.0.1", port), QuantumApiHandler)
    print(f"\n=======================================================", flush=True)
    print(f"  Q-Day OS Futuristic Cyber-Quantum UI Server Active!", flush=True)
    print(f"  URL: http://127.0.0.1:{port}", flush=True)
    print(f"=======================================================\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Q-Day OS Server...", flush=True)
        server.server_close()


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 8500
    start_quantum_server(p)
