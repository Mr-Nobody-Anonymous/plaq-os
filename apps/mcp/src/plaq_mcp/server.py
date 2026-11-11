"""Stdio MCP server exposing Plaq-OS quantum simulation + task tools.

Speaks JSON-RPC 2.0 over stdin/stdout with both newline-delimited and
LSP-style Content-Length framing so Claude Desktop, Cursor, and similar
MCP hosts can drive the FTQC engine without going through HTTP.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "plaq-os"
SERVER_VERSION = "0.3.0"


def _json_default(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, (set, tuple)):
        return list(obj)
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def _ok_text(payload: Any) -> Dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=_json_default)
    return {"content": [{"type": "text", "text": text}]}


def _err_text(message: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _tool(name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return {"name": name, "description": description, "inputSchema": schema}


def tool_catalog() -> List[Dict[str, Any]]:
    return [
        _tool(
            "quantum_compile",
            "Synthesize a named quantum workload (QAOA, QFT, BV, chemistry, Shor, Bell, GHZ) or OpenQASM and extract T-count / depth metrics.",
            {
                "workload": {"type": "string", "description": "Workload id or alias (qaoa, qft, bv, chemistry, shor, bell, ghz, …)"},
                "qubits": {"type": "integer"},
                "bitstring": {"type": "string"},
                "qasm": {"type": "string", "description": "OpenQASM 2.0 body"},
            },
        ),
        _tool(
            "quantum_estimate",
            "Analytical fault-tolerant resource estimate (code distance, physical qubits, runtime, P_fail).",
            {
                "hardware_profile": {"type": "string", "default": "superconducting"},
                "num_qubits": {"type": "integer", "default": 5},
                "circuit_depth": {"type": "integer", "default": 100},
                "t_count": {"type": "integer"},
                "target_epsilon": {"type": "number", "default": 0.001},
                "workload": {"type": "string", "description": "If set, metrics are taken from this compiled workload"},
            },
        ),
        _tool(
            "quantum_simulate",
            "Rotated surface-code Stim + PyMatching Monte Carlo (logical error rate, Wilson CI).",
            {
                "code_distance": {"type": "integer", "default": 3},
                "physical_error_rate": {"type": "number", "default": 0.001},
                "shots": {"type": "integer", "default": 200},
                "seed": {"type": "integer", "default": 42},
            },
        ),
        _tool(
            "quantum_run",
            "Circuit-level statevector or shot simulation (probabilities, counts, optional MaxCut/Ising energy).",
            {
                "workload": {"type": "string", "default": "bell"},
                "qubits": {"type": "integer"},
                "qasm": {"type": "string"},
                "shots": {"type": "integer", "description": "0 = statevector, >0 = sampled counts"},
                "compute_energy": {"type": "boolean", "default": False},
                "seed": {"type": "integer", "default": 42},
            },
        ),
        _tool(
            "quantum_optimize",
            "Pareto co-design search over compiler / factories / decoder / code-distance strategies.",
            {
                "workload": {"type": "string", "default": "test_rz_cx_5q"},
                "hardware_profile": {"type": "string", "default": "superconducting"},
                "candidate_limit": {"type": "integer", "default": 12},
                "target_epsilon": {"type": "number", "default": 0.001},
            },
        ),
        _tool(
            "quantum_baselines",
            "Run the 4-baselines co-design protocol (raw / Qiskit-L3 / decoupled / joint).",
            {
                "workload": {"type": "string", "default": "test_rz_cx_5q"},
                "hardware_profile": {"type": "string", "default": "demo"},
                "target_epsilon": {"type": "number", "default": 0.001},
            },
        ),
        _tool(
            "quantum_threshold",
            "Stim surface-code threshold sweep across distances and physical error rates.",
            {
                "distances": {"type": "array", "items": {"type": "integer"}, "default": [3]},
                "physical_error_rates": {"type": "array", "items": {"type": "number"}},
                "shots_per_point": {"type": "integer", "default": 40},
            },
        ),
        _tool(
            "quantum_workloads",
            "List named quantum workloads an agent can compile, simulate, or optimize.",
            {},
        ),
        _tool(
            "quantum_hardware",
            "List calibrated hardware profiles (superconducting, trapped ion, neutral atom, qLDPC).",
            {},
        ),
        _tool(
            "task_create",
            "Create a Plaq-OS agent task from a natural-language goal (queued for the 7-stage loop).",
            {"goal": {"type": "string"}, "workspace_path": {"type": "string"}},
            required=["goal"],
        ),
        _tool(
            "task_run",
            "Run (or enqueue) an agent task. background=true returns a job id immediately.",
            {
                "task_id": {"type": "string"},
                "background": {"type": "boolean", "default": False},
            },
            required=["task_id"],
        ),
        _tool(
            "task_status",
            "Fetch task status, steps, and latest job if any.",
            {"task_id": {"type": "string"}},
            required=["task_id"],
        ),
    ]


def resource_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "uri": "plaq://workloads",
            "name": "Quantum workloads",
            "mimeType": "application/json",
            "description": "Named FTQC / NISQ workloads (QAOA, QFT, chemistry, Shor, …)",
        },
        {
            "uri": "plaq://hardware",
            "name": "Hardware profiles",
            "mimeType": "application/json",
            "description": "Calibrated device models with error rates and QEC thresholds",
        },
        {
            "uri": "plaq://tools",
            "name": "Agent tool registry",
            "mimeType": "application/json",
            "description": "Plaq-OS tool names, tiers, and JSON schemas",
        },
    ]


def _repo():
    from plaq_control_plane.repository import ControlPlaneRepository

    from plaq_control_plane.db import resolve_db_path

    return ControlPlaneRepository(resolve_db_path())


def _call_quantum_compile(args: Dict[str, Any]) -> Any:
    import plaq_quantum as pq

    qc = pq.workloads.resolve_circuit(
        workload=args.get("workload"),
        qubits=args.get("qubits"),
        bitstring=args.get("bitstring"),
        qasm=args.get("qasm"),
    )
    metrics = pq.cost_model.extract_circuit_metrics(qc)
    return {
        "num_qubits": metrics.num_qubits,
        "depth": metrics.depth,
        "t_ops": metrics.t_ops,
        "t_depth": metrics.t_depth,
        "total_ops": metrics.total_ops,
        "workload": args.get("workload"),
    }


def _call_quantum_estimate(args: Dict[str, Any]) -> Any:
    import plaq_quantum as pq

    hw = pq.hardware.get_hardware_profile(args.get("hardware_profile") or "superconducting")
    n = int(args.get("num_qubits") or 5)
    depth = int(args.get("circuit_depth") or 100)
    t_count = int(args.get("t_count") or n * 10)
    workload = args.get("workload")
    if workload:
        qc = pq.workloads.resolve_circuit(workload=workload, qubits=args.get("qubits"))
        m = pq.cost_model.extract_circuit_metrics(qc)
        n, depth, t_count = m.num_qubits, m.depth, m.t_ops
        metrics = m
    else:
        metrics = pq.cost_model.CircuitMetrics(
            num_qubits=n,
            depth=depth,
            total_ops=n * depth,
            single_qubit_ops=max(0, n * depth - t_count),
            two_qubit_ops=n,
            t_ops=t_count,
            t_depth=max(1, t_count // 2),
            measurement_ops=n,
            operation_counts={"t": t_count},
            synthesis_t_count=0,
        )
    cost = pq.cost_model.evaluate_fault_tolerant_cost(
        metrics=metrics,
        hardware=hw,
        target_epsilon=float(args.get("target_epsilon") or 1e-3),
    )
    return {
        "hardware": hw.name,
        "code_distance": cost.code_distance,
        "physical_qubits": cost.physical_qubits,
        "runtime_seconds": cost.runtime_seconds,
        "failure_probability": cost.failure_probability,
        "feasible": cost.valid,
        "num_qubits": n,
        "depth": depth,
        "t_count": t_count,
    }


def _call_quantum_simulate(args: Dict[str, Any]) -> Any:
    import plaq_quantum as pq

    res = pq.stim_bridge.run_surface_code_simulation(
        code_distance=int(args.get("code_distance") or 3),
        physical_error_rate=float(args.get("physical_error_rate") or 0.001),
        shots=int(args.get("shots") or 200),
        seed=int(args.get("seed") or 42),
    )
    return asdict(res)


def _call_quantum_run(args: Dict[str, Any]) -> Any:
    import plaq_quantum as pq

    res = pq.simulation.run_circuit_simulation(
        workload=args.get("workload") or "bell",
        qubits=args.get("qubits"),
        qasm=args.get("qasm"),
        shots=int(args.get("shots") or 0),
        seed=int(args.get("seed") or 42),
        compute_energy=bool(args.get("compute_energy") or False),
    )
    return res.to_dict()


def _call_quantum_optimize(args: Dict[str, Any]) -> Any:
    import plaq_quantum as pq

    qc = pq.workloads.resolve_circuit(workload=args.get("workload") or "test_rz_cx_5q")
    hw = pq.hardware.get_hardware_profile(args.get("hardware_profile") or "superconducting")
    _, pareto = pq.optimizer.search_pareto_optimizer(
        circuit=qc,
        hardware=hw,
        target_epsilon=float(args.get("target_epsilon") or 1e-3),
        candidate_limit=int(args.get("candidate_limit") or 12),
    )
    return {"hardware": hw.name, "pareto_points": len(pareto), "frontier": [p.to_row() for p in pareto]}


def _call_quantum_baselines(args: Dict[str, Any]) -> Any:
    import plaq_quantum as pq

    qc = pq.workloads.resolve_circuit(workload=args.get("workload") or "test_rz_cx_5q")
    hw = pq.hardware.get_hardware_profile(args.get("hardware_profile") or "demo")
    records = pq.baselines.run_four_baselines_protocol(
        circuit=qc, hardware=hw, target_epsilon=float(args.get("target_epsilon") or 1e-3)
    )
    return {"comparisons": [asdict(r) for r in records]}


def _call_quantum_threshold(args: Dict[str, Any]) -> Any:
    import plaq_quantum as pq

    distances = args.get("distances") or [3]
    rates = args.get("physical_error_rates") or [0.001, 0.01]
    results = pq.stim_bridge.run_threshold_study(
        distances=list(distances),
        physical_error_rates=list(rates),
        shots_per_point=int(args.get("shots_per_point") or 40),
    )
    return {"samples": [asdict(r) for r in results]}


def _dispatch_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if name == "quantum_compile":
            return _ok_text(_call_quantum_compile(args))
        if name == "quantum_estimate":
            return _ok_text(_call_quantum_estimate(args))
        if name == "quantum_simulate":
            return _ok_text(_call_quantum_simulate(args))
        if name == "quantum_run":
            return _ok_text(_call_quantum_run(args))
        if name == "quantum_optimize":
            return _ok_text(_call_quantum_optimize(args))
        if name == "quantum_baselines":
            return _ok_text(_call_quantum_baselines(args))
        if name == "quantum_threshold":
            return _ok_text(_call_quantum_threshold(args))
        if name == "quantum_workloads":
            import plaq_quantum as pq

            return _ok_text(pq.workloads.list_workloads())
        if name == "quantum_hardware":
            import plaq_quantum as pq

            return _ok_text(pq.workloads.list_hardware_profiles())
        if name == "task_create":
            repo = _repo()
            row = repo.create_task(
                goal=str(args.get("goal") or ""),
                workspace_path=str(args.get("workspace_path") or os.getcwd()),
            )
            return _ok_text(row)
        if name == "task_run":
            from plaq_agent_runtime.loop import AgentRuntime
            from plaq_agent_runtime.queue import BackgroundTaskQueue

            repo = _repo()
            task_id = str(args["task_id"])
            runtime = AgentRuntime(repository=repo)
            if args.get("background"):
                q = BackgroundTaskQueue(repo, runtime)
                job = q.enqueue(task_id)
                return _ok_text(job)
            result = runtime.execute_task(task_id)
            return _ok_text(
                {
                    "task_id": result.task_id,
                    "status": result.status,
                    "summary": result.summary,
                    "error": result.error,
                }
            )
        if name == "task_status":
            repo = _repo()
            task = repo.get_task(str(args["task_id"]))
            if not task:
                return _err_text(f"Task '{args['task_id']}' not found")
            steps = repo.list_steps(task["id"])
            jobs = repo.list_jobs(task_id=task["id"])
            return _ok_text({"task": task, "steps": steps, "jobs": jobs})
        return _err_text(f"Unknown tool: {name}")
    except Exception as exc:
        return _err_text(f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}")


def _read_resource(uri: str) -> Dict[str, Any]:
    import plaq_quantum as pq

    if uri == "plaq://workloads":
        body = json.dumps(pq.workloads.list_workloads(), indent=2, default=_json_default)
    elif uri == "plaq://hardware":
        body = json.dumps(pq.workloads.list_hardware_profiles(), indent=2, default=_json_default)
    elif uri == "plaq://tools":
        from plaq_agent_runtime.registry import create_default_tool_registry

        tools = [
            {
                "name": t.name,
                "description": t.description,
                "tier": t.tier.value if hasattr(t.tier, "value") else str(t.tier),
                "parameters_schema": t.parameters_schema,
            }
            for t in create_default_tool_registry().list_tools()
        ]
        body = json.dumps(tools, indent=2, default=_json_default)
    else:
        raise KeyError(f"Unknown resource: {uri}")
    return {"contents": [{"uri": uri, "mimeType": "application/json", "text": body}]}


def handle_rpc(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Dispatch a single JSON-RPC request. Returns None for notifications."""
    method = message.get("method")
    msg_id = message.get("id", None)
    params = message.get("params") or {}

    def result(value: Any) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": value}

    def error(code: int, err_message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": err_message}}

    if method is None:
        return error(-32600, "Invalid Request")

    # Notifications have no id
    is_notification = "id" not in message

    try:
        if method == "initialize":
            return result(
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False, "subscribe": False},
                    },
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                }
            )
        if method in {"notifications/initialized", "initialized"}:
            return None
        if method == "ping":
            return None if is_notification else result({})
        if method == "tools/list":
            return result({"tools": tool_catalog()})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if not name:
                return error(-32602, "tools/call requires 'name'")
            return result(_dispatch_tool(str(name), dict(args)))
        if method == "resources/list":
            return result({"resources": resource_catalog()})
        if method == "resources/read":
            uri = params.get("uri")
            if not uri:
                return error(-32602, "resources/read requires 'uri'")
            return result(_read_resource(str(uri)))
        if method == "prompts/list":
            return result({"prompts": []})
        if is_notification:
            return None
        return error(-32601, f"Method not found: {method}")
    except Exception as exc:
        if is_notification:
            return None
        return error(-32603, f"{type(exc).__name__}: {exc}")


