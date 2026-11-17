# NISQ ↔ FTQC lab

Plaq-OS now has a **second physics path** next to Stim surface-code memory:

| Layer | What it is | What it is not |
|---|---|---|
| `quantum.noise` | Depolarizing + readout mixture on the ideal statevector | Qiskit Aer / a real IBM noise model |
| `quantum.mitigate` | Readout inversion + zero-noise extrapolation (Temme 2017) | PEC, CDR, or Mitiq |
| `quantum.transpile` | BFS SWAP router on linear / grid / toy heavy-hex | Sabre, lookahead, or a full IBM lattice |
| `quantum.surgery` | Patch + 15-to-1 factory + merge/split cycle estimate | A 3-D Classiq / CUDA-Q Logical layout |
| `quantum.draw` | Qiskit text + Mermaid | A drag-and-drop editor |
| Workloads | Grover, teleport, QPE, Deutsch–Jozsa, Toffoli | Full Shor / chemistry Hamiltonians |

No new pip packages. `--lite` still works (no Aer, no Mitiq, no Stim required for this lab).

## Why these

2025–2026 FTQC software (Classiq Fault Tolerance Engine, CUDA-Q Logical, IBM Runtime resilience levels) all sit on the same stack: **noisy circuits → mitigation → topology → lattice surgery**. Plaq-OS now exposes that stack to the agent loop, MCP, CLI, API, and workbench so an agent can actually *run* the comparison instead of only quoting the analytical cost model.

## Commands

```bash
plaq quantum run grover --json
plaq quantum noise bell --p2 0.03 --json
plaq quantum mitigate bell --json
plaq quantum transpile qft --topology heavy_hex --json
plaq quantum surgery qft --distance 5 --json
plaq quantum draw teleport
```

API: `POST /api/v1/quantum/{noise,mitigate,transpile,surgery,draw}`

MCP: `quantum_noise`, `quantum_mitigate`, `quantum_transpile`, `quantum_surgery`, `quantum_draw`
