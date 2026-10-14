# Plaq-OS Sandbox Manager (`plaq-sandbox`)

The Sandbox Manager provides process execution confinement, directory boundary enforcement (`PathGuard`), and isolated Git worktree management for agent tasks.

## Components
- `PathGuard`: Canonical path resolution with recursive URL decoding and null-byte injection detection.
- `ProcessRunner`: Sandboxed subprocess execution with configurable timeouts and Windows process-tree termination (`taskkill /F /T`).
- `WorktreeManager`: Isolated worktree lifecycle management under `.worktrees/<task_id>` with Windows file permission handling.
- `SandboxManager`: Unified façade conforming to `PROJECT.md § 3`.
