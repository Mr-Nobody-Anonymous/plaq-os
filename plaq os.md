# Plaq OS: The Fault-Tolerant Quantum Execution Planner & Resource Optimizer
## Master Research, Engineering, and Venture Architecture

> **Executive Vision**: Build the definitive operating system for Fault-Tolerant Quantum Computing (FTQC)—software that ingests arbitrary quantum algorithms, models physical-to-logical noise dynamics and hardware geometries, and discovers Pareto-optimal, cross-layer execution plans that minimize physical qubits, wall-clock execution time, and classical decoding bottlenecks.

---

## 1. The Core Scientific Hypothesis & The Plaq OS Paradigm Shift

### 1.1 The Transition from NISQ to FTQC
In Noisy Intermediate-Scale Quantum (NISQ) computing, optimization focused almost exclusively on minimizing raw 2-qubit gate counts to prevent decoherence before the circuit finishes. In Fault-Tolerant Quantum Computing (FTQC), however, physical qubits are bound together into **logical qubits** protected by Quantum Error-Correcting Codes (QECC), such as the Surface Code or Quantum Low-Density Parity-Check (qLDPC) codes.

In this regime, the primary bottlenecks are:
1. **Physical Qubit Footprint Overhead**: Each logical qubit requires between $2 d^2$ and $4 d^2$ physical qubits in rotated surface codes (e.g., 450–1,922 physical qubits per logical qubit at code distance $d = 15$ to $31$).
2. **Non-Clifford Magic State Bottleneck**: Fault-tolerant quantum processors cannot execute non-Clifford gates (such as $T$-gates or $CCZ$) transversally without violating the Eastin-Knill theorem. They must inject and distill magic states $|T\rangle = \frac{1}{\sqrt{2}}(|0\rangle + e^{i\pi/4}|1\rangle)$ in dedicated **Magic State Factories**, consuming up to 90% of the processor's spacetime volume.
3. **Classical Decoder Backlog Crisis**: Stabilizer syndrome measurements are generated every cycle ($t_{cyc} \sim 1\,\mu\text{s}$ for superconducting processors). If the classical decoding algorithm takes longer than $t_{cyc}$ to identify error chains, syndrome measurements accumulate in a FIFO buffer, causing an exponential backlog that halts execution.

### 1.2 The Cross-Layer Co-Optimization Hypothesis
Existing quantum toolchains operate in rigid, sequential silos:
$$\text{Algorithm Synthesis} \longrightarrow \text{Circuit Transpilation (Qiskit/TKET)} \longrightarrow \text{QEC Sizing (Azure QRE)} \longrightarrow \text{Post-facto Decoder}$$

This siloed approach frequently chooses sub-optimal plans:
* A compiler pass optimizing purely for minimum 2-qubit CX gates may serialize operations, elongating logical circuit depth. This forces the memory idle qubits to endure more error-correction rounds, which increases the required code distance $d$, ultimately multiplying total physical qubit demand by thousands.
* Conversely, allocating additional magic state factories expands spatial footprint but drastically compresses wall-clock runtime, preventing decoder backlog stalls.

**The Plaq OS Research Formulation**:
> *Jointly optimizing circuit compilation, qubit routing, error-correcting code distance, magic state factory parallelization, and classical decoder latency exposes non-dominated Pareto trade-offs superior to sequential optimization under fixed algorithm accuracy requirements ($\epsilon$) and target hardware noise specifications.*

---

## 2. Rigorous Mathematical Formulations

Let:
- $A$: Input quantum algorithm with $N_L$ logical qubits, Clifford depth $D_C$, $T$-count $N_T$, and $T$-depth $D_T$.
- $H$: Target hardware specification $\{p_1, p_2, p_{meas}, t_1, t_2, t_{cyc}, p_{th}, T_1, T_2, G_H, f_{crosstalk}\}$.
- $\theta \in \mathcal{F}(A, H)$: Candidate execution plan tuple:
  $$\theta = \left(\text{opt\_level}, \text{routing\_algorithm}, \text{code\_family}, d, N_{factories}, \text{distillation\_protocol}, \text{decoder\_arch}\right)$$
- $\epsilon$: Target algorithm reliability budget (maximum allowable failure probability, e.g. $\epsilon = 10^{-3}$).

### 2.1 Multi-Objective Optimization Problem

$$\begin{aligned}
\min_{\theta \in \mathcal{F}(A, H)} \quad & \mathbf{F}(A, \theta, H) = \begin{bmatrix} Q_{phys}(A, \theta, H) \\ T_{wall}(A, \theta, H) \\ P_{fail}(A, \theta, H) \end{bmatrix} \\
\text{subject to} \quad & P_{\mathrm{fail}}(A, \theta, H) \le \epsilon \\
& Q_{phys}(A, \theta, H) \le Q_{max} \\
& t_{\mathrm{decode}}(\theta, H) \le t_{cyc} \quad \text{(Backlog-free condition)}
\end{aligned}$$