def _read_message(stdin) -> Optional[Dict[str, Any]]:
    header = stdin.readline()
    if header == "":
        return None
    if header.lower().startswith("content-length:"):
        try:
            length = int(header.split(":", 1)[1].strip())
        except ValueError:
            return None
        while True:
            line = stdin.readline()
            if line in ("", "\n", "\r\n"):
                break
        body = stdin.read(length)
        return json.loads(body)
    header = header.strip()
    if not header:
        return _read_message(stdin)
    return json.loads(header)


def _write_message(stdout, message: Dict[str, Any], framing: str) -> None:
    body = json.dumps(message, ensure_ascii=False, default=_json_default)
    if framing == "content-length":
        payload = body.encode("utf-8")
        stdout.write(f"Content-Length: {len(payload)}\r\n\r\n")
        stdout.write(body)
        stdout.flush()
    else:
        stdout.write(body + "\n")
        stdout.flush()


def run_stdio_server(stdin=None, stdout=None) -> None:
    """Serve MCP over stdio until EOF."""
    # Bootstrap monorepo imports when launched as `python -m plaq_mcp`.
    try:
        import plaq_bootstrap  # noqa: F401
    except Exception:
        root = Path(__file__).resolve().parents[4]
        bootstrap = root / "plaq_bootstrap.py"
        if bootstrap.exists():
            sys.path.insert(0, str(root))
            import plaq_bootstrap  # noqa: F401

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    framing = "content-length"
    while True:
        try:
            msg = _read_message(stdin)
        except json.JSONDecodeError:
            continue
        if msg is None:
            break
        # First message style sticks: if it came in as raw JSON line, reply in kind.
        # Content-Length detection happens inside _read_message; we always reply
        # with Content-Length because that is what Claude Desktop / the TS SDK expect.
        reply = handle_rpc(msg)
        if reply is not None:
            _write_message(stdout, reply, framing)
