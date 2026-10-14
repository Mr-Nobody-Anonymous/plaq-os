# E2E Test Infra: Plaq-OS

## Test Philosophy
- Opaque-box, requirement-driven, derived directly from `ORIGINAL_REQUEST.md` and user-facing contracts.
- Systematic 4-tier methodology: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial + Real-World Workload Testing.
- Progressive testability: verification mechanism does not require features more complex than what it verifies.

## Feature Inventory
| # | Feature | Source (Requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| 1 | Monorepo Structure & Layout | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 2 | Quantum Modularization & 38 Unit Tests | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 3 | SQLite Control Plane Persistence & Schema | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 4 | Task Lifecycle State Machine (8 States) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 5 | Append-Only Audit Trail & Chained Hash | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 6 | Secret Redaction Filter | ORIGINAL_REQUEST §R2, AC | 5 | 5 | ✓ |
| 7 | Checkpoint Recovery Upon Restart | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 8 | Sandbox PathGuard & Path Traversal Rejection | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 9 | Subprocess Runner & Timeout / Tree-Kill | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 10 | Agent Execution Loop (7-Stage Deterministic) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 11 | Typed Tool Registry (6 Permission Tiers) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 12 | Human Approval Gates & Blocking Transitions | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 13 | FastAPI REST Endpoints & OpenAPI 3.1 | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 14 | WebSocket & SSE Real-time Event Streaming | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 15 | Unified `plaq` CLI (task, quantum, workspace, serve) | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 16 | Plaq Workbench 4-Panel OS Interface | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ |

## Test Architecture
- **Location**: `tests/e2e/`
- **Harness & Runner**:
  - `pytest tests/e2e -v`
  - Uses `plaq_bootstrap.py` for monorepo PYTHONPATH resolution.
  - Test fixtures: in-memory / temporary SQLite databases, FastAPI `TestClient`, temporary workspace directories with git repos.
- **Directory Layout**:
  ```text
  tests/e2e/
  ├── conftest.py               # Shared fixtures: temp_workspace, test_db, api_client, event_recorder
  ├── test_tier1_feature.py     # Tier 1: Unit & feature isolation verification (>=5 per feature)
  ├── test_tier2_boundary.py    # Tier 2: Boundary, corner cases, error-prone inputs (>=5 per boundary)
  ├── test_tier3_pairwise.py    # Tier 3: Pairwise cross-feature combinations
  └── test_tier4_workloads.py   # Tier 4: Real-world end-to-end application scenarios
  ```

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Full Agent Task Lifecycle: Submit Goal, Plan, Execute Tools, Redact Secrets, Publish Artifact, Complete | F3, F4, F5, F6, F10, F11 | High |
| 2 | Sensitive Operation Approval: Agent attempts destructive file deletion, halts at Approval Gate, Human Approves via API, Agent Resumes and Completes | F4, F6, F10, F11, F12, F13 | High |
| 3 | Server Crash Checkpoint Recovery: Task running multi-step quantum job is interrupted by process kill, server restarts, recovers task state, and resumes | F3, F4, F7, F10 | Critical |
| 4 | CLI to API to Quantum Co-design Pipeline: User runs `plaq quantum estimate` and `plaq task create`, CLI talks to REST API, dispatches Stim/PyMatching QEC, outputs table | F2, F13, F15 | High |
| 5 | Real-time Workbench Monitoring: WebSocket client connects, listens to live agent step updates, tool execution stream, and receives completion event | F4, F5, F14, F16 | High |

## Coverage Thresholds
- Tier 1: Feature coverage >=5 test cases per major feature area (~80 tests).
- Tier 2: Boundary & Corner coverage >=5 test cases per boundary condition (~80 tests).
- Tier 3: Pairwise coverage of major feature interactions (~20 tests).
- Tier 4: Realistic end-to-end user application scenarios (>=5 workflows).
- **Total Minimum**: >= 180 comprehensive E2E test cases passing 100%.