Scalar cost ranking combines physical qubits and wall-clock time via normalized operator weights:
$$C(\theta) = Q_{phys}(\theta) + \alpha \cdot \frac{T_{wall}(\theta)}{1\,\text{ms}}$$

### 2.2 Quantum Error Correction Models

#### Model A: Rotated Surface Code
For code distance $d$ (odd integer $d \ge 3$) and composite physical error rate $p < p_{th} \approx 0.01$:
- **Logical Error Rate per Cycle**:
  $$P_L(d, p) \approx c \cdot \left( \frac{p}{p_{th}} \right)^{\frac{d+1}{2}}$$
  where $c \approx 0.1$ is the empirical fitting prefactor.
- **Physical Data Qubits per Logical Patch**:
  $$Q_{patch}(d) = 2 d^2$$
- **Composite Physical Error Rate**:
  $$p_{comp} = \left( p_{2q} + 0.5 \cdot p_{1q} + 0.25 \cdot p_{meas} \right) \times f_{crosstalk}$$
  where $f_{crosstalk} = 1.15$ on planar superconducting grids and $1.00$ on all-to-all ion traps.

#### Model B: Quantum Low-Density Parity-Check (qLDPC) Codes
For bivariate bicycle codes (e.g., IBM $[[144, 12, 12]]$):
- Physical qubit overhead scales as a **constant rate** $k / n \approx 0.083$, reducing physical qubit requirements by $4\times$ to $10\times$ compared to standard surface codes, but requiring non-local long-range coupler routing.

### 2.3 Magic State Distillation Mechanics

#### Ross-Selinger Optimal $T$-Gate Synthesis
Continuous single-qubit rotations $R_z(\theta)$ are synthesized into the Clifford+$T$ basis via gridsynth:
$$N_T = \left\lceil 3.21 \cdot \log_2\left(\frac{1}{\epsilon_{syn}}\right) + 2.5 \right\rceil$$
For synthesis tolerance $\epsilon_{syn} = 10^{-4}$, each rotation requires $N_T = 46$ $T$-gates.

#### 15-to-1 Bravyi-Kitaev Distillation Factory
- Input: 15 noisy magic states with physical error $p_{comp}$.
- Output: 1 purified magic state with logical error rate:
  $$P_{\text{magic\_fail}} \approx 35 \cdot p_{comp}^3$$
- Space footprint: $Q_{factory} = 16 \times 2 \times d_{factory}^2$ physical qubits.
- Distillation time: $T_{distill} = d_{factory}$ surface code cycles.

### 2.4 Classical Decoder Latency & Throughput Model
Let $t_{dec}$ be the decoding time per syndrome measurement cycle:
* **Streaming Custom ASIC**: $t_{dec} \approx 80\,\text{ns} \ll t_{cyc} \implies \text{No stall } (\text{Stall Factor} = 1.0)$.
* **Cryogenic / Warm FPGA**: $t_{dec} \approx 350\,\text{ns} \le t_{cyc} \implies \text{No stall } (\text{Stall Factor} = 1.0)$.
* **Distributed Networked CPU**: $t_{dec} \approx 1200\,\text{ns} > t_{cyc} \implies \text{Stall Factor} = \frac{t_{dec}}{t_{cyc}} = 1.2\times$.

When $t_{dec} > t_{cyc}$, the quantum processor must pause every round for the classical syndrome computation to resolve, directly slowing wall-clock runtime:
$$T_{wall} = K_{total\_cycles} \times \max\left(t_{cyc}, t_{dec}\right)$$

---

## 3. Supported Hardware Geometries

All hardware models are backed by peer-reviewed literature with explicit calibration uncertainty tolerances:

