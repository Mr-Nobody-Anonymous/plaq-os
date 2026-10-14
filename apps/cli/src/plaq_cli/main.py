"""Unified Command Line Interface for Plaq-OS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from plaq_sdk.client import PlaqClient


def build_parser() -> argparse.ArgumentParser:
    """Build root CLI argument parser with task, quantum, workspace, and serve subcommands."""
    parser = argparse.ArgumentParser(
        prog="plaq",
        description="Plaq-OS: Programmable, Agent-Driven Quantum Computing Workbench CLI",
    )
    parser.add_argument("--version", action="version", version="plaq 0.3.0")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. task group
    task_parser = subparsers.add_parser("task", help="Manage asynchronous agent tasks and workflows")
    task_sub = task_parser.add_subparsers(dest="subcommand", help="Task actions")

    # plaq task create <goal> [--workspace <path>] [--json]
    task_create = task_sub.add_parser("create", help="Create and queue a new task")
    task_create.add_argument("goal", help="High-level goal description")
    task_create.add_argument("--workspace", default=".", help="Workspace root directory path")
    task_create.add_argument("--json", action="store_true", help="Output raw JSON")

    # plaq task list [--status <status>] [--json]
    task_list = task_sub.add_parser("list", help="List tasks")
    task_list.add_argument("--status", default=None, help="Filter by lifecycle status")
    task_list.add_argument("--json", action="store_true", help="Output raw JSON")

    # plaq task status <task_id> [--json]
    task_status = task_sub.add_parser("status", help="Get status and details of a task")
    task_status.add_argument("task_id", help="Target task ID")
    task_status.add_argument("--json", action="store_true", help="Output raw JSON")

    # plaq task logs <task_id> [--json]
    task_logs = task_sub.add_parser("logs", help="Get append-only audit trail logs for a task")
    task_logs.add_argument("task_id", help="Target task ID")
    task_logs.add_argument("--json", action="store_true", help="Output raw JSON")

    # plaq task cancel <task_id> [--json]
    task_cancel = task_sub.add_parser("cancel", help="Cancel an in-flight or queued task")
    task_cancel.add_argument("task_id", help="Target task ID")
    task_cancel.add_argument("--json", action="store_true", help="Output raw JSON")

    # plaq task resume <task_id> [--approved/--denied] [--json]
    task_resume = task_sub.add_parser("resume", help="Resume a blocked task following approval decision")
    task_resume.add_argument("task_id", help="Target task ID")
    task_resume.add_argument("--approved", dest="approved", action="store_true", default=True, help="Approve pending gate")
    task_resume.add_argument("--denied", dest="approved", action="store_false", help="Reject pending gate")
    task_resume.add_argument("--json", action="store_true", help="Output raw JSON")

    # 2. quantum group
    quantum_parser = subparsers.add_parser("quantum", help="Quantum circuit synthesis, estimation, and optimization")
    quantum_sub = quantum_parser.add_subparsers(dest="subcommand", help="Quantum actions")

    # plaq quantum compile [circuit_name] [--qubits N] [--json]
    q_compile = quantum_sub.add_parser("compile", help="Synthesize quantum workload and extract metrics")
    q_compile.add_argument("circuit_name", nargs="?", default="bernstein_vazirani", help="Circuit identifier")
    q_compile.add_argument("--qubits", type=int, default=4, help="Number of qubits")
    q_compile.add_argument("--json", action="store_true", help="Output raw JSON")

    # plaq quantum estimate [--qubits N] [--depth D] [--hardware H] [--error-rate P] [--json]
    q_estimate = quantum_sub.add_parser("estimate", help="Analytical fault-tolerant cost and code distance estimation")
    q_estimate.add_argument("--qubits", type=int, default=4, help="Logical qubits")
    q_estimate.add_argument("--depth", type=int, default=50, help="Circuit depth")
    q_estimate.add_argument("--hardware", default="demo-illustrative", help="Hardware profile name")
    q_estimate.add_argument("--error-rate", type=float, default=0.001, help="Physical two-qubit error rate")
    q_estimate.add_argument("--error-budget", type=float, default=1e-3, help="Allocated error budget epsilon")
    q_estimate.add_argument("--json", action="store_true", help="Output raw JSON")

    # plaq quantum benchmark [--json]
    q_benchmark = quantum_sub.add_parser("benchmark", help="Execute fair multi-workload co-design benchmark")
    q_benchmark.add_argument("--hardware", default="demo-illustrative", help="Hardware profile")
    q_benchmark.add_argument("--json", action="store_true", help="Output raw JSON")

    # 3. workspace group
    workspace_parser = subparsers.add_parser("workspace", help="Inspect and configure workbench workspaces")
    workspace_sub = workspace_parser.add_subparsers(dest="subcommand", help="Workspace actions")

    # plaq workspace open <path>
    ws_open = workspace_sub.add_parser("open", help="Open or switch active workspace")
    ws_open.add_argument("path", help="Path to local directory")

    # plaq workspace status
    workspace_sub.add_parser("status", help="Display current active workspace information")

    # 4. serve group
    serve_parser = subparsers.add_parser("serve", help="Start the Plaq-OS FastAPI backend & Workbench server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host address")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port number")
    serve_parser.add_argument("--reload", action="store_true", help="Enable hot reload")

    return parser


def get_client() -> PlaqClient:
    """Instantiate a local PlaqClient configured with default database."""
    db_path = os.environ.get("PLAQ_DB_PATH")
    if not db_path:
        home_db = Path.home() / ".plaq" / "plaq.db"
        home_db.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(home_db)
    return PlaqClient.local_client(db_path=db_path)


def handle_task(args: argparse.Namespace) -> int:
    """Handle plaq task subcommands."""
    client = get_client()
    sub = getattr(args, "subcommand", None)

    if sub == "create":
        task = client.create_task(goal=args.goal, workspace_path=args.workspace)
        if args.json:
            print(task.model_dump_json(indent=2))
        else:
            print(f"Task created successfully.")
            print(f"  ID:     {task.id}")
            print(f"  Status: {task.status}")
            print(f"  Goal:   {task.goal}")
        return 0

    elif sub == "list":
        tasks = client.list_tasks(status=args.status)
        if args.json:
            print(json.dumps([t.model_dump(mode="json") for t in tasks], indent=2))
        else:
            if not tasks:
                print("No tasks found.")
            else:
                print(f"{'ID':<38} {'STATUS':<12} {'GOAL':<40}")
                print("-" * 92)
                for t in tasks:
                    print(f"{t.id:<38} {t.status:<12} {t.goal[:38]:<40}")
        return 0

    elif sub == "status":
        task = client.get_task(args.task_id)
        if not task:
            print(f"Error: Task '{args.task_id}' not found.", file=sys.stderr)
            return 1
        if args.json:
            print(task.model_dump_json(indent=2))
        else:
            print(f"Task Details:")
            print(f"  ID:         {task.id}")
            print(f"  Status:     {task.status}")
            print(f"  Goal:       {task.goal}")
            print(f"  Workspace:  {task.workspace_path}")
            print(f"  Created:    {task.created_at}")
            if task.error:
                print(f"  Error:      {task.error}")
        return 0

    elif sub == "logs":
        logs = client.get_task_logs(args.task_id)
        if args.json:
            print(json.dumps(logs, indent=2))
        else:
            if not logs:
                print(f"No audit logs for task '{args.task_id}'.")
            else:
                print(f"Audit Trail for Task {args.task_id} ({len(logs)} entries):")
                for entry in logs:
                    seq = entry.get("sequence_number", 0)
                    tool = entry.get("tool_name", "unknown")
                    dur = entry.get("duration_ms", 0.0)
                    code = entry.get("exit_code", 0)
                    print(f"  [{seq:>2}] {tool:<22} exit={code:<2} duration={dur:>6.1f}ms")
        return 0

    elif sub == "cancel":
        client.transition_task(args.task_id, "cancelled")
        if args.json:
            print(json.dumps({"task_id": args.task_id, "status": "cancelled"}))
        else:
            print(f"Task '{args.task_id}' cancelled.")
        return 0

    else:
        print("Usage: plaq task [create|list|status|logs|cancel|resume]", file=sys.stderr)
        return 1


def handle_quantum(args: argparse.Namespace) -> int:
    """Handle plaq quantum subcommands."""
    sub = getattr(args, "subcommand", None)

    if sub == "compile":
        import plaq_quantum as pq
        circuit_name = args.circuit_name
        if circuit_name == "bernstein_vazirani":
            circuit = pq.circuits.make_bernstein_vazirani_circuit(bitstring="1" * max(1, args.qubits - 1))
        elif circuit_name == "qft":
            circuit = pq.circuits.make_qft_circuit(n_qubits=args.qubits)
        elif circuit_name == "qaoa":
            circuit = pq.circuits.make_qaoa_circuit(n_qubits=args.qubits)
        else:
            circuit = pq.circuits.make_test_circuit(n_qubits=args.qubits)

        metrics = pq.cost_model.extract_circuit_metrics(circuit)
        data = {
            "workload": circuit_name,
            "num_qubits": metrics.num_qubits,
            "depth": metrics.depth,
            "total_ops": metrics.total_ops,
            "t_count": metrics.t_ops,
            "t_depth": metrics.t_depth,
        }
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"Quantum Circuit Synthesis: {circuit_name}")
            print(f"  Logical Qubits:  {metrics.num_qubits}")
            print(f"  Circuit Depth:   {metrics.depth}")
            print(f"  Total Ops:       {metrics.total_ops}")
            print(f"  T-Gate Count:    {metrics.t_ops}")
            print(f"  T-Gate Depth:    {metrics.t_depth}")
        return 0

    elif sub == "estimate":
        client = get_client()
        res = client.estimate_quantum(
            qubits=args.qubits,
            physical_error_rate=args.error_rate,
            error_budget=args.error_budget,
        )
        if args.json:
            print(res.model_dump_json(indent=2))
        else:
            print("Plaq-OS Fault-Tolerant Resource Estimation:")
            print(f"  Logical Qubits:       {res.num_qubits}")
            print(f"  Min Code Distance d:  {res.code_distance}")
            print(f"  Physical Error Rate:  {args.error_rate}")
            print(f"  T-Gate Synthesis:     {res.t_count}")
            print(f"  Feasible:             {res.feasible}")
            print(f"  Estimated Wall Clock: {res.estimated_runtime_sec:.4f}s")
        return 0

    elif sub == "benchmark":
        import plaq_quantum as pq
        results = pq.baselines.run_baselines_comparison()
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print("Plaq-OS Four-Baselines Co-Design Protocol:")
            for name, metrics in results.items():
                print(f"  Baseline: {name}")
                print(f"    Physical Qubits: {metrics.get('physical_qubits')}")
                print(f"    Runtime:         {metrics.get('runtime_ms')} ms")
                print(f"    Cost Score:      {metrics.get('cost_score')}")
        return 0

    else:
        print("Usage: plaq quantum [compile|estimate|benchmark]", file=sys.stderr)
        return 1


def handle_workspace(args: argparse.Namespace) -> int:
    """Handle plaq workspace subcommands."""
    sub = getattr(args, "subcommand", None)

    if sub == "open":
        target = Path(args.path).resolve()
        if not target.exists():
            print(f"Error: Directory '{args.path}' does not exist.", file=sys.stderr)
            return 1
        if not target.is_dir():
            print(f"Error: Path '{args.path}' is not a directory.", file=sys.stderr)
            return 1
        print(f"Workspace opened: {target}")
        return 0

    elif sub == "status":
        cwd = Path.cwd().resolve()
        print(f"Current Workspace: {cwd}")
        is_git = (cwd / ".git").exists()
        print(f"Git Repository:   {'Yes' if is_git else 'No'}")
        return 0

    else:
        print("Usage: plaq workspace [open|status]", file=sys.stderr)
        return 1


def handle_serve(args: argparse.Namespace) -> int:
    """Handle plaq serve subcommand."""
    import uvicorn
    print(f"Starting Plaq-OS Server on http://{args.host}:{args.port} ...")
    uvicorn.run("plaq_api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "task":
        return handle_task(args)
    elif args.command == "quantum":
        return handle_quantum(args)
    elif args.command == "workspace":
        return handle_workspace(args)
    elif args.command == "serve":
        return handle_serve(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
