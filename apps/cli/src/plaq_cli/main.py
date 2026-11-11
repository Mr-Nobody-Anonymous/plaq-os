"""Unified Command Line Interface for Plaq-OS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from plaq_sdk.client import PlaqClient


def configure_stdio() -> None:
    """Force UTF-8 stdio on Windows consoles so quantum Unicode prints don't crash."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONUTF8", "1")
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass


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

    # plaq task run <task_id> [--wait] [--json]
    task_run = task_sub.add_parser("run", help="Execute a queued task (background worker by default)")
    task_run.add_argument("task_id", help="Target task ID")
    task_run.add_argument("--wait", action="store_true", help="Block until the job finishes")
    task_run.add_argument("--inline", action="store_true", help="Run in-process instead of the queue")
    task_run.add_argument("--json", action="store_true", help="Output raw JSON")

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

    # plaq quantum optimize [--hardware H] [--max-evals N] [--json]
    q_optimize = quantum_sub.add_parser("optimize", help="Run Pareto co-design optimization")
    q_optimize.add_argument("--hardware", default="demo-illustrative", help="Hardware profile")
    q_optimize.add_argument("--max-evals", type=int, default=15, help="Candidate evaluation budget")
    q_optimize.add_argument("--json", action="store_true", help="Output raw JSON")

    q_sim = quantum_sub.add_parser("simulate", help="Stim surface-code Monte Carlo")
    q_sim.add_argument("--distance", type=int, default=3)
    q_sim.add_argument("--shots", type=int, default=200)
    q_sim.add_argument("--error-rate", type=float, default=0.001)
    q_sim.add_argument("--json", action="store_true")

    q_run = quantum_sub.add_parser("run", help="Circuit-level statevector / shot simulation")
    q_run.add_argument("workload", nargs="?", default="bell")
    q_run.add_argument("--qubits", type=int, default=None)
    q_run.add_argument("--shots", type=int, default=0)
    q_run.add_argument("--energy", action="store_true")
    q_run.add_argument("--json", action="store_true")

    quantum_sub.add_parser("workloads", help="List named quantum workloads")
    quantum_sub.add_parser("hardware", help="List calibrated hardware profiles")

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
    serve_parser.add_argument("--host", default=None, help="Bind host (default 127.0.0.1, or 0.0.0.0 in Docker)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port number")
    serve_parser.add_argument("--reload", action="store_true", help="Enable hot reload")

    # 5. mcp — Model Context Protocol stdio server
    subparsers.add_parser("mcp", help="Start the Plaq-OS MCP server on stdio (for Claude Desktop / Cursor)")

    # 6. job group
    job_parser = subparsers.add_parser("job", help="Inspect background agent jobs")
    job_sub = job_parser.add_subparsers(dest="subcommand")
    job_status = job_sub.add_parser("status", help="Show a job by id")
    job_status.add_argument("job_id")
    job_status.add_argument("--json", action="store_true")
    job_list = job_sub.add_parser("list", help="List jobs")
    job_list.add_argument("--task", default=None, help="Filter by task id")
    job_list.add_argument("--json", action="store_true")

    # 7. worker — dedicated SQLite job drain (can run next to `plaq serve`)
    worker_parser = subparsers.add_parser(
        "worker",
        help="Run a background worker that drains the SQLite job queue",
    )
    worker_parser.add_argument("--poll", type=float, default=0.25, help="Poll interval seconds")
    worker_parser.add_argument("--workers", type=int, default=1, help="Worker threads")

    # 8. db — schema migrations
    db_parser = subparsers.add_parser("db", help="Control-plane SQLite migrations")
    db_sub = db_parser.add_subparsers(dest="subcommand")
    db_sub.add_parser("migrate", help="Apply pending schema migrations")
    db_sub.add_parser("status", help="Show applied migration versions")

    doctor = subparsers.add_parser("doctor", help="Diagnose Python, OS, packages, database, and auth")
    doctor.add_argument("--json", action="store_true")

    init = subparsers.add_parser("init", help="Create ~/.plaq, apply migrations, seed an API key")
    init.add_argument("--json", action="store_true")

    return parser


def _db_path() -> str:
    from plaq_control_plane.db import resolve_db_path

    return resolve_db_path()


def get_client() -> PlaqClient:
    """Instantiate a local PlaqClient configured with default database."""
    return PlaqClient.local_client(db_path=_db_path())