```
1. Superconducting Transmons (IBM Heron / Eagle Architecture)
   ├── Literature: arXiv:2310.02450 (IBM Quantum Heron Processor)
   ├── Physical Error Rates: p1 ~ 1.5e-4, p2 ~ 1.2e-3, p_meas ~ 8.0e-4
   ├── Cycle Time: 1,000 ns (1.0 microsecond)
   ├── Topology: Heavy-Hex planar graph
   ├── Calibration Uncertainty: +/- 15%
   └── Critical Challenge: Classical decoder throughput pressure (must decode in < 1 us)

2. Trapped Ion Shuttling (IonQ Forte / Quantinuum H2 Architecture)
   ├── Literature: arXiv:2305.03828 (High-fidelity shuttling-based ion traps)
   ├── Physical Error Rates: p1 ~ 1.0e-5, p2 ~ 1.0e-4 (Ultra-high fidelity)
   ├── Cycle Time: 150,000 ns (150 microseconds)
   ├── Topology: All-to-All reconfigurable ion shuttling
   ├── Calibration Uncertainty: +/- 10%
   └── Critical Challenge: Slow gate speeds; high wall-clock latency

3. Neutral Atom Arrays (QuEra Aquila Architecture)
   ├── Literature: Nature 626, 7914 (2024) (High-fidelity neutral atom arrays)
   ├── Physical Error Rates: p1 ~ 5.0e-5, p2 ~ 5.0e-4
   ├── Cycle Time: 20,000 ns (20 microseconds)
   ├── Topology: Dynamically reconfigurable 2D optical tweezer grid
   ├── Calibration Uncertainty: +/- 20%
   └── Critical Challenge: Atom shuttling loss and 2D spatial arrangement

4. Quantum LDPC Bivariate Bicycle (IBM qLDPC Architecture)
   ├── Literature: arXiv:2308.07915 (High-threshold bivariate bicycle codes)
   ├── Physical Error Rates: p1 ~ 1.0e-4, p2 ~ 1.0e-3
   ├── Cycle Time: 1,200 ns
   ├── Topology: Long-range coupled superconducting planar chip
   ├── Calibration Uncertainty: +/- 25%
   └── Critical Challenge: Complex non-local routing graphs
```

---

## 4. Empirical Model-Based Results & Trade-Off Analysis

### 4.1 Multi-Objective Pareto Trade-Off Analysis (Distinguishing Qubit vs. Runtime Exchanges)
To ensure complete scientific integrity, Plaq OS distinguishes between scalar cost improvements, physical qubit allocations, and wall-clock runtimes. 

The evaluation of a sequential compiler baseline against Plaq OS joint optimization yields the following results:

| Metric | Sequential Baseline (B2) | Plaq OS Joint Plan (B4) | Impact / Delta | Classification |
|:---|:---:|:---:|:---:|:---|
| **Physical Qubits** | 5,036 | 5,836 | **+800 qubits** (+15.8%) | *Higher spatial allocation* |
| **Wall-Clock Runtime** | 9.576 ms | 3.850 ms | **-5.726 ms (2.49x speedup)** | *Dramatic temporal speedup* |
| **Failure Probability ($P_{fail}$)** | $1.918 \times 10^{-4}$ | $4.050 \times 10^{-4}$ | **+$2.132 \times 10^{-4}$** | *Both strictly within $\epsilon = 10^{-3}$* |
| **Multi-Objective Cost Score** | 9,824 | 7,761 | **-21.0%** | *Modeled Pareto trade-off* |

#### Key Scientific Findings:
1. **The Trade-Off Mechanism**: The joint plan allocates one additional magic state factory (+800 physical qubits). In exchange, it achieves a **2.49x wall-clock execution speedup** by parallelizing non-Clifford distillation and preventing decoder backlog stalls.
2. **Reliability Verification**: While the failure probability of the joint plan is slightly higher ($4.050 \times 10^{-4}$ vs $1.918 \times 10^{-4}$), both plans comfortably satisfy the user-specified error budget $\epsilon = 10^{-3}$.
3. **Objective Scalar Metric**: The scalar cost score decreases by ~21% because the temporal gain exceeds the spatial penalty under the objective weighting function. This represents a legitimate and valuable Pareto trade-off, rather than a universal qubit reduction across all dimensions.

### 4.2 The Four-Baselines Comparative Protocol
Plaq OS benchmarks its optimization against four formal baselines:
1. **Baseline 1 (B1 - Original Workload)**: Raw logical circuit without compilation or hardware-topology routing.
2. **Baseline 2 (B2 - Standard Compiler)**: Qiskit Level-3 optimization with SABRE routing, followed by default resource estimation.
3. **Baseline 3 (B3 - Decoupled Resource Estimator)**: Sequential pipeline mirroring existing tools (transpile first, run decoupled QEC solver with fixed 2 factories and CPU decoder).
4. **Baseline 4 (B4 - Plaq OS Joint Co-Design)**: Full cross-layer co-optimization across compiler passes, code distances, dynamic factory sizing, and backlog-free decoding.

### 4.3 Genuine Stim and PyMatching MWPM Verification
Plaq OS integrates genuine quantum error correction simulation using Google's Stim and PyMatching:
- **Rotated Surface Code Memory Experiments**: Exact syndrome schedules with depolarizing, measurement, and reset errors.
- **Minimum-Weight Perfect Matching (MWPM)**: C++ syndrome decoding on detector error graphs (`dem`).
- **Statistical Rigor**: Wilson score 95% confidence intervals on logical error rates $\hat{p}_L$.
- **Threshold Curves**: Reproduces the circuit-level surface code threshold ($p_{th} \approx 0.7\% - 1.0\%$).

