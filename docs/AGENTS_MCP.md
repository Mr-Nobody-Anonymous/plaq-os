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
| `quantum.noise` | Ideal vs depolarizing+readout TVD | phenomenological NISQ model |
| `quantum.mitigate` | Readout inversion + ZNE | Temme et al. 2017 |
| `quantum.transpile` | SWAP count on linear/grid/heavy-hex | BFS router |
| `quantum.surgery` | Patches, 15-to-1 factories, code cycles | Litinski / Fowler model |
| `quantum.draw` | ASCII + Mermaid | Qiskit text drawer |
| `quantum.sampler` | Shot counts from the ideal statevector | local SamplerV2 analogue |
| `quantum.estimator` | Pauli expectation ⟨P⟩ | local EstimatorV2 analogue |
| `quantum.suppress` | XpXm dynamical decoupling + CX Pauli twirl | gate-level analogue |
| `quantum.vqe` | Hardware-efficient VQE on toy H₂ | SciPy COBYLA + statevector |
| `quantum.frame` | Deferred Pauli-frame updates | FTQC compiler artefact |
| `quantum.repetition` | Majority-vote bit-flip repetition code | Stim-free QEC demo |
| `quantum.bundle` | OpenQASM 2/3 + metrics + FT estimate | versioned job bundle |

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

Tools: `quantum_compile`, `quantum_estimate`, `quantum_simulate`, `quantum_run`, `quantum_optimize`, `quantum_baselines`, `quantum_threshold`, `quantum_workloads`, `quantum_hardware`, `quantum_noise`, `quantum_mitigate`, `quantum_transpile`, `quantum_surgery`, `quantum_draw`, `quantum_sampler`, `quantum_estimator`, `quantum_suppress`, `quantum_vqe`, `quantum_frame`, `quantum_repetition`, `quantum_bundle`, `quantum_qasm`, `task_create`, `task_run`, `task_status`.

Prompts: `nisq_lab`, `ftqc_estimate`, `lattice_surgery`, `vqe_h2`, `job_bundle`. Stdio accepts **Content-Length** (Claude Desktop) and **NDJSON** (Cursor / line clients). `quantum_simulate` returns a clean tool error if Stim is missing instead of crashing the host.

Successful tool calls include MCP 2025-06-18 `structuredContent` (JSON object) next to the text block. Argument completion is advertised as `completions` and served at `completion/complete`.

Resources: `plaq://workloads`, `plaq://hardware`, `plaq://tools`.

Workbench file explorer is live via `GET /api/v1/workspace/tree` (PathGuard-confined to `PLAQ_WORKSPACE` or cwd).

## Auth

`plaq serve` requires `Authorization: Bearer <key>` unless `PLAQ_AUTH=off`.
The key is generated at `~/.plaq/api_key` (or next to `PLAQ_DB_PATH`).
Health (`/api/v1/health`) stays public. Pytest stays open.
