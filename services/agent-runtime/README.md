# Plaq-OS Agent Runtime (`plaq-agent-runtime`)

The Agent Runtime provides the deterministic 7-stage execution loop, typed 6-tier tool registry, and human approval gates for Plaq-OS.

## Components
- `AgentRuntime`: Coordinates the 7-stage deterministic task lifecycle (`Receive Task` -> `Inspect Context` -> `Plan & Define Criteria` -> `Execute Tool` -> `Collect Output` -> `Verify` -> `Review Diff & Deliver`).
- `ToolRegistry`: Typed registry enforcing 6 permission tiers (`read_only`, `workspace_write`, `git_isolated`, `process_sandbox`, `quantum_engine`, `privileged`), parameter validation, duration measurement, secret redaction, and audit logging.
- `ApprovalManager`: Intercepts destructive commands and critical file modifications, transitions tasks to `blocked`, and resumes or fails tasks upon operator decision.
- 12 Built-in Domain Tools:
  - Workspace: `workspace.list`, `workspace.read`, `workspace.write`, `workspace.patch`
  - Git: `git.diff`, `git.branch`
  - Process: `terminal.run`, `tests.run`
  - Quantum: `quantum.compile`, `quantum.estimate`, `quantum.simulate`
  - Artifacts: `artifacts.publish`