---

## 5. Comprehensive Repository Gap Analysis & Resolution Matrix

The scientific gap analysis identified 7 major architectural challenges. All have been fully resolved in Plaq OS v0.3.0:

| Gap Identified | Audit Findings | Resolution Implemented in Plaq OS v0.3.0 |
|:---|:---|:---|
| **1. Unsubstantiated Claims** | "Hypothesis Confirmed" claim concealed that joint plan used +800 more qubits. | Replaced with transparent Pareto trade-off classification. Qubits, runtime, and failure probabilities are reported independently. |
| **2. Synthetic QEC Simulation** | Earlier `stim_bridge.py` generated toy random numbers. | Implemented genuine Stim rotated surface code memory circuits and PyMatching MWPM decoding with Wilson intervals. |
| **3. Arbitrary Cost Model Numbers** | Fixed factor of 50 $T$-gates per rotation. | Implemented Ross-Selinger / gridsynth synthesis scaling ($N_T \approx 3.21 \log_2(1/\epsilon_{syn}) + 2.5$) and DAG $T$-depth. |
| **4. Hardware Provenance** | Unreferenced hardware error parameters. | Documented peer-reviewed citations (Heron, Forte, Aquila, qLDPC) with calibration uncertainty tolerances. |
| **5. Undocumented Workloads** | Unspecified benchmark circuits. | Built `WORKLOAD_MANIFEST` defining formal problem definitions, Hamiltonians, and validation criteria. |
| **6. Benchmarking Fairness** | Shared cache contaminated search method benchmarks. | Enforced cache isolation per search method and added SHA-256 compilation fingerprints. |
| **7. Research Infrastructure** | Missing CI, license, and provenance tracking. | Added GitHub Actions CI, MIT License, and automated `results/run_manifest.json` generation. |

---

## 6. Commercial Startup Strategy & Business Model

### 6.1 Market Sizing
* **Total Addressable Market (TAM)**: \$4.5B (Global fault-tolerant quantum computing infrastructure and design automation by 2032).
* **Serviceable Addressable Market (SAM)**: \$850M (Software tools for quantum algorithm development, resource planning, and compiler stacks).
* **Serviceable Obtainable Market (SOM)**: \$120M (Enterprise execution planning software for pharmaceuticals, materials science, and defense).

### 6.2 Target Customer Personas
1. **Pharma & Materials Simulation Teams**:
   - Running electronic structure VQE / Phase Estimation for catalyst and drug discovery (e.g. FeMoCo Nitrogenase).
   - *Pain Point*: Need to prove whether an algorithm requires 100,000 physical qubits in 2028 or 10,000,000 in 2035.
2. **Quantum Hardware Providers (OEMs)**:
   - Superconducting, trapped ion, and neutral atom manufacturers.
   - *Pain Point*: Need customer workloads benchmarked to demonstrate commercial utility and justify cryogenic system sizing.
3. **Defense & High-Performance Computing (HPC) Datacenters**:
   - Planning post-quantum cryptography transitions and datacenter power/cryostat sizing.

### 6.3 Product Packaging & Pricing
* **Community Tier (Free / Open Source - MIT)**: Core Python CLI for basic circuit estimation, Stim/PyMatching QEC simulation, and single-point calculations.
* **Professional / Research Tier (\$25,000 / seat / year)**: Cross-layer Pareto optimizer, standard hardware models, and exportable execution reports.
* **Enterprise / Datacenter Tier (\$75,000+ / seat / year + API Usage)**: Custom hardware calibration ingestion, qLDPC and custom code support, real-time CI/CD pipeline integration, and dedicated FPGA decoder co-simulation.

---

## 7. The 12-Week Operational Roadmap

```
Week 1–2:  Literature Review & Formal IR Specification
           └── Deliverable: Validated Python IR and baseline specification document.

Week 3–4:  Compiler Transpilation Benchmarking Suite
           └── Deliverable: Automated multi-level Qiskit baseline exporter (benchmark.py).

Week 5–6:  Fault-Tolerant Resource & Decoder Modeling
           └── Deliverable: Surface code solver, 15-to-1 factory sizing, and decoder backlog models.

Week 7–8:  Joint Cross-Layer Search & Pareto Engine
           └── Deliverable: Combinatorial search with compilation caching (optimizer.py).

Week 9–10: Hypothesis Testing & Ablation Studies
           └── Deliverable: Empirical comparison tables and sensitivity reports across 8+ workloads.

Week 11–12: Commercial Packaging, CLI & Technical Report
           └── Deliverable: Unified CLI (main.py), interactive dashboard, and investor presentation.
```

---
*Maintained by the Plaq OS Project Contributors.*
