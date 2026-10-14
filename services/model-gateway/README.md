# Plaq-OS Model Gateway (`plaq-model-gateway`)

Centralized provider abstraction and model gateway routing for Plaq-OS agent execution, planning, criteria verification, and delivery summarization.

## Features
- `BaseModelProvider`: Abstract base class defining planning and validation contracts.
- `DeterministicPlanner` (aliased as `MockModelProvider`): Deterministic rule engine for quantum circuit synthesis, Pareto benchmarking, maintenance, and test suites.
- `LLMProvider`: Pluggable LLM provider integration with graceful fallback.
- `ModelGateway`: Centralized registry and query dispatcher.
