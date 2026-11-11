# AI agents, complex quantum simulation, and MCP

Plaq-OS now exposes the fault-tolerant quantum engine to **agents** three ways:

1. The 7-stage agent loop (`plaq task create` / `POST /api/v1/tasks/{id}/run`)
2. Direct tools (`quantum.run`, `quantum.simulate`, `quantum.optimize`, …)
3. The **MCP** server (`plaq mcp` / `python -m plaq_mcp`) for Claude Desktop, Cursor, etc.

## What an agent can actually simulate

| Tool | Physics | Engine |
|---|---|---|
| `quantum.run` | Statevector amplitudes, shot counts, MaxCut / Ising energy | Qiskit `quantum_info.Statevector` |
| `quantum.simulate` | Rotated surface-code logical error, Wilson CI | Stim + PyMatching MWPM |
| `quantum.threshold` | p_L vs (d, p) sweep | Stim |
| `quantum.compile` | Named workloads or OpenQASM → T-count / depth | Qiskit + Ross-Selinger |
| `quantum.estimate` | d, physical qubits, runtime, P_fail | rotated surface-code cost model |
| `quantum.optimize` | Pareto frontier over compiler / factories / decoder / QEC | joint co-design search |
| `quantum.baselines` | Raw vs Qiskit-L3 vs decoupled vs joint | 4-baselines protocol |

Workloads: `bell`, `ghz`, `qaoa` / `qaoa_cycle_6q`, `qft`, `bv`, `chemistry` / FeMoCo, `shor`, `clifford_t`, plus any OpenQASM 2.0 body.

## Background queue

Long optimizations no longer block the API worker:

```bash
plaq task create "Run a QAOA MaxCut simulation" --json
plaq task run <task_id> --wait
# or
curl -X POST http://127.0.0.1:8000/api/v1/tasks/<id>/run?background=true
```

Jobs live in SQLite (`jobs` table, schema migration v1) and are drained by in-process daemon threads.

## MCP

```bash
python -m plaq_mcp
```

Claude Desktop snippet:

```json
{
  "mcpServers": {
    "plaq-os": {
      "command": "python",
      "args": ["-m", "plaq_mcp"]
    }
  }
}
```

Tools: `quantum_compile`, `quantum_estimate`, `quantum_simulate`, `quantum_run`, `quantum_optimize`, `quantum_baselines`, `quantum_threshold`, `quantum_workloads`, `quantum_hardware`, `task_create`, `task_run`, `task_status`.

Resources: `plaq://workloads`, `plaq://hardware`, `plaq://tools`.

## Auth

`plaq serve` requires `Authorization: Bearer <key>` unless `PLAQ_AUTH=off`.
The key is generated at `~/.plaq/api_key` (or next to `PLAQ_DB_PATH`).
Health (`/api/v1/health`) stays public. Pytest stays open.