def handle_task(args: argparse.Namespace) -> int:
    """Handle plaq task subcommands."""
    client = get_client()
    sub = getattr(args, "subcommand", None)

    if sub == "create":
        task = client.create_task(goal=args.goal, workspace_path=args.workspace)
        if args.json:
            print(task.model_dump_json(indent=2))
        else:
            print("Task created successfully.")
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
            print("Task Details:")
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

    elif sub == "resume":
        # Resume a blocked task: decide the pending approval, then re-run.
        from plaq_control_plane.repository import ControlPlaneRepository

        db_path = _db_path()
        repo = ControlPlaneRepository(db_path)
        try:
            pending = repo.list_approvals(task_id=args.task_id)
            pending = [a for a in pending if a.get("status") == "pending"]
            if pending:
                repo.decide_approval(
                    approval_id=pending[0]["id"],
                    approved=bool(args.approved),
                    reason="CLI resume",
                    decided_by="cli",
                )
            from plaq_agent_runtime.loop import AgentRuntime

            runtime = AgentRuntime(repository=repo)
            result = runtime.resume_task(args.task_id)
            if args.json:
                print(json.dumps({
                    "task_id": result.task_id,
                    "status": result.status,
                    "summary": result.summary,
                    "artifacts": result.artifacts,
                }, indent=2))
            else:
                print(f"Task '{args.task_id}' resumed -> {result.status}")
                if result.summary:
                    print(f"  Summary: {result.summary}")
        finally:
            repo.close()
        return 0

    elif sub == "run":
        from plaq_control_plane.repository import ControlPlaneRepository
        from plaq_agent_runtime.loop import AgentRuntime
        from plaq_agent_runtime.queue import BackgroundTaskQueue

        db_path = _db_path()
        repo = ControlPlaneRepository(db_path)
        try:
            runtime = AgentRuntime(repository=repo)
            if args.inline:
                result = runtime.execute_task(args.task_id)
                payload = {
                    "task_id": result.task_id,
                    "status": result.status,
                    "summary": result.summary,
                    "error": result.error,
                    "mode": "inline",
                }
            else:
                queue = BackgroundTaskQueue(repo, runtime)
                job = queue.enqueue(args.task_id)
                if args.wait:
                    job = queue.wait(job["id"], timeout=300)
                payload = {"mode": "background", "job": job}
            if args.json:
                print(json.dumps(payload, indent=2, default=str))
            else:
                print(json.dumps(payload, indent=2, default=str))
        finally:
            repo.close()
        return 0

    else:
        print("Usage: plaq task [create|list|status|logs|cancel|resume|run]", file=sys.stderr)
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
            circuit_depth=args.depth,
            hardware_profile=args.hardware,
        )
        if args.json:
            print(res.model_dump_json(indent=2))
        else:
            print("Plaq-OS Fault-Tolerant Resource Estimation:")
            print(f"  Logical Qubits:       {res.num_qubits}")
            print(f"  Min Code Distance d:  {res.code_distance}")
            print(f"  Physical Qubits:      {res.physical_qubits}")
            print(f"  Physical Error Rate:  {args.error_rate}")
            print(f"  T-Gate Synthesis:     {res.t_count}")
            print(f"  Feasible:             {res.feasible}")
            print(f"  Estimated Wall Clock: {res.estimated_runtime_sec:.4f}s")
        return 0

    elif sub == "benchmark":
        import plaq_quantum as pq
        from dataclasses import asdict

        hw = pq.hardware.get_hardware_profile(args.hardware)
        circuit = pq.circuits.make_test_circuit(n_qubits=4)
        records = pq.baselines.run_four_baselines_protocol(
            circuit=circuit,
            hardware=hw,
            target_epsilon=1e-3,
        )
        results = [asdict(r) for r in records]
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print("Plaq-OS Four-Baselines Co-Design Protocol:")
            for r in records:
                print(f"  [{r.baseline_id}] {r.baseline_name}")
                print(f"    Physical Qubits: {r.physical_qubits}")
                print(f"    Runtime:         {r.runtime_seconds * 1000:.3f} ms")
                print(f"    Cost Score:      {r.total_cost_score:.1f}")
        return 0

    elif sub == "optimize":
        import plaq_quantum as pq

        hw = pq.hardware.get_hardware_profile(args.hardware)
        circuit = pq.circuits.make_bernstein_vazirani_circuit(bitstring="1111")
        _, pareto = pq.optimizer.search_pareto_optimizer(
            circuit=circuit,
            hardware=hw,
            target_epsilon=1e-3,
            candidate_limit=args.max_evals,
        )
        rows = [p.to_row() for p in pareto]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print(f"Pareto frontier: {len(pareto)} non-dominated plans (hardware={hw.name})")
            for i, r in enumerate(rows):
                print(f"  P{i+1}: qubits={r.get('physical_qubits')} runtime_s={r.get('runtime_s')} d={r.get('code_distance')}")
        return 0

    elif sub == "simulate":
        import plaq_quantum as pq
        from dataclasses import asdict

        res = pq.stim_bridge.run_surface_code_simulation(
            code_distance=args.distance,
            physical_error_rate=args.error_rate,
            shots=args.shots,
        )
        data = asdict(res)
        print(json.dumps(data, indent=2) if args.json else json.dumps(data, indent=2))
        return 0

    elif sub == "run":
        import plaq_quantum as pq

        res = pq.simulation.run_circuit_simulation(
            workload=args.workload,
            qubits=args.qubits,
            shots=args.shots,
            compute_energy=args.energy,
        )
        print(json.dumps(res.to_dict(), indent=2))
        return 0

    elif sub == "workloads":
        import plaq_quantum as pq

        print(json.dumps(pq.workloads.list_workloads(), indent=2))
        return 0

    elif sub == "hardware":
        import plaq_quantum as pq

        print(json.dumps(pq.workloads.list_hardware_profiles(), indent=2))
        return 0

    else:
        print("Usage: plaq quantum [compile|estimate|benchmark|optimize|simulate|run|workloads|hardware]", file=sys.stderr)
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


