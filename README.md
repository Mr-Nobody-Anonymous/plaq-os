# Q-Day OS

**Fault-Tolerant Quantum Execution Planner & Cross-Layer Resource Optimizer**

Q-Day OS is an enterprise and research operating platform designed to answer the fundamental question of quantum scaling:
> *How can we obtain the same reliable quantum computation using fewer physical resources, less time, or both?*

Instead of treating circuit compilation, quantum error correction (QEC) allocation, and classical decoding as isolated silos, Q-Day OS searches across the entire co-design space to find **Pareto-optimal execution plans** balancing physical qubits, wall-clock execution time, and reliability constraints.

---

## Quickstart on Windows

### 1. Installation
Navigate to this directory in PowerShell:
```powershell
cd C:\Users\hp\Desktop\q-day-os
python -m pip install -r requirements.txt
```

### 2. Launch the Cyber-Quantum UI
```powershell
python main.py --ui
```
*(Spins up local server at `http://127.0.0.1:8500` with live REST endpoints and opens the interactive cyber-quantum dashboard in your browser).*
Or open `results/quantum_ui.html` directly in any web browser for immediate offline interactive exploration.

### 3. Run the Complete R&D Pipeline
```powershell
python main.py --run-all
```
This executes:
1. **Transpilation Baselines**: Benchmarks 8 workload families across 4 Qiskit optimization levels and exports to `results/benchmark_results.csv`.
2. **Joint Cross-Layer Optimization**: Discovers the multi-objective Pareto frontier over compiler levels, routing algorithms, magic-state factory counts, and classical decoder architectures.
3. **Hypothesis Testing**: Directly compares Sequential Compilation against Q-Day OS Joint Optimization.
4. **Four-Baselines Protocol**: Formally evaluates Baseline 1 (Original), Baseline 2 (Standard Compiler L3), Baseline 3 (Decoupled Estimator / MS QRE style), and Baseline 4 (Q-Day Joint Optimizer).
5. **Systematic Ablation Study**: Quantifies cost penalties when decoder co-design, factory scaling, routing optimization, or QEC distance solvers are isolated.
6. **Search Algorithms Comparison**: Benchmarks Exhaustive Ground Truth, Greedy Coordinate Descent, Simulated Annealing, and Random Search.
7. **Pareto Frontier Visualization**: Generates publication-ready trade-off plots in `results/pareto_frontier.png`.
8. **Interactive Dashboards**: Generates `results/dashboard.html` and `results/quantum_ui.html`.

---

## Command Line Options

```powershell
# Launch futuristic cyber-quantum UI
python main.py --ui

# Run Four-Baselines comparative protocol
python main.py --baselines --workload chemistry_femoco_6q

# Run systematic ablation study
python main.py --ablation --workload chemistry_femoco_6q

# Benchmark search algorithms (Exhaustive, Greedy, Annealing, Random)
python main.py --search-bench --workload chemistry_femoco_6q

# Run compiler benchmarks only
python main.py --benchmark --hardware superconducting

# Optimize a specific algorithm workload (e.g., FeMoCo nitrogenase)
python main.py --optimize --workload chemistry_femoco_6q --hardware superconducting --epsilon 1e-3

# Compare Sequential vs Joint optimization
python main.py --compare --hardware trapped_ion

# Run full test suite (33/33 tests passing)
python -m pytest
```

---

## Project Structure

```
q-day-os/
├── q-day os.md              # Master research thesis, math equations, and startup plan
├── circuits.py              # Workloads (QAOA, QFT, Bernstein-Vazirani, Clifford+T, Chemistry, Shor)
├── hardware.py              # Target hardware models (Superconducting, Trapped Ion, Neutral Atom, qLDPC)
├── cost_model.py            # Surface code scaling, 15-to-1 factories, decoder latency & cascades
├── benchmark.py             # Compiler baseline suite & CSV exporter
├── optimizer.py             # Joint search engine & Pareto frontier extractor
├── search_algorithms.py     # Search benchmark suite (Exhaustive, Greedy, Annealing, Random)
├── baselines.py             # 4-Baselines protocol & systematic ablation study engine
├── stim_bridge.py           # Stim stabilizer circuit generator & Monte Carlo threshold sampler
├── dashboard.py             # Standalone executive HTML dashboard generator
├── server.py                # REST API & static web server (port 8500)
├── main.py                  # Unified CLI and visualization generator
├── ui/                      # Futuristic cyber-quantum mission control frontend
│   └── index.html
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Package configuration
├── tests/                   # Comprehensive pytest test suite (33 tests)
│   ├── test_circuits.py
│   ├── test_hardware.py
│   ├── test_cost_model.py
│   ├── test_optimizer.py
│   ├── test_search_algorithms.py
│   ├── test_baselines.py
│   └── test_stim_bridge.py
└── results/                 # Benchmark datasets, Pareto JSON, plots, and dashboards
    ├── quantum_ui.html      # Standalone cyber-quantum mission control UI
    ├── dashboard.html       # Executive HTML dashboard
    ├── pareto_frontier.png  # Publication-grade Pareto scatter plot
    └── *.json / *.csv
```

---

## Research Foundations & Mathematics

See [`q-day os.md`](./q-day%20os.md) for the complete theoretical derivation, including:
- Rotated surface code logical error rate: $P_L(d, p) \approx c \left(\frac{p}{p_{th}}\right)^{(d+1)/2}$
- Quantum LDPC bivariate bicycle constant-rate scaling
- 15-to-1 magic-state distillation footprint and multi-level cascade formulas
- Classical decoder throughput bottlenecks: $\max(t_{cycle}, t_{decode})$
- Mathematical formulation of multi-objective Pareto dominance
