## 2026-10-14T13:25:05Z

You are explorer_m3_1 (Explorer M3-1: Sandbox Manager).
Your working directory is: C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m3_1
Project root: C:\Users\hp\Desktop\plaq-os

MANDATORY FIRST STEP:
Read C:\Users\hp\Desktop\plaq-os\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Also read C:\Users\hp\Desktop\plaq-os\.agents\teamwork\orchestrator_1\PROJECT.md.

OBJECTIVE:
Investigate and design `services/sandbox-manager` (Feature 13: PathGuard, Feature 14: Subprocess Runner, Feature 15: Git Worktree Isolation).
1. Inspect requirements in `ORIGINAL_REQUEST.md § R3`.
2. Inspect tests in `tests/e2e/test_tier1_feature.py` (specifically `TestFeature08SandboxPathGuard` and `TestFeature09SubprocessRunner`) and `tests/e2e/test_tier2_boundary.py` (specifically path traversal and command injection tests).
3. Design the package `plaq-sandbox` (`services/sandbox-manager/`):
   - `pyproject.toml`
   - `src/plaq_sandbox/guard.py`: `PathGuard`, `PathTraversalError` with null-byte detection, URL-encoding unquote, canonical resolving, ensuring target is within workspace root.
   - `src/plaq_sandbox/runner.py`: `ProcessRunner`, `ProcessResult` with timeout support, subprocess execution, environment isolation, Windows process-tree termination with `taskkill /F /T /PID <pid>` on Windows / `os.killpg` on Unix, capturing stdout/stderr/exit_code/duration.
   - `src/plaq_sandbox/worktree.py`: `WorktreeManager` managing isolated `.worktrees/<task_id>` git worktrees with creation, status, and cleanup.
   - `src/plaq_sandbox/__init__.py`: Clean exports.

OUTPUT REQUIREMENT:
Write your investigation report to `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m3_1\handoff.md`. Include:
- Observation (verified test contracts and requirements)
- Logic Chain (design architecture and Windows-safe process handling)
- Caveats (Windows file locks, git worktree nuances)
- Worker Action Plan
Send a message to your orchestrator when done.