def _default_bind_host() -> str:
    if os.environ.get("PLAQ_HOST"):
        return os.environ["PLAQ_HOST"]
    if os.environ.get("PLAQ_BIND_ALL") == "1" or Path("/.dockerenv").exists():
        return "0.0.0.0"
    return "127.0.0.1"


def handle_serve(args: argparse.Namespace) -> int:
    """Handle plaq serve subcommand."""
    import uvicorn
    from plaq_api.auth import describe_auth

    host = args.host or _default_bind_host()
    _, auth_msg = describe_auth()
    print(f"Starting Plaq-OS Server on http://{host}:{args.port} ...")
    print(auth_msg)
    uvicorn.run("plaq_api.app:app", host=host, port=args.port, reload=args.reload)
    return 0


def handle_mcp(args: argparse.Namespace) -> int:
    """Start the stdio MCP server (stdout is the protocol stream)."""
    from plaq_mcp.server import run_stdio_server

    print("Plaq-OS MCP server listening on stdio", file=sys.stderr)
    run_stdio_server()
    return 0


def handle_job(args: argparse.Namespace) -> int:
    """Inspect background jobs."""
    from plaq_control_plane.repository import ControlPlaneRepository

    db_path = _db_path()
    repo = ControlPlaneRepository(db_path)
    try:
        sub = getattr(args, "subcommand", None)
        if sub == "status":
            job = repo.get_job(args.job_id)
            if not job:
                print(f"Error: Job '{args.job_id}' not found.", file=sys.stderr)
                return 1
            print(json.dumps(job, indent=2, default=str))
            return 0
        if sub == "list":
            jobs = repo.list_jobs(task_id=args.task)
            print(json.dumps(jobs, indent=2, default=str))
            return 0
        print("Usage: plaq job [status|list]", file=sys.stderr)
        return 1
    finally:
        repo.close()


def handle_worker(args: argparse.Namespace) -> int:
    """Run a dedicated job worker until interrupted."""
    from plaq_agent_runtime.loop import AgentRuntime
    from plaq_agent_runtime.queue import BackgroundTaskQueue
    from plaq_control_plane.repository import ControlPlaneRepository

    repo = ControlPlaneRepository(_db_path())
    runtime = AgentRuntime(repository=repo)
    queue = BackgroundTaskQueue(
        repository=repo,
        runtime=runtime,
        max_workers=args.workers,
        poll_interval=args.poll,
    )
    n = queue.recover_orphans()
    queue.start()
    print(f"Plaq worker online (db={_db_path()}, recovered={n}, threads={args.workers})", flush=True)
    try:
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping worker...", flush=True)
        queue.stop()
        repo.close()
    return 0


def handle_db(args: argparse.Namespace) -> int:
    """Apply or inspect control-plane migrations."""
    from plaq_control_plane.db import DatabaseEngine
    from plaq_control_plane.migrations import MIGRATIONS, applied_versions, apply_migrations

    engine = DatabaseEngine(_db_path())
    try:
        sub = getattr(args, "subcommand", None)
        applied = applied_versions(engine.conn)
        latest = [v for v, _, _ in MIGRATIONS]
        if sub == "status":
            print(json.dumps({"applied": applied, "available": latest, "db": _db_path()}, indent=2))
            return 0
        if sub == "migrate":
            newly = apply_migrations(engine.conn)
            print(json.dumps({"applied_now": newly, "applied": applied_versions(engine.conn)}, indent=2))
            return 0
        print("Usage: plaq db [migrate|status]", file=sys.stderr)
        return 1
    finally:
        engine.close()


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    configure_stdio()
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
    elif args.command == "mcp":
        return handle_mcp(args)
    elif args.command == "job":
        return handle_job(args)
    elif args.command == "worker":
        return handle_worker(args)
    elif args.command == "db":
        return handle_db(args)
    elif args.command == "doctor":
        from plaq_cli.doctor import run_doctor

        return run_doctor(as_json=bool(getattr(args, "json", False)))
    elif args.command == "init":
        from plaq_cli.doctor import run_init

        return run_init(as_json=bool(getattr(args, "json", False)))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
