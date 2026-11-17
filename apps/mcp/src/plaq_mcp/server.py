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
from typing import Any, Dict, List, Optional, Tuple

PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
SERVER_NAME = "plaq-os"
SERVER_VERSION = "0.3.0"


def _json_default(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, (set, tuple)):
        return list(obj)
    if isinstance(obj, Path):
        return str(obj)
    ndim = getattr(obj, "ndim", None)
    if ndim == 0 and hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "tolist") and callable(obj.tolist) and ndim is not None:
        return obj.tolist()
    return str(obj)


def _jsonable(obj: Any) -> Any:
    """Make numpy keys/values and dataclasses JSON-safe."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        return _jsonable(asdict(obj))
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, (str, int, float, bool)) or k is None:
                key: Any = k
            else:
                key = str(k)
            out[key] = _jsonable(v)
        return out
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(x) for x in obj]
    ndim = getattr(obj, "ndim", None)
    if ndim == 0 and hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "tolist") and callable(obj.tolist) and ndim is not None:
        return _jsonable(obj.tolist())
    return obj


def _ok_text(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(_jsonable(payload), indent=2, default=_json_default)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _err_text(message: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _get_int(args: Dict[str, Any], key: str, default: Optional[int] = None) -> Optional[int]:
    if key not in args or args[key] is None or args[key] == "":
        return default
    return int(args[key])


def _get_float(args: Dict[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
    if key not in args or args[key] is None or args[key] == "":
        return default
    return float(args[key])


def _negotiate_version(params: Dict[str, Any]) -> str:
    requested = str((params or {}).get("protocolVersion") or "")
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return PROTOCOL_VERSION


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
            "quantum_noise",
            "Phenomenological NISQ noise (depolarizing + readout) versus the ideal statevector.",
            {
                "workload": {"type": "string", "default": "bell"},
                "shots": {"type": "integer", "default": 1024},
                "p1": {"type": "number", "default": 0.001},
                "p2": {"type": "number", "default": 0.01},
                "p_readout": {"type": "number", "default": 0.02},
            },
        ),
        _tool(
            "quantum_mitigate",
            "Readout inversion + zero-noise extrapolation (ZNE) on a circuit observable.",
            {
                "workload": {"type": "string", "default": "bell"},
                "observable": {"type": "string", "default": "success"},
                "p2": {"type": "number", "default": 0.01},
            },
        ),
        _tool(
            "quantum_transpile",
            "SWAP-route a circuit onto linear, grid, or IBM-like heavy-hex coupling.",
            {
                "workload": {"type": "string", "default": "qft"},
                "qubits": {"type": "integer", "default": 4},
                "topology": {"type": "string", "default": "linear"},
            },
        ),
        _tool(
            "quantum_surgery",
            "Lattice-surgery resource plan: surface-code patches, 15-to-1 T factories, code cycles.",
            {
                "workload": {"type": "string", "default": "qft"},
                "qubits": {"type": "integer", "default": 4},
                "code_distance": {"type": "integer", "default": 3},
                "hardware_profile": {"type": "string", "default": "superconducting"},
            },
        ),
        _tool(
            "quantum_draw",
            "ASCII and Mermaid diagram of a named workload or OpenQASM circuit.",
            {"workload": {"type": "string", "default": "bell"}, "qubits": {"type": "integer"}},
        ),
        _tool(
            "quantum_qasm",
            "Compile an OpenQASM 2.0 body and extract circuit metrics.",
            {"qasm": {"type": "string", "description": "OpenQASM 2.0 source"}},
            required=["qasm"],
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


def prompt_catalog() -> List[Dict[str, Any]]:
    """Prompts MCP hosts can offer the user / agent."""
    return [
        {
            "name": "nisq_lab",
            "description": "Run a Bell circuit through NISQ noise and ZNE mitigation.",
            "arguments": [],
        },
        {
            "name": "ftqc_estimate",
            "description": "Compile a workload, estimate FT resources, optionally Stim-simulate.",
            "arguments": [
                {"name": "workload", "description": "Named circuit (qft, qaoa, chemistry, …)", "required": False}
            ],
        },
        {
            "name": "lattice_surgery",
            "description": "Plan surface-code patches and T factories for a logical circuit.",
            "arguments": [
                {"name": "workload", "description": "Named circuit", "required": False},
                {"name": "distance", "description": "Code distance d (odd integer >= 3)", "required": False},
            ],
        },
    ]


def _render_prompt(name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    args = arguments or {}
    wl = str(args.get("workload") or "qft")
    d = str(args.get("distance") or "5")
    texts = {
        "nisq_lab": (
            "Use Plaq-OS MCP tools. 1) quantum_run workload=bell. "
            "2) quantum_noise workload=bell p2=0.03. "
            "3) quantum_mitigate workload=bell. Summarize TVD and whether ZNE improved the observable."
        ),
        "ftqc_estimate": (
            f"Use Plaq-OS MCP tools on workload={wl}: quantum_compile, quantum_estimate, "
            "then quantum_simulate if Stim is available (if it errors, skip and say so)."
        ),
        "lattice_surgery": (
            f"Call quantum_surgery with workload={wl} and code_distance={d}. "
            "Explain physical qubit total, factory count, and decoder_backlog_safe."
        ),
    }
    if name not in texts:
        raise KeyError(f"Unknown prompt: {name}")
    return {
        "description": next(p["description"] for p in prompt_catalog() if p["name"] == name),
        "messages": [{"role": "user", "content": {"type": "text", "text": texts[name]}}],
    }


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

    if not getattr(pq.stim_bridge, "HAS_STIM", False):
        raise RuntimeError(
            "Stim is not installed. Install stim+pymatching or use quantum_run / quantum_noise (lite profile)."
        )
    res = pq.stim_bridge.run_surface_code_simulation(
        code_distance=_get_int(args, "code_distance", 3) or 3,
        physical_error_rate=_get_float(args, "physical_error_rate", 0.001) or 0.001,
        shots=_get_int(args, "shots", 200) or 200,
        seed=_get_int(args, "seed", 42) or 42,
    )
    return asdict(res)


def _call_quantum_run(args: Dict[str, Any]) -> Any:
    import plaq_quantum as pq

    res = pq.simulation.run_circuit_simulation(
        workload=args.get("workload") or "bell",
        qubits=_get_int(args, "qubits", None),
        qasm=args.get("qasm"),
        shots=_get_int(args, "shots", 0) or 0,
        seed=_get_int(args, "seed", 42) or 42,
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

    if not getattr(pq.stim_bridge, "HAS_STIM", False):
        raise RuntimeError(
            "Stim is not installed. Install stim+pymatching for threshold sweeps, or use quantum_noise."
        )
    distances = args.get("distances") or [3]
    rates = args.get("physical_error_rates") or [0.001, 0.01]
    results = pq.stim_bridge.run_threshold_study(
        distances=list(distances),
        physical_error_rates=list(rates),
        shots_per_point=_get_int(args, "shots_per_point", 40) or 40,
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
        if name == "quantum_noise":
            import plaq_quantum as pq

            return _ok_text(
                pq.noise.run_noisy_simulation(
                    workload=args.get("workload") or "bell",
                    qubits=_get_int(args, "qubits", None),
                    qasm=args.get("qasm"),
                    shots=_get_int(args, "shots", 1024) or 0,
                    seed=_get_int(args, "seed", 42) or 42,
                    p1=_get_float(args, "p1", 0.001) or 0.0,
                    p2=_get_float(args, "p2", 0.01) or 0.0,
                    p_readout=_get_float(args, "p_readout", 0.02) or 0.0,
                ).to_dict()
            )
        if name == "quantum_mitigate":
            import plaq_quantum as pq

            return _ok_text(
                pq.mitigation.run_mitigation(
                    workload=args.get("workload") or "bell",
                    qubits=_get_int(args, "qubits", None),
                    qasm=args.get("qasm"),
                    p1=_get_float(args, "p1", 0.001),
                    p2=_get_float(args, "p2", 0.01),
                    p_readout=_get_float(args, "p_readout", 0.02),
                    observable=str(args.get("observable") or "success"),
                ).to_dict()
            )
        if name == "quantum_transpile":
            import plaq_quantum as pq

            return _ok_text(
                pq.transpiler.route_circuit(
                    workload=args.get("workload") or "qft",
                    qubits=_get_int(args, "qubits", 4),
                    qasm=args.get("qasm"),
                    topology=str(args.get("topology") or "linear"),
                ).to_dict()
            )
        if name == "quantum_surgery":
            import plaq_quantum as pq

            return _ok_text(
                pq.surgery.plan_lattice_surgery(
                    workload=args.get("workload") or "qft",
                    qubits=_get_int(args, "qubits", 4),
                    qasm=args.get("qasm"),
                    code_distance=_get_int(args, "code_distance", 3),
                    hardware_profile=str(args.get("hardware_profile") or "superconducting"),
                ).to_dict()
            )
        if name == "quantum_draw":
            import plaq_quantum as pq

            return _ok_text(
                pq.visualize.draw_circuit(
                    workload=args.get("workload") or "bell",
                    qubits=_get_int(args, "qubits", None),
                    qasm=args.get("qasm"),
                ).to_dict()
            )
        if name == "quantum_qasm":
            qasm = args.get("qasm")
            if not qasm:
                return _err_text("quantum_qasm requires 'qasm'")
            return _ok_text(_call_quantum_compile({"qasm": qasm}))
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
        print(f"[plaq-mcp] {name} failed: {exc}\n{traceback.format_exc(limit=4)}", file=sys.stderr)
        return _err_text(f"{type(exc).__name__}: {exc}")


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
            version = _negotiate_version(params if isinstance(params, dict) else {})
            return result(
                {
                    "protocolVersion": version,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False, "subscribe": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": (
                        "Plaq-OS quantum workbench. Prefer quantum_run / quantum_noise / "
                        "quantum_mitigate for NISQ circuits; quantum_estimate / quantum_surgery "
                        "for FTQC resources; quantum_simulate only when Stim is installed."
                    ),
                }
            )
        if method in {"notifications/initialized", "initialized", "notifications/cancelled"}:
            return None
        if method == "ping":
            return None if is_notification else result({})
        if method == "logging/setLevel":
            return None if is_notification else result({})
        if method == "tools/list":
            return result({"tools": tool_catalog()})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if not name:
                return error(-32602, "tools/call requires 'name'")
            if not isinstance(args, dict):
                return error(-32602, "tools/call 'arguments' must be an object")
            return result(_dispatch_tool(str(name), dict(args)))
        if method == "resources/list":
            return result({"resources": resource_catalog()})
        if method == "resources/templates/list":
            return result({"resourceTemplates": []})
        if method == "resources/read":
            uri = params.get("uri")
            if not uri:
                return error(-32602, "resources/read requires 'uri'")
            try:
                return result(_read_resource(str(uri)))
            except KeyError as exc:
                return error(-32602, str(exc))
        if method == "prompts/list":
            return result({"prompts": prompt_catalog()})
        if method == "prompts/get":
            pname = params.get("name")
            if not pname:
                return error(-32602, "prompts/get requires 'name'")
            try:
                return result(_render_prompt(str(pname), params.get("arguments") or {}))
            except KeyError as exc:
                return error(-32602, str(exc))
        if is_notification:
            return None
        return error(-32601, f"Method not found: {method}")
    except Exception as exc:
        if is_notification:
            return None
        return error(-32603, f"{type(exc).__name__}: {exc}")


def _read_message(stdin) -> Tuple[Optional[Dict[str, Any]], str]:
    """Read one JSON-RPC message. Returns (msg, framing) where framing is
    ``content-length`` (Claude Desktop / MCP TS SDK) or ``ndjson`` (Cursor / line clients).
    ``msg is None`` means EOF.
    """
    header = stdin.readline()
    if header == "":
        return None, "content-length"
    if header.lower().startswith("content-length:"):
        try:
            length = int(header.split(":", 1)[1].strip())
        except ValueError:
            return None, "content-length"
        while True:
            line = stdin.readline()
            if line in ("", "\n", "\r\n"):
                break
        raw = stdin.read(length)
        if isinstance(raw, bytes):
            body = raw.decode("utf-8")
        else:
            # Text IO: Content-Length is bytes. If the stream is UTF-8 text,
            # ``read(length)`` is characters; hosts send ASCII JSON so this matches.
            body = raw
        return json.loads(body), "content-length"
    header = header.strip()
    if not header:
        return _read_message(stdin)
    return json.loads(header), "ndjson"


def _write_message(stdout, message: Dict[str, Any], framing: str) -> None:
    body = json.dumps(_jsonable(message), ensure_ascii=False, default=_json_default)
    if framing == "ndjson":
        stdout.write(body + "\n")
        stdout.flush()
        return
    payload = body.encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n"
    buf = getattr(stdout, "buffer", None)
    if buf is not None:
        buf.write(header.encode("ascii") + payload)
        buf.flush()
        return
    stdout.write(header)
    stdout.write(body)
    stdout.flush()


def run_stdio_server(stdin=None, stdout=None) -> None:
    """Serve MCP over stdio until EOF."""
    try:
        import plaq_bootstrap  # noqa: F401
    except Exception:
        root = Path(__file__).resolve().parents[4]
        bootstrap = root / "plaq_bootstrap.py"
        if bootstrap.exists():
            sys.path.insert(0, str(root))
            import plaq_bootstrap  # noqa: F401

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    while True:
        try:
            msg, framing = _read_message(stdin)
        except json.JSONDecodeError as exc:
            print(f"[plaq-mcp] invalid JSON: {exc}", file=sys.stderr)
            continue
        if msg is None:
            break
        if not isinstance(msg, dict):
            continue
        reply = handle_rpc(msg)
        if reply is not None:
            try:
                _write_message(stdout, reply, framing)
            except Exception as exc:
                print(f"[plaq-mcp] write failed: {exc}", file=sys.stderr)
