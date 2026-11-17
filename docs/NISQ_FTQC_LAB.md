# NISQ ↔ FTQC lab

Plaq-OS now has a **second physics path** next to Stim surface-code memory:

| Layer | What it is | What it is not |
|---|---|---|
| `quantum.noise` | Depolarizing + readout mixture on the ideal statevector | Qiskit Aer / a real IBM noise model |
| `quantum.mitigate` | Readout inversion + zero-noise extrapolation (Temme 2017) | PEC, CDR, or Mitiq |
| `quantum.transpile` | BFS SWAP router on linear / grid / toy heavy-hex | Sabre, lookahead, or a full IBM lattice |
| `quantum.surgery` | Patch + 15-to-1 factory + merge/split cycle estimate | A 3-D Classiq / CUDA-Q Logical layout |
| `quantum.draw` | Qiskit text + Mermaid | A drag-and-drop editor |
| `quantum.sampler` | Local SamplerV2 analogue (statevector shots) | `qiskit-ibm-runtime` SamplerV2 |
| `quantum.estimator` | Local EstimatorV2 analogue (Pauli ⟨P⟩) | IBM Runtime EstimatorV2 |
| `quantum.suppress` | Gate-level XpXm DD + CX Pauli twirl | Pulse-level DD / hardware twirl |
| `quantum.vqe` | 2-qubit hardware-efficient VQE on toy H₂ | PySCF / Qiskit Nature |
| `quantum.frame` | Deferred Pauli-frame update counts | An MLIR FTQC dialect |
| `quantum.repetition` | Majority-vote bit-flip repetition code | Stim surface-code memory |
| `quantum.bundle` | Versioned OpenQASM 2/3 job bundle + FT fields | A real QPU submission |
| Workloads | Grover, teleport, QPE, Deutsch–Jozsa, Toffoli | Full Shor / chemistry Hamiltonians |

No new pip packages. `--lite` still works (no Aer, no Mitiq, no Stim required for this lab).

## Why these

2025–2026 FTQC software (Classiq Fault Tolerance Engine, CUDA-Q Logical, IBM Runtime resilience levels) all sit on the same stack: **noisy circuits → mitigation → topology → lattice surgery**, plus Sampler/Estimator primitives, dynamical decoupling, Pauli-frame deferral, and versioned QASM3 job bundles. Plaq-OS now exposes that stack to the agent loop, MCP, CLI, API, and workbench so an agent can actually *run* the comparison instead of only quoting the analytical cost model.

## Commands

```bash
plaq quantum run grover --json
plaq quantum noise bell --p2 0.03 --json
plaq quantum mitigate bell --json
plaq quantum transpile qft --topology heavy_hex --json
plaq quantum surgery qft --distance 5 --json
plaq quantum draw teleport
plaq quantum sampler bell --shots 1024
plaq quantum estimator bell --observable ZZ
plaq quantum suppress bell --sequence XpXm
plaq quantum vqe --maxiter 40
plaq quantum frame qft --qubits 4
plaq quantum repetition --distance 3 --error-rate 0.1
plaq quantum bundle bell --json
```

API: `POST /api/v1/quantum/{noise,mitigate,transpile,surgery,draw,sampler,estimator,suppress,vqe,frame,repetition,bundle}`

Live workbench file tree: `GET /api/v1/workspace/tree`

MCP: `quantum_noise`, `quantum_mitigate`, `quantum_transpile`, `quantum_surgery`, `quantum_draw`, `quantum_sampler`, `quantum_estimator`, `quantum_suppress`, `quantum_vqe`, `quantum_frame`, `quantum_repetition`, `quantum_bundle`
